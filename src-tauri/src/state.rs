//! Состояние приложения и фоновая запись на диск.
//!
//! Ключевое отличие от v0.9: мутации живут в памяти и отвечают мгновенно,
//! а на диск уходит один атомарный снапшот на пачку правок. Диск никогда
//! не трогается под мьютексом стора — сначала снимок, потом запись.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use pwl_core::flush::Debouncer;
use pwl_core::migrate::{self, MigrationReport};
use pwl_core::{persist, NoopProtector, Protector, Snapshot, Store};
use tauri::{AppHandle, Emitter};

use crate::secrets;

pub enum FlushMsg {
    Dirty,
    Now,
    /// Синхронная запись с подтверждением — используется при выходе.
    Sync(std::sync::mpsc::Sender<()>),
    Shutdown,
}

pub struct AppState {
    pub store: Arc<Mutex<Store>>,
    pub data_dir: PathBuf,
    pub migration: Mutex<Option<MigrationReport>>,
    tx: Sender<FlushMsg>,
}

impl AppState {
    pub fn library_path(&self) -> PathBuf {
        persist::library_path(&self.data_dir)
    }

    /// Пометить, что данные изменились. Не блокирует и не пишет на диск.
    pub fn mark_dirty(&self) {
        let _ = self.tx.send(FlushMsg::Dirty);
    }

    /// Дождаться записи (перед выходом или по требованию пользователя).
    pub fn flush_now(&self) {
        let _ = self.tx.send(FlushMsg::Now);
    }

    pub fn shutdown(&self) {
        let _ = self.tx.send(FlushMsg::Shutdown);
    }

    /// Дождаться, пока данные реально лягут на диск. Без слипов «на глазок».
    pub fn flush_blocking(&self, timeout: Duration) -> bool {
        let (tx, rx) = mpsc::channel();
        if self.tx.send(FlushMsg::Sync(tx)).is_err() {
            return false;
        }
        rx.recv_timeout(timeout).is_ok()
    }

    pub fn take_migration(&self) -> Option<MigrationReport> {
        self.migration.lock().ok()?.take()
    }
}

/// Загрузка с миграцией. Порядок важен: если новый файл уже есть, старые
/// данные не трогаем вообще.
fn load_or_migrate(
    dir: &PathBuf,
    protector: &dyn Protector,
) -> pwl_core::Result<(Snapshot, Option<MigrationReport>, Option<String>)> {
    let path = persist::library_path(dir);
    match persist::load(&path) {
        Ok(Some(snapshot)) => Ok((snapshot, None, None)),
        Ok(None) => {
            if migrate::legacy_present(dir) {
                let (snapshot, report) = migrate::run(dir, protector)?;
                Ok((snapshot, Some(report), None))
            } else {
                Ok((Snapshot::default(), None, None))
            }
        }
        Err(_) => {
            let (snapshot, warning) = persist::load_with_recovery(&path)?;
            Ok((snapshot, None, warning))
        }
    }
}

pub fn init(app: &AppHandle) -> pwl_core::Result<Arc<AppState>> {
    let data_dir = persist::default_data_dir();
    std::fs::create_dir_all(&data_dir)?;

    let protector: Arc<dyn Protector> = secrets::platform_protector();
    let (mut snapshot, report, warning) = load_or_migrate(&data_dir, protector.as_ref())?;

    if let Some(text) = warning {
        let _ = app.emit("pwl://warning", text);
    }

    // Мигрированные пароли были открытым текстом — шифруем сразу.
    if report.is_some() {
        let mut tmp = Store::new(std::mem::take(&mut snapshot), protector.clone());
        let secured = tmp.secure_secrets().unwrap_or(0);
        snapshot = tmp.into_snapshot();
        if secured > 0 {
            let _ = app.emit(
                "pwl://warning",
                format!("Пароли зашифрованы средствами Windows: {secured}"),
            );
        }
        persist::save_atomic(&persist::library_path(&data_dir), &snapshot, false)?;
    }

    let store = Arc::new(Mutex::new(Store::new(snapshot, protector)));
    let (tx, rx) = mpsc::channel::<FlushMsg>();
    let backup_pending = Arc::new(AtomicBool::new(true));

    spawn_flusher(
        app.clone(),
        store.clone(),
        rx,
        persist::library_path(&data_dir),
        backup_pending,
    );

    Ok(Arc::new(AppState {
        store,
        data_dir,
        migration: Mutex::new(report),
        tx,
    }))
}

fn spawn_flusher(
    app: AppHandle,
    store: Arc<Mutex<Store>>,
    rx: Receiver<FlushMsg>,
    path: PathBuf,
    backup_pending: Arc<AtomicBool>,
) {
    std::thread::Builder::new()
        .name("pwl-flush".into())
        .spawn(move || {
            let epoch = Instant::now();
            let now = || epoch.elapsed().as_millis() as u64;
            let mut deb = Debouncer::default();

            loop {
                let wait = deb
                    .wait_ms(now())
                    .map(Duration::from_millis)
                    .unwrap_or_else(|| Duration::from_secs(3600));
                match rx.recv_timeout(wait) {
                    Ok(FlushMsg::Dirty) => deb.edit(now()),
                    Ok(FlushMsg::Now) => {
                        flush(&app, &store, &path, &backup_pending);
                        deb.clear();
                    }
                    Ok(FlushMsg::Sync(ack)) => {
                        flush(&app, &store, &path, &backup_pending);
                        deb.clear();
                        let _ = ack.send(());
                    }
                    Ok(FlushMsg::Shutdown) => {
                        flush(&app, &store, &path, &backup_pending);
                        break;
                    }
                    Err(RecvTimeoutError::Timeout) => {
                        if deb.due(now()) {
                            flush(&app, &store, &path, &backup_pending);
                            deb.clear();
                        }
                    }
                    Err(RecvTimeoutError::Disconnected) => {
                        flush(&app, &store, &path, &backup_pending);
                        break;
                    }
                }
            }
        })
        .expect("не удалось запустить поток записи");
}

fn flush(
    app: &AppHandle,
    store: &Arc<Mutex<Store>>,
    path: &PathBuf,
    backup_pending: &Arc<AtomicBool>,
) {
    // Снимок под мьютексом, запись — без него.
    let (snapshot, revision) = {
        let guard = match store.lock() {
            Ok(g) => g,
            Err(_) => return,
        };
        if !guard.is_dirty() {
            return;
        }
        (guard.snapshot().clone(), guard.revision())
    };

    let keep_backup = backup_pending.swap(false, Ordering::Relaxed);
    match persist::save_atomic(path, &snapshot, keep_backup) {
        Ok(()) => {
            if let Ok(mut guard) = store.lock() {
                // Пока писали, могли прилететь новые правки — их не затираем.
                if guard.revision() == revision {
                    guard.mark_saved();
                }
            }
            // UI показывает статус сохранения по факту записи, а не «на глазок».
            let _ = app.emit("pwl://saved", revision);
        }
        Err(e) => {
            backup_pending.store(true, Ordering::Relaxed);
            let _ = app.emit("pwl://save-error", e.to_string());
        }
    }
}

/// Заглушка для не-Windows сборок: ядро работает как обычно, пароли не шифруются.
#[allow(dead_code)]
pub fn noop_protector() -> Arc<dyn Protector> {
    Arc::new(NoopProtector)
}