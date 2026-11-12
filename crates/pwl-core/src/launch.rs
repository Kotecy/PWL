//! Планирование запуска клиента. Раньше на каждый вход создавался .bat в
//! cp1251, поднимался `cmd.exe`, менялась кодовая страница и только потом
//! `start`. Теперь — один `CreateProcess` с готовым argv: ноль файлов,
//! ноль лишних процессов, ошибка возвращается в UI, а не глотается.

use std::path::{Path, PathBuf};

use crate::domain::{Account, Server};
use crate::error::{Error, Result};

pub const CLIENT_EXE: &str = "elementclient.exe";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LaunchPlan {
    pub exe: PathBuf,
    pub cwd: PathBuf,
    pub args: Vec<String>,
}

/// Путь может указывать как на сам exe, так и на папку клиента.
pub fn resolve_client(raw: &str) -> Result<PathBuf> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err(Error::ClientMissing("Путь к Elementclient не задан".into()));
    }
    let p = Path::new(trimmed);
    if p.is_file() {
        return Ok(p.to_path_buf());
    }
    if p.is_dir() {
        let direct = p.join(CLIENT_EXE);
        if direct.is_file() {
            return Ok(direct);
        }
        // Регистр имени файла на диске может отличаться.
        if let Ok(entries) = std::fs::read_dir(p) {
            for entry in entries.flatten() {
                if entry.file_name().to_string_lossy().eq_ignore_ascii_case(CLIENT_EXE) {
                    let cand = entry.path();
                    if cand.is_file() {
                        return Ok(cand);
                    }
                }
            }
        }
        return Err(Error::ClientMissing(format!(
            "{CLIENT_EXE} не найден в папке {}",
            p.display()
        )));
    }
    Err(Error::ClientMissing(format!("Путь не существует: {trimmed}")))
}

/// Аргументы клиента. Каждый — один токен argv, поэтому пробелы внутри
/// значения больше не рвут командную строку (в .bat-версии рвали).
pub fn build_args(login: &str, password: &str, nick: &str, auto_role: bool) -> Vec<String> {
    let mut args = vec!["startbypatcher".to_string(), "nocheck".to_string()];
    if !login.is_empty() {
        args.push(format!("user:{login}"));
    }
    if !password.is_empty() {
        args.push(format!("pwd:{password}"));
    }
    if auto_role && !nick.is_empty() {
        args.push(format!("role:{nick}"));
    }
    args
}

fn check_token(value: &str, field: &str) -> Result<()> {
    if value.chars().any(|c| c == '"' || c == '\0' || c == '\n' || c == '\r') {
        return Err(Error::Validation(format!(
            "{field}: кавычки и переводы строк недопустимы"
        )));
    }
    Ok(())
}

pub fn plan(server: &Server, account: &Account, password: &str) -> Result<LaunchPlan> {
    let raw = server.client_path.as_deref().unwrap_or("");
    let exe = resolve_client(raw)?;
    let cwd = exe.parent().map(Path::to_path_buf).unwrap_or_else(|| PathBuf::from("."));
    check_token(&account.login, "Логин")?;
    check_token(password, "Пароль")?;
    check_token(&account.nick, "Ник")?;
    let args = build_args(&account.login, password, &account.nick, account.auto_role);
    Ok(LaunchPlan { exe, cwd, args })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::AccountDraft;
    use crate::secret::Secret;

    fn account(nick: &str, auto: bool) -> Account {
        Account::new(
            AccountDraft {
                login: "user".into(),
                nick: nick.into(),
                auto_role: auto,
                class: "mag".into(),
                ..Default::default()
            },
            Secret::Plain("pw".into()),
        )
    }

    #[test]
    fn args_match_legacy_order() {
        assert_eq!(
            build_args("user", "pw", "Nick", true),
            vec!["startbypatcher", "nocheck", "user:user", "pwd:pw", "role:Nick"]
        );
    }

    #[test]
    fn no_role_without_autologin() {
        assert_eq!(
            build_args("user", "pw", "Nick", false),
            vec!["startbypatcher", "nocheck", "user:user", "pwd:pw"]
        );
    }

    #[test]
    fn empty_password_is_skipped() {
        assert_eq!(build_args("user", "", "", true), vec!["startbypatcher", "nocheck", "user:user"]);
    }

    #[test]
    fn spaces_stay_inside_one_token() {
        let args = build_args("user", "p w", "Two Words", true);
        assert_eq!(args[3], "pwd:p w");
        assert_eq!(args[4], "role:Two Words");
        assert_eq!(args.len(), 5, "пробел не должен порождать лишний аргумент");
    }

    #[test]
    fn missing_path_is_client_missing() {
        let s = Server::new("S", None);
        let err = plan(&s, &account("N", true), "pw").unwrap_err();
        assert_eq!(err.code(), "clientMissing");
    }

    #[test]
    fn resolves_exe_and_directory() {
        let dir = std::env::temp_dir().join(format!("pwl_launch_test_{}", crate::ids::new_id("t")));
        std::fs::create_dir_all(&dir).unwrap();
        let exe = dir.join(CLIENT_EXE);
        std::fs::write(&exe, b"stub").unwrap();

        let from_file = resolve_client(exe.to_str().unwrap()).unwrap();
        let from_dir = resolve_client(dir.to_str().unwrap()).unwrap();
        assert_eq!(from_file, from_dir);

        let s = Server::new("S", Some(dir.to_string_lossy().into_owned()));
        let p = plan(&s, &account("N", true), "pw").unwrap();
        assert_eq!(p.exe, exe);
        assert_eq!(p.cwd, dir);
        assert_eq!(p.args.len(), 5);

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn quotes_are_rejected() {
        let dir = std::env::temp_dir().join(format!("pwl_launch_bad_{}", crate::ids::new_id("t")));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join(CLIENT_EXE), b"stub").unwrap();
        let s = Server::new("S", Some(dir.to_string_lossy().into_owned()));
        let err = plan(&s, &account("Ni\"ck", true), "pw").unwrap_err();
        assert_eq!(err.code(), "validation");
        std::fs::remove_dir_all(&dir).ok();
    }
}