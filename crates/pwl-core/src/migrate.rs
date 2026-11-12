//! Миграция с формата v0.9 (Python): `config.json` + файл аккаунтов со случайным
//! числовым именем → один `library.json`.
//!
//! Что чинится по пути:
//! * класс «Маг» → стабильный slug `mag` (иконки больше не зависят от подписи);
//! * аккаунты получают стабильные id вместо индексов;
//! * `kept_accounts` (аккаунты «сохранённые» при удалении сервера, которые
//!   невозможно было достать) возвращаются в библиотеку отдельным сервером;
//! * пароли сразу шифруются, если платформа умеет;
//! * исходные файлы копируются в `backup-v0/` и не удаляются.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::catalog;
use crate::domain::{Account, AccountDraft, Server, Settings, Snapshot, Theme, SCHEMA};
use crate::error::{Error, Result};
use crate::ids::now_millis;
use crate::secret::Protector;

pub const BACKUP_DIR: &str = "backup-v0";

#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MigrationReport {
    pub servers: usize,
    pub accounts: usize,
    pub restored_accounts: usize,
    pub warnings: Vec<String>,
    pub backup_dir: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct LegacyConfig {
    #[serde(default)]
    accepted: bool,
    #[serde(default)]
    theme: Option<String>,
    #[serde(default)]
    minimize_to_tray: bool,
    #[serde(default)]
    accounts_file: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct LegacyAccount {
    #[serde(default)]
    login: String,
    #[serde(default)]
    password: String,
    #[serde(default)]
    nick: String,
    #[serde(default)]
    auto: bool,
    #[serde(default)]
    class: String,
    #[serde(default)]
    comment: String,
}

#[derive(Debug, Default, Deserialize)]
struct LegacyServer {
    #[serde(default)]
    name: String,
    #[serde(default)]
    path: String,
    #[serde(default)]
    accounts: Vec<LegacyAccount>,
}

#[derive(Debug, Default, Deserialize)]
struct LegacyData {
    #[serde(default)]
    servers: Vec<LegacyServer>,
    #[serde(default)]
    kept_accounts: std::collections::HashMap<String, Vec<LegacyAccount>>,
}

/// Есть ли в папке данные старого формата.
pub fn legacy_present(dir: &Path) -> bool {
    dir.join("config.json").is_file() || find_legacy_accounts_file(dir, None).is_some()
}

fn is_digits(stem: &str) -> bool {
    !stem.is_empty() && stem.len() <= 32 && stem.bytes().all(|b| b.is_ascii_digit())
}

/// Старая версия звала файл 7–15 случайными цифрами. Если путь в конфиге
/// потерян — ищем такой файл сами (берём самый свежий).
fn find_legacy_accounts_file(dir: &Path, remembered: Option<&str>) -> Option<PathBuf> {
    if let Some(p) = remembered {
        let path = PathBuf::from(p);
        if path.is_file() {
            return Some(path);
        }
        // Мог быть относительный путь или переезд папки.
        if let Some(name) = path.file_name() {
            let cand = dir.join(name);
            if cand.is_file() {
                return Some(cand);
            }
        }
    }
    let mut best: Option<(std::time::SystemTime, PathBuf)> = None;
    for entry in fs::read_dir(dir).ok()?.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
        if !is_digits(stem) {
            continue;
        }
        let mtime = entry
            .metadata()
            .and_then(|m| m.modified())
            .unwrap_or(std::time::SystemTime::UNIX_EPOCH);
        if best.as_ref().map(|(t, _)| mtime > *t).unwrap_or(true) {
            best = Some((mtime, path));
        }
    }
    best.map(|(_, p)| p)
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T> {
    let bytes = fs::read(path)?;
    serde_json::from_slice(&bytes).map_err(|e| Error::Corrupt(format!("{}: {e}", path.display())))
}

pub fn run(dir: &Path, protector: &dyn Protector) -> Result<(Snapshot, MigrationReport)> {
    let mut report = MigrationReport::default();
    let config_path = dir.join("config.json");
    let config: LegacyConfig = if config_path.is_file() {
        read_json(&config_path)?
    } else {
        report
            .warnings
            .push("config.json не найден — настройки взяты по умолчанию".into());
        LegacyConfig::default()
    };

    let accounts_file = find_legacy_accounts_file(dir, config.accounts_file.as_deref());
    let data: LegacyData = match &accounts_file {
        Some(p) => read_json(p)?,
        None => {
            report
                .warnings
                .push("Файл аккаунтов не найден — перенесены только настройки".into());
            LegacyData::default()
        }
    };

    let settings = Settings {
        theme: match config.theme.as_deref() {
            Some("light") => Theme::Light,
            _ => Theme::Dark,
        },
        minimize_to_tray: config.minimize_to_tray,
        accepted: config.accepted,
        confirm_delete: true,
    };

    let mut snapshot = Snapshot { schema: SCHEMA, settings, servers: Vec::new() };
    let mut used_names: HashSet<String> = HashSet::new();

    let convert = |name: &str,
                       path: &str,
                       accounts: &[LegacyAccount],
                       report: &mut MigrationReport,
                       used: &mut HashSet<String>|
     -> Server {
        let base = if name.trim().is_empty() { "Без названия" } else { name.trim() };
        let mut unique = base.to_string();
        let mut n = 2;
        while !used.insert(unique.to_lowercase()) {
            unique = format!("{base} ({n})");
            n += 1;
        }
        let mut server = Server::new(&unique, Some(path.to_string()));
        server.created_at = now_millis();
        for legacy in accounts {
            let class = match catalog::by_legacy_name(&legacy.class) {
                Some(c) => c.slug,
                None => {
                    if !legacy.class.trim().is_empty() {
                        report.warnings.push(format!(
                            "Неизвестный класс «{}» у аккаунта {} — заменён на «Воин»",
                            legacy.class, legacy.login
                        ));
                    }
                    catalog::DEFAULT_CLASS
                }
            };
            let secret = protector.protect(&legacy.password).unwrap_or_default();
            let account = Account::new(
                AccountDraft {
                    login: legacy.login.clone(),
                    password: None,
                    nick: legacy.nick.clone(),
                    auto_role: legacy.auto,
                    class: class.to_string(),
                    comment: legacy.comment.clone(),
                },
                secret,
            );
            server.accounts.push(account);
            report.accounts += 1;
        }
        server
    };

    for legacy in &data.servers {
        let server = convert(
            &legacy.name,
            &legacy.path,
            &legacy.accounts,
            &mut report,
            &mut used_names,
        );
        report.servers += 1;
        snapshot.servers.push(server);
    }

    // Возвращаем «сохранённые» аккаунты, которые старая версия прятала навсегда.
    let mut kept: Vec<(&String, &Vec<LegacyAccount>)> = data.kept_accounts.iter().collect();
    kept.sort_by(|a, b| a.0.cmp(b.0));
    for (name, accounts) in kept {
        if accounts.is_empty() {
            continue;
        }
        let before = report.accounts;
        let server = convert(
            &format!("{name} — аккаунты"),
            "",
            accounts,
            &mut report,
            &mut used_names,
        );
        report.restored_accounts += report.accounts - before;
        report.servers += 1;
        snapshot.servers.push(server);
    }

    // Копируем исходники, ничего не удаляя.
    let backup = dir.join(BACKUP_DIR);
    let mut copied = false;
    if fs::create_dir_all(&backup).is_ok() {
        if config_path.is_file() {
            copied |= fs::copy(&config_path, backup.join("config.json")).is_ok();
        }
        if let Some(p) = &accounts_file {
            if let Some(name) = p.file_name() {
                copied |= fs::copy(p, backup.join(name)).is_ok();
            }
        }
    }
    if copied {
        report.backup_dir = Some(backup.to_string_lossy().into_owned());
    }

    Ok((snapshot, report))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secret::NoopProtector;

    fn tmp_dir() -> PathBuf {
        let d = std::env::temp_dir().join(format!("pwl_migrate_{}", crate::ids::new_id("t")));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn write_legacy(dir: &Path) -> PathBuf {
        fs::write(
            dir.join("config.json"),
            r#"{"accepted":true,"theme":"light","minimize_to_tray":true,"launch_mode":"bat","accounts_file":"1234567.json"}"#,
        )
        .unwrap();
        let acc = dir.join("1234567.json");
        fs::write(
            &acc,
            r#"{"servers":[{"name":"RU-1","path":"C:\\Games\\elementclient.exe","accounts":[
                {"login":"u1","password":"p1","nick":"Nick1","auto":true,"class":"Маг","comment":"основа"},
                {"login":"u2","password":"p2","nick":"Nick2","auto":false,"class":"Жнец"}]}],
                "kept_accounts":{"Старый":[{"login":"u3","password":"p3","nick":"Nick3","class":"Дух крови"}]}}"#,
        )
        .unwrap();
        acc
    }

    #[test]
    fn detects_legacy_layout() {
        let d = tmp_dir();
        assert!(!legacy_present(&d));
        write_legacy(&d);
        assert!(legacy_present(&d));
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn migrates_servers_accounts_and_settings() {
        let d = tmp_dir();
        write_legacy(&d);
        let (snap, report) = run(&d, &NoopProtector).unwrap();
        assert_eq!(snap.schema, SCHEMA);
        assert!(snap.settings.accepted && snap.settings.minimize_to_tray);
        assert_eq!(snap.settings.theme, Theme::Light);
        assert_eq!(snap.servers.len(), 2, "второй — восстановленный архив");
        assert_eq!(snap.servers[0].name, "RU-1");
        assert_eq!(snap.servers[0].accounts.len(), 2);
        assert_eq!(snap.servers[0].accounts[0].class, "mag");
        assert_eq!(snap.servers[0].accounts[1].class, "kosa");
        assert!(snap.servers[0].accounts[0].auto_role);
        assert_eq!(report.accounts, 3);
        assert_eq!(report.restored_accounts, 1);
        assert!(report.warnings.is_empty());
        assert!(report.backup_dir.is_some());
        // оригиналы на месте
        assert!(d.join("config.json").is_file());
        assert!(d.join("1234567.json").is_file());
        assert!(d.join(BACKUP_DIR).join("1234567.json").is_file());
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn ids_are_unique_after_migration() {
        let d = tmp_dir();
        write_legacy(&d);
        let (snap, _) = run(&d, &NoopProtector).unwrap();
        let ids: HashSet<&str> = snap
            .servers
            .iter()
            .flat_map(|s| s.accounts.iter().map(|a| a.id.as_str()))
            .collect();
        assert_eq!(ids.len(), 3);
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn finds_accounts_file_without_config() {
        let d = tmp_dir();
        fs::write(
            d.join("987654321.json"),
            r#"{"servers":[{"name":"S","path":"","accounts":[]}]}"#,
        )
        .unwrap();
        let (snap, report) = run(&d, &NoopProtector).unwrap();
        assert_eq!(snap.servers.len(), 1);
        assert!(!report.warnings.is_empty(), "должно быть предупреждение про config");
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn unknown_class_warns_but_keeps_account() {
        let d = tmp_dir();
        fs::write(
            d.join("1111111.json"),
            r#"{"servers":[{"name":"S","path":"","accounts":[{"login":"u","password":"p","nick":"n","class":"Кто-то"}]}]}"#,
        )
        .unwrap();
        let (snap, report) = run(&d, &NoopProtector).unwrap();
        assert_eq!(snap.servers[0].accounts.len(), 1);
        assert_eq!(snap.servers[0].accounts[0].class, "var");
        assert!(report.warnings.iter().any(|w| w.contains("Кто-то")));
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn duplicate_names_are_deduplicated() {
        let d = tmp_dir();
        fs::write(
            d.join("2222222.json"),
            r#"{"servers":[{"name":"S","path":"","accounts":[]},{"name":"s","path":"","accounts":[]}]}"#,
        )
        .unwrap();
        let (snap, _) = run(&d, &NoopProtector).unwrap();
        assert_eq!(snap.servers[0].name, "S");
        assert_eq!(snap.servers[1].name, "s (2)");
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn corrupt_legacy_file_reports_error_instead_of_wiping() {
        let d = tmp_dir();
        fs::write(d.join("3333333.json"), b"{oops").unwrap();
        let err = run(&d, &NoopProtector).unwrap_err();
        assert_eq!(err.code(), "corrupt");
        fs::remove_dir_all(d).ok();
    }

    #[test]
    fn empty_dir_yields_empty_snapshot() {
        let d = tmp_dir();
        let (snap, report) = run(&d, &NoopProtector).unwrap();
        assert!(snap.servers.is_empty());
        assert_eq!(report.accounts, 0);
        fs::remove_dir_all(d).ok();
    }
}