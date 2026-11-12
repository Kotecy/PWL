//! Стор — единственный владелец состояния. Чтение из памяти, запись через
//! `persist` (атомарно и отложенно, снаружи). Мутации возвращают `Change`,
//! чтобы UI обновлял ровно один узел, а не перерисовывал экран.

use std::sync::Arc;

use crate::domain::{
    Account, AccountDraft, Bootstrap, Change, Op, Server, Settings, SettingsPatch, Snapshot, SCHEMA,
};
use crate::error::{Error, Result};
use crate::launch::{self, LaunchPlan};
use crate::migrate::MigrationReport;
use crate::secret::Protector;

pub struct Store {
    snapshot: Snapshot,
    protector: Arc<dyn Protector>,
    dirty: bool,
    revision: u64,
}

impl Store {
    pub fn new(snapshot: Snapshot, protector: Arc<dyn Protector>) -> Self {
        Self { snapshot, protector, dirty: false, revision: 0 }
    }

    pub fn settings(&self) -> &Settings {
        &self.snapshot.settings
    }

    pub fn servers(&self) -> &[Server] {
        &self.snapshot.servers
    }

    pub fn snapshot(&self) -> &Snapshot {
        &self.snapshot
    }

    pub fn into_snapshot(self) -> Snapshot {
        self.snapshot
    }

    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    pub fn revision(&self) -> u64 {
        self.revision
    }

    /// Вызывается после успешной записи на диск.
    pub fn mark_saved(&mut self) {
        self.dirty = false;
    }

    pub fn bootstrap(&self, migration: Option<MigrationReport>) -> Bootstrap {
        Bootstrap {
            version: crate::APP_VERSION,
            schema: SCHEMA,
            settings: self.snapshot.settings.clone(),
            servers: self.snapshot.servers.iter().map(Server::view).collect(),
            races: crate::catalog::RACES,
            classes: crate::catalog::CLASSES,
            secrets_secure: self.protector.is_secure(),
            migration,
        }
    }

    fn server_mut(&mut self, id: &str) -> Result<&mut Server> {
        self.snapshot
            .servers
            .iter_mut()
            .find(|s| s.id == id)
            .ok_or(Error::NotFound("Сервер"))
    }

    fn touch(&mut self) {
        self.dirty = true;
        self.revision += 1;
    }

    fn name_taken(&self, name: &str, except: Option<&str>) -> bool {
        let n = name.trim();
        self.snapshot
            .servers
            .iter()
            .any(|s| Some(s.id.as_str()) != except && s.name.trim().eq_ignore_ascii_case(n))
    }

    /// Применить одну операцию. Ошибка не меняет состояние.
    pub fn apply(&mut self, op: Op) -> Result<Change> {
        let change = match op {
            Op::AddServer { name, client_path } => {
                let name = name.trim();
                if name.is_empty() {
                    return Err(Error::Validation("Введите название сервера".into()));
                }
                if self.name_taken(name, None) {
                    return Err(Error::Validation("Сервер с таким названием уже есть".into()));
                }
                let server = Server::new(name, client_path);
                let view = server.view();
                self.snapshot.servers.push(server);
                Change::ServerAdded { server: view }
            }

            Op::RenameServer { id, name } => {
                let name = name.trim();
                if name.is_empty() {
                    return Err(Error::Validation("Введите название сервера".into()));
                }
                if self.name_taken(name, Some(&id)) {
                    return Err(Error::Validation("Сервер с таким названием уже есть".into()));
                }
                let s = self.server_mut(&id)?;
                s.name = name.to_string();
                Change::ServerUpdated { meta: s.meta() }
            }

            Op::SetClientPath { id, path } => {
                let s = self.server_mut(&id)?;
                s.client_path = path.filter(|p| !p.trim().is_empty());
                Change::ServerUpdated { meta: s.meta() }
            }

            Op::DeleteServer { id, keep_accounts } => {
                let pos = self
                    .snapshot
                    .servers
                    .iter()
                    .position(|s| s.id == id)
                    .ok_or(Error::NotFound("Сервер"))?;
                let removed = self.snapshot.servers.remove(pos);
                if keep_accounts && !removed.accounts.is_empty() {
                    // Старая версия прятала такие аккаунты в `kept_accounts`,
                    // откуда их невозможно было достать. Теперь это обычный
                    // сервер-архив: аккаунты видны и ими можно пользоваться.
                    let archive_name = format!("{} — аккаунты", removed.name);
                    if let Some(existing) = self
                        .snapshot
                        .servers
                        .iter_mut()
                        .find(|s| s.name.eq_ignore_ascii_case(&archive_name))
                    {
                        existing.accounts.extend(removed.accounts);
                    } else {
                        let mut archive = Server::new(&archive_name, None);
                        archive.accounts = removed.accounts;
                        self.snapshot.servers.push(archive);
                    }
                }
                Change::ServerRemoved { id }
            }

            Op::AddAccount { server_id, draft } => {
                validate_draft(&draft, true)?;
                let secret = self
                    .protector
                    .protect(draft.password.as_deref().unwrap_or(""))?;
                let account = Account::new(draft, secret);
                let view = account.view();
                self.server_mut(&server_id)?.accounts.push(account);
                Change::AccountAdded { server_id, account: view }
            }

            Op::UpdateAccount { server_id, id, draft } => {
                validate_draft(&draft, false)?;
                // Шифруем до мутации: если protect упадёт, состояние не изменится.
                let new_secret = match draft.password.as_deref() {
                    Some(pw) => Some(self.protector.protect(pw)?),
                    None => None,
                };
                let s = self.server_mut(&server_id)?;
                let idx = s.position(&id).ok_or(Error::NotFound("Аккаунт"))?;
                let current = &mut s.accounts[idx];
                current.login = draft.login.trim().to_string();
                current.nick = draft.nick.trim().to_string();
                current.auto_role = draft.auto_role;
                current.class = crate::catalog::normalize(&draft.class).to_string();
                current.comment = draft.comment.trim().to_string();
                // None = поле пароля не трогали, оставляем прежний.
                if let Some(secret) = new_secret {
                    current.secret = secret;
                }
                Change::AccountUpdated { server_id, account: current.view() }
            }

            Op::DeleteAccount { server_id, id } => {
                let s = self.server_mut(&server_id)?;
                let idx = s.position(&id).ok_or(Error::NotFound("Аккаунт"))?;
                s.accounts.remove(idx);
                Change::AccountRemoved { server_id, id }
            }

            Op::MoveAccount { server_id, id, to } => {
                let s = self.server_mut(&server_id)?;
                let from = s.position(&id).ok_or(Error::NotFound("Аккаунт"))?;
                let to = to.min(s.accounts.len().saturating_sub(1));
                if from != to {
                    let item = s.accounts.remove(from);
                    s.accounts.insert(to, item);
                }
                Change::AccountMoved { server_id, id, to }
            }

            Op::SetSettings { patch } => {
                apply_settings(&mut self.snapshot.settings, patch);
                Change::Settings { settings: self.snapshot.settings.clone() }
            }
        };
        self.touch();
        Ok(change)
    }

    /// Пачка операций за один вызов: одна запись на диск вместо N.
    pub fn apply_batch(&mut self, ops: Vec<Op>) -> Result<Vec<Change>> {
        let mut out = Vec::with_capacity(ops.len());
        for op in ops {
            out.push(self.apply(op)?);
        }
        Ok(out)
    }

    /// План запуска игры. Пароль раскрывается здесь и наружу не отдаётся.
    pub fn launch_plan(&self, server_id: &str, account_id: &str) -> Result<LaunchPlan> {
        let server = self
            .snapshot
            .servers
            .iter()
            .find(|s| s.id == server_id)
            .ok_or(Error::NotFound("Сервер"))?;
        let account = server
            .accounts
            .iter()
            .find(|a| a.id == account_id)
            .ok_or(Error::NotFound("Аккаунт"))?;
        let password = self.protector.reveal(&account.secret)?;
        launch::plan(server, account, &password)
    }

    /// Зашифровать всё, что ещё лежит открытым текстом (после миграции).
    pub fn secure_secrets(&mut self) -> Result<usize> {
        if !self.protector.is_secure() {
            return Ok(0);
        }
        let mut n = 0;
        for server in &mut self.snapshot.servers {
            for account in &mut server.accounts {
                if let crate::secret::Secret::Plain(p) = &account.secret {
                    let p = p.clone();
                    account.secret = self.protector.protect(&p)?;
                    n += 1;
                }
            }
        }
        if n > 0 {
            self.touch();
        }
        Ok(n)
    }
}

fn validate_draft(draft: &AccountDraft, _is_new: bool) -> Result<()> {
    if draft.login.trim().is_empty() {
        return Err(Error::Validation("Введите логин аккаунта".into()));
    }
    if draft.auto_role && draft.nick.trim().is_empty() {
        return Err(Error::Validation(
            "Для автовхода нужен ник персонажа".into(),
        ));
    }
    Ok(())
}

fn apply_settings(s: &mut Settings, patch: SettingsPatch) {
    if let Some(v) = patch.theme {
        s.theme = v;
    }
    if let Some(v) = patch.minimize_to_tray {
        s.minimize_to_tray = v;
    }
    if let Some(v) = patch.accepted {
        s.accepted = v;
    }
    if let Some(v) = patch.confirm_delete {
        s.confirm_delete = v;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secret::NoopProtector;

    fn store() -> Store {
        Store::new(Snapshot::default(), Arc::new(NoopProtector))
    }

    fn draft(login: &str) -> AccountDraft {
        AccountDraft {
            login: login.into(),
            password: Some("pw".into()),
            nick: "Nick".into(),
            class: "mag".into(),
            ..Default::default()
        }
    }

    fn server_id(s: &Store) -> String {
        s.servers()[0].id.clone()
    }

    #[test]
    fn add_server_and_account() {
        let mut s = store();
        assert!(!s.is_dirty());
        s.apply(Op::AddServer { name: " RU-1 ".into(), client_path: None }).unwrap();
        assert_eq!(s.servers()[0].name, "RU-1");
        let sid = server_id(&s);
        let ch = s.apply(Op::AddAccount { server_id: sid.clone(), draft: draft("u1") }).unwrap();
        assert!(matches!(ch, Change::AccountAdded { .. }));
        assert_eq!(s.servers()[0].accounts.len(), 1);
        assert!(s.is_dirty());
        s.mark_saved();
        assert!(!s.is_dirty());
    }

    #[test]
    fn duplicate_name_rejected_case_insensitively() {
        let mut s = store();
        s.apply(Op::AddServer { name: "RU-1".into(), client_path: None }).unwrap();
        let err = s.apply(Op::AddServer { name: "ru-1".into(), client_path: None }).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert_eq!(s.servers().len(), 1);
    }

    #[test]
    fn empty_name_rejected() {
        let mut s = store();
        assert!(s.apply(Op::AddServer { name: "   ".into(), client_path: None }).is_err());
        assert!(!s.is_dirty(), "ошибка не должна помечать стор грязным");
    }

    #[test]
    fn ids_survive_reorder() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        for i in 0..5 {
            s.apply(Op::AddAccount { server_id: sid.clone(), draft: draft(&format!("u{i}")) }).unwrap();
        }
        let ids: Vec<String> = s.servers()[0].accounts.iter().map(|a| a.id.clone()).collect();
        // Перетаскиваем последний в начало и редактируем «первый» —
        // правка должна попасть именно в перетащенный аккаунт.
        s.apply(Op::MoveAccount { server_id: sid.clone(), id: ids[4].clone(), to: 0 }).unwrap();
        let mut d = draft("edited");
        d.password = None;
        s.apply(Op::UpdateAccount { server_id: sid.clone(), id: ids[4].clone(), draft: d }).unwrap();
        let accs = &s.servers()[0].accounts;
        assert_eq!(accs[0].id, ids[4]);
        assert_eq!(accs[0].login, "edited");
        assert_eq!(accs[1].id, ids[0]);
        // пароль не затёрт пустым полем
        assert_eq!(accs[0].secret, crate::secret::Secret::Plain("pw".into()));
    }

    #[test]
    fn move_clamps_out_of_range() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        for i in 0..3 {
            s.apply(Op::AddAccount { server_id: sid.clone(), draft: draft(&format!("u{i}")) }).unwrap();
        }
        let first = s.servers()[0].accounts[0].id.clone();
        s.apply(Op::MoveAccount { server_id: sid.clone(), id: first.clone(), to: 999 }).unwrap();
        assert_eq!(s.servers()[0].accounts.last().unwrap().id, first);
    }

    #[test]
    fn delete_server_keeps_accounts_reachable() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        s.apply(Op::AddAccount { server_id: sid.clone(), draft: draft("u1") }).unwrap();
        s.apply(Op::DeleteServer { id: sid, keep_accounts: true }).unwrap();
        assert_eq!(s.servers().len(), 1, "аккаунты должны остаться видимыми");
        assert_eq!(s.servers()[0].accounts.len(), 1);
        assert!(s.servers()[0].name.contains("аккаунты"));
    }

    #[test]
    fn delete_server_drops_accounts_when_asked() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        s.apply(Op::AddAccount { server_id: sid.clone(), draft: draft("u1") }).unwrap();
        s.apply(Op::DeleteServer { id: sid, keep_accounts: false }).unwrap();
        assert!(s.servers().is_empty());
    }

    #[test]
    fn auto_role_requires_nick() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        let mut d = draft("u1");
        d.auto_role = true;
        d.nick = "  ".into();
        assert!(s.apply(Op::AddAccount { server_id: sid, draft: d }).is_err());
    }

    #[test]
    fn batch_produces_one_dirty_flag() {
        let mut s = store();
        s.apply(Op::AddServer { name: "S".into(), client_path: None }).unwrap();
        let sid = server_id(&s);
        s.mark_saved();
        let ops: Vec<Op> = (0..50)
            .map(|i| Op::AddAccount { server_id: sid.clone(), draft: draft(&format!("u{i}")) })
            .collect();
        let changes = s.apply_batch(ops).unwrap();
        assert_eq!(changes.len(), 50);
        assert_eq!(s.revision(), 51);
        assert!(s.is_dirty());
    }

    #[test]
    fn settings_patch_is_partial() {
        let mut s = store();
        s.apply(Op::SetSettings {
            patch: SettingsPatch { theme: Some(crate::domain::Theme::Light), ..Default::default() },
        })
        .unwrap();
        assert_eq!(s.settings().theme, crate::domain::Theme::Light);
        assert!(s.settings().confirm_delete, "не заданные поля не трогаем");
    }

    #[test]
    fn unknown_ids_are_errors_not_panics() {
        let mut s = store();
        assert!(s.apply(Op::DeleteAccount { server_id: "nope".into(), id: "nope".into() }).is_err());
        assert!(s.apply(Op::MoveAccount { server_id: "nope".into(), id: "x".into(), to: 0 }).is_err());
        assert!(s.launch_plan("nope", "nope").is_err());
    }
}