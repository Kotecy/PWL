//! Тонкий RPC-слой. Вся логика — в `pwl-core`; здесь только разбор вызова,
//! мьютекс на время мутации и побочные эффекты окна/трея.
//!
//! Один вызов `apply` на любое действие, `bootstrap` отдаёт всё состояние
//! сразу — вместо цепочки запросов к диску, как в v0.9.

use std::sync::{Arc, MutexGuard};

use pwl_core::domain::{Bootstrap, Change, Op};
use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::state::AppState;
use crate::tray;

#[derive(Debug, Serialize)]
pub struct ApiError {
    pub code: String,
    pub message: String,
}

impl From<pwl_core::Error> for ApiError {
    fn from(e: pwl_core::Error) -> Self {
        Self { code: e.code().to_string(), message: e.to_string() }
    }
}

type ApiResult<T> = std::result::Result<T, ApiError>;

fn lock<'a>(state: &'a State<'_, Arc<AppState>>) -> ApiResult<MutexGuard<'a, pwl_core::Store>> {
    state
        .store
        .lock()
        .map_err(|_| ApiError { code: "poisoned".into(), message: "Внутренняя ошибка состояния".into() })
}

#[derive(Serialize)]
pub struct LaunchInfo {
    pub pid: u32,
    pub exe: String,
}

/// Всё состояние одним сообщением: настройки, серверы, каталог классов.
#[tauri::command]
pub fn bootstrap(state: State<'_, Arc<AppState>>) -> ApiResult<Bootstrap> {
    let store = lock(&state)?;
    Ok(store.bootstrap(state.take_migration()))
}

#[tauri::command]
pub fn apply(app: AppHandle, state: State<'_, Arc<AppState>>, op: Op) -> ApiResult<Change> {
    let change = {
        let mut store = lock(&state)?;
        store.apply(op)?
    };
    state.mark_dirty();
    if let Change::Settings { settings } = &change {
        tray::sync(&app, settings.minimize_to_tray);
    }
    Ok(change)
}

/// Пачка операций за один IPC и одну запись на диск.
#[tauri::command]
pub fn apply_batch(
    app: AppHandle,
    state: State<'_, Arc<AppState>>,
    ops: Vec<Op>,
) -> ApiResult<Vec<Change>> {
    let changes = {
        let mut store = lock(&state)?;
        store.apply_batch(ops)?
    };
    state.mark_dirty();
    if changes.iter().any(|c| matches!(c, Change::Settings { .. })) {
        let enabled = lock(&state)?.settings().minimize_to_tray;
        tray::sync(&app, enabled);
    }
    Ok(changes)
}

/// Запуск клиента: один CreateProcess, без .bat, cmd.exe и temp-файлов.
#[tauri::command]
pub fn launch(
    state: State<'_, Arc<AppState>>,
    server_id: String,
    account_id: String,
) -> ApiResult<LaunchInfo> {
    let plan = {
        let store = lock(&state)?;
        store.launch_plan(&server_id, &account_id)?
    };

    let mut cmd = std::process::Command::new(&plan.exe);
    cmd.args(&plan.args).current_dir(&plan.cwd);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;
        // Клиент должен пережить закрытие PWL.
        cmd.creation_flags(CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB);
    }
    let child = cmd.spawn().map_err(pwl_core::Error::Io)?;
    Ok(LaunchInfo { pid: child.id(), exe: plan.exe.to_string_lossy().into_owned() })
}

/// Системный диалог выбора elementclient.exe.
#[tauri::command]
pub fn pick_client(state: State<'_, Arc<AppState>>) -> ApiResult<Option<String>> {
    let start_dir = {
        let store = lock(&state)?;
        store
            .servers()
            .iter()
            .filter_map(|s| s.client_path.as_deref())
            .map(std::path::PathBuf::from)
            .find_map(|p| {
                let dir = if p.is_file() { p.parent()?.to_path_buf() } else { p };
                dir.is_dir().then_some(dir)
            })
    };

    let mut dialog = rfd::FileDialog::new()
        .set_title("Выберите elementclient.exe")
        .add_filter("Elementclient", &["exe"])
        .add_filter("Все файлы", &["*"]);
    if let Some(dir) = start_dir {
        dialog = dialog.set_directory(dir);
    }
    Ok(dialog.pick_file().map(|p| p.to_string_lossy().into_owned()))
}

#[tauri::command]
pub fn data_dir(state: State<'_, Arc<AppState>>) -> String {
    state.data_dir.to_string_lossy().into_owned()
}

/// Открыть папку данных в проводнике. Путь берётся из состояния, а не от интерфейса.
#[tauri::command]
pub fn open_data_dir(state: State<'_, Arc<AppState>>) -> Result<(), ApiError> {
    #[cfg(windows)]
    let program = "explorer.exe";
    #[cfg(target_os = "macos")]
    let program = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let program = "xdg-open";

    std::process::Command::new(program)
        .arg(&state.data_dir)
        .spawn()
        .map(|_| ())
        .map_err(|e| ApiError {
            code: "open_failed".into(),
            message: format!("Не удалось открыть папку: {e}"),
        })
}

#[tauri::command]
pub fn flush(state: State<'_, Arc<AppState>>) {
    state.flush_now();
}

fn main_window(app: &AppHandle) -> Option<tauri::WebviewWindow> {
    app.get_webview_window("main")
}

#[tauri::command]
pub fn win_minimize(app: AppHandle, state: State<'_, Arc<AppState>>) {
    let to_tray = lock(&state).map(|s| s.settings().minimize_to_tray).unwrap_or(false);
    if let Some(w) = main_window(&app) {
        if to_tray {
            let _ = w.hide();
        } else {
            let _ = w.minimize();
        }
    }
}

#[tauri::command]
pub fn win_toggle_maximize(app: AppHandle) {
    if let Some(w) = main_window(&app) {
        match w.is_maximized() {
            Ok(true) => {
                let _ = w.unmaximize();
            }
            _ => {
                let _ = w.maximize();
            }
        }
    }
}

#[tauri::command]
pub fn win_close(app: AppHandle, state: State<'_, Arc<AppState>>) {
    let to_tray = lock(&state).map(|s| s.settings().minimize_to_tray).unwrap_or(false);
    if to_tray {
        if let Some(w) = main_window(&app) {
            let _ = w.hide();
        }
        return;
    }
    quit(app, state);
}

/// Выход с гарантированной записью данных.
#[tauri::command]
pub fn quit(app: AppHandle, state: State<'_, Arc<AppState>>) {
    state.flush_blocking(std::time::Duration::from_secs(3));
    app.exit(0);
}