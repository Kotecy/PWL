//! Персистентность: один компактный JSON, атомарная замена, резервная копия
//! предыдущей версии. Никаких чтений на каждое действие — стор живёт в памяти.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::domain::Snapshot;
use crate::error::{Error, Result};

pub const LIBRARY_FILE: &str = "library.json";
pub const BACKUP_SUFFIX: &str = "bak";
pub const TMP_SUFFIX: &str = "tmp";

/// `%APPDATA%\PWL` на Windows, `~/.local/share/PWL` на остальных ОС.
pub fn default_data_dir() -> PathBuf {
    if let Some(appdata) = std::env::var_os("APPDATA") {
        return PathBuf::from(appdata).join("PWL");
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    home.join(".local").join("share").join("PWL")
}

pub fn library_path(dir: &Path) -> PathBuf {
    dir.join(LIBRARY_FILE)
}

fn backup_path(path: &Path) -> PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(".");
    s.push(BACKUP_SUFFIX);
    PathBuf::from(s)
}

fn tmp_path(path: &Path) -> PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(".");
    s.push(TMP_SUFFIX);
    PathBuf::from(s)
}

/// Отсутствующий файл — это `Ok(None)`, а битый — ошибка. Старая версия
/// путала эти случаи и молча отдавала пустую библиотеку, теряя данные.
pub fn load(path: &Path) -> Result<Option<Snapshot>> {
    match fs::read(path) {
        Ok(bytes) => {
            let snap: Snapshot = serde_json::from_slice(&bytes)
                .map_err(|e| Error::Corrupt(format!("{}: {e}", path.display())))?;
            Ok(Some(snap))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(Error::Io(e)),
    }
}

/// Загрузка с откатом на `.bak`. Возвращает снапшот и текст предупреждения,
/// если пришлось восстановиться из копии.
pub fn load_with_recovery(path: &Path) -> Result<(Snapshot, Option<String>)> {
    match load(path) {
        Ok(Some(s)) => Ok((s, None)),
        Ok(None) => Ok((Snapshot::default(), None)),
        Err(primary) => {
            let bak = backup_path(path);
            match load(&bak) {
                Ok(Some(s)) => Ok((
                    s,
                    Some(format!(
                        "Основной файл повреждён ({primary}). Загружена резервная копия."
                    )),
                )),
                _ => Err(primary),
            }
        }
    }
}

/// Атомарная запись: tmp → fsync → замена целевого файла.
/// `keep_backup` копирует предыдущую версию в `.bak` (достаточно раза за сессию).
pub fn save_atomic(path: &Path, snapshot: &Snapshot, keep_backup: bool) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    // Компактный JSON: примерно вдвое меньше indent=2 и заметно быстрее парсится.
    let bytes = serde_json::to_vec(snapshot)?;
    let tmp = tmp_path(path);
    {
        let mut f = fs::File::create(&tmp)?;
        f.write_all(&bytes)?;
        f.sync_all()?;
    }
    if keep_backup && path.is_file() {
        // Копия делается до замены и не мешает атомарности самой замены.
        let _ = fs::copy(path, backup_path(path));
    }
    match atomic_replace(&tmp, path) {
        Ok(()) => Ok(()),
        Err(e) => {
            let _ = fs::remove_file(&tmp);
            Err(Error::Io(e))
        }
    }
}

#[cfg(not(windows))]
fn atomic_replace(from: &Path, to: &Path) -> std::io::Result<()> {
    fs::rename(from, to)
}

/// На Windows `rename` не перезаписывает существующий файл, а `remove+rename`
/// не атомарен. Нужен `MoveFileExW` с `MOVEFILE_REPLACE_EXISTING`.
#[cfg(windows)]
fn atomic_replace(from: &Path, to: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;

    fn wide(p: &Path) -> Vec<u16> {
        p.as_os_str().encode_wide().chain(std::iter::once(0)).collect()
    }
    extern "system" {
        fn MoveFileExW(from: *const u16, to: *const u16, flags: u32) -> i32;
    }
    const MOVEFILE_REPLACE_EXISTING: u32 = 0x1;
    const MOVEFILE_WRITE_THROUGH: u32 = 0x8;
    let ok = unsafe {
        MoveFileExW(
            wide(from).as_ptr(),
            wide(to).as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if ok == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{Server, Settings, Theme};

    fn tmp_dir() -> PathBuf {
        let d = std::env::temp_dir().join(format!("pwl_persist_{}", crate::ids::new_id("t")));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn snapshot(n: usize) -> Snapshot {
        let mut s = Snapshot::default();
        s.settings.theme = Theme::Light;
        for i in 0..n {
            s.servers.push(Server::new(&format!("S{i}"), None));
        }
        s
    }

    #[test]
    fn missing_file_is_none_not_empty_default() {
        let d = tmp_dir();
        assert!(load(&d.join("nope.json")).unwrap().is_none());
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn corrupt_file_is_error() {
        let d = tmp_dir();
        let p = d.join("bad.json");
        fs::write(&p, b"{ not json").unwrap();
        assert_eq!(load(&p).unwrap_err().code(), "corrupt");
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn save_load_roundtrip() {
        let d = tmp_dir();
        let p = library_path(&d);
        let snap = snapshot(3);
        save_atomic(&p, &snap, false).unwrap();
        assert_eq!(load(&p).unwrap().unwrap(), snap);
        assert!(!p.with_extension("json.tmp").exists(), "tmp не должен оставаться");
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn backup_is_written_and_used_for_recovery() {
        let d = tmp_dir();
        let p = library_path(&d);
        save_atomic(&p, &snapshot(1), false).unwrap();
        save_atomic(&p, &snapshot(2), true).unwrap();
        assert!(backup_path(&p).is_file());
        // Ломаем основной файл — должны подняться из копии.
        fs::write(&p, b"broken").unwrap();
        let (snap, warn) = load_with_recovery(&p).unwrap();
        assert_eq!(snap.servers.len(), 1);
        assert!(warn.is_some());
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn repeated_saves_do_not_leak_tmp_files() {
        let d = tmp_dir();
        let p = library_path(&d);
        for i in 0..20 {
            save_atomic(&p, &snapshot(i % 4), false).unwrap();
        }
        let leftovers: Vec<_> = fs::read_dir(&d)
            .unwrap()
            .flatten()
            .filter(|e| e.file_name().to_string_lossy().ends_with(".tmp"))
            .collect();
        assert!(leftovers.is_empty());
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn compact_json_is_smaller_than_indented() {
        let snap = snapshot(20);
        let compact = serde_json::to_vec(&snap).unwrap().len();
        let pretty = serde_json::to_vec_pretty(&snap).unwrap().len();
        assert!(compact < pretty);
    }

    #[test]
    fn settings_survive_roundtrip() {
        let d = tmp_dir();
        let p = library_path(&d);
        let mut snap = snapshot(0);
        snap.settings = Settings { minimize_to_tray: true, accepted: true, ..Default::default() };
        save_atomic(&p, &snap, false).unwrap();
        let back = load(&p).unwrap().unwrap();
        assert!(back.settings.minimize_to_tray && back.settings.accepted);
        fs::remove_dir_all(d).ok();
    }
}