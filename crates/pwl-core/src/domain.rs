//! Домен и контракты обмена с UI. Всё, что пересекает границу процесса,
//! описано здесь: `Op` (что сделать), `Change` (что изменилось), `Bootstrap`
//! (полное состояние одним вызовом).
//!
//! Пароль в UI не попадает: наружу идёт `AccountView`, у него нет поля пароля.

use serde::{Deserialize, Serialize};

use crate::catalog;
use crate::ids::{now_millis, stable_hash};
use crate::secret::Secret;

pub const SCHEMA: u32 = 1;
pub const ART_VARIANTS: u8 = 5;
pub const GLYPH_VARIANTS: u8 = 20;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum Theme {
    #[default]
    Dark,
    Light,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Settings {
    pub theme: Theme,
    pub minimize_to_tray: bool,
    pub accepted: bool,
    /// Показывать диалог подтверждения перед удалением аккаунта.
    pub confirm_delete: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            theme: Theme::Dark,
            minimize_to_tray: false,
            accepted: false,
            confirm_delete: true,
        }
    }
}

/// Частичное обновление настроек: `None` = не менять.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct SettingsPatch {
    pub theme: Option<Theme>,
    pub minimize_to_tray: Option<bool>,
    pub accepted: Option<bool>,
    pub confirm_delete: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Account {
    pub id: String,
    pub login: String,
    pub secret: Secret,
    pub nick: String,
    pub auto_role: bool,
    /// Slug класса из `catalog`, а не русское имя.
    pub class: String,
    #[serde(default)]
    pub comment: String,
    #[serde(default)]
    pub created_at: u64,
}

impl Account {
    pub fn new(draft: AccountDraft, secret: Secret) -> Self {
        Self {
            id: crate::ids::new_id("acc"),
            login: draft.login.trim().to_string(),
            secret,
            nick: draft.nick.trim().to_string(),
            auto_role: draft.auto_role,
            class: catalog::normalize(&draft.class).to_string(),
            comment: draft.comment.trim().to_string(),
            created_at: now_millis(),
        }
    }

    pub fn view(&self) -> AccountView {
        AccountView {
            id: self.id.clone(),
            login: self.login.clone(),
            nick: self.nick.clone(),
            auto_role: self.auto_role,
            class: self.class.clone(),
            comment: self.comment.clone(),
            has_password: !self.secret.is_empty(),
            sprite_index: catalog::by_slug(&self.class).map(|c| c.sprite_index).unwrap_or(0),
        }
    }
}

/// Аккаунт в том виде, в котором его видит UI. Пароля тут нет — только флаг.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountView {
    pub id: String,
    pub login: String,
    pub nick: String,
    pub auto_role: bool,
    pub class: String,
    pub comment: String,
    pub has_password: bool,
    pub sprite_index: u16,
}

/// Форма аккаунта. `password: None` при редактировании = оставить прежний.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct AccountDraft {
    pub login: String,
    pub password: Option<String>,
    pub nick: String,
    pub auto_role: bool,
    pub class: String,
    pub comment: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Server {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub client_path: Option<String>,
    #[serde(default)]
    pub accounts: Vec<Account>,
    #[serde(default)]
    pub created_at: u64,
}

impl Server {
    pub fn new(name: &str, client_path: Option<String>) -> Self {
        Self {
            id: crate::ids::new_id("srv"),
            name: name.trim().to_string(),
            client_path: client_path.filter(|p| !p.trim().is_empty()),
            accounts: Vec::new(),
            created_at: now_millis(),
        }
    }

    pub fn view(&self) -> ServerView {
        let h = stable_hash(&self.id);
        ServerView {
            id: self.id.clone(),
            name: self.name.clone(),
            client_path: self.client_path.clone(),
            art: (h % ART_VARIANTS as u64) as u8,
            glyph: ((h >> 11) % GLYPH_VARIANTS as u64) as u8,
            accounts: self.accounts.iter().map(Account::view).collect(),
        }
    }

    pub fn position(&self, account_id: &str) -> Option<usize> {
        self.accounts.iter().position(|a| a.id == account_id)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ServerView {
    pub id: String,
    pub name: String,
    pub client_path: Option<String>,
    /// Эмблема выводится из id: одна и та же при каждой перерисовке.
    pub art: u8,
    pub glyph: u8,
    pub accounts: Vec<AccountView>,
}

/// Шапка сервера без аккаунтов: переименование или смена пути к клиенту
/// не должны гонять по IPC весь список аккаунтов.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ServerMeta {
    pub id: String,
    pub name: String,
    pub client_path: Option<String>,
    pub art: u8,
    pub glyph: u8,
    pub account_count: usize,
}

impl Server {
    pub fn meta(&self) -> ServerMeta {
        let h = stable_hash(&self.id);
        ServerMeta {
            id: self.id.clone(),
            name: self.name.clone(),
            client_path: self.client_path.clone(),
            art: (h % ART_VARIANTS as u64) as u8,
            glyph: ((h >> 11) % GLYPH_VARIANTS as u64) as u8,
            account_count: self.accounts.len(),
        }
    }
}

/// То, что лежит на диске.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub schema: u32,
    #[serde(default)]
    pub settings: Settings,
    #[serde(default)]
    pub servers: Vec<Server>,
}

impl Default for Snapshot {
    fn default() -> Self {
        Self { schema: SCHEMA, settings: Settings::default(), servers: Vec::new() }
    }
}

/// Одно сообщение UI на старте вместо цепочки запросов.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Bootstrap {
    pub version: &'static str,
    pub schema: u32,
    pub settings: Settings,
    pub servers: Vec<ServerView>,
    pub races: &'static [catalog::RaceInfo],
    pub classes: &'static [catalog::ClassInfo],
    /// Пароли зашифрованы DPAPI (на Windows — true).
    pub secrets_secure: bool,
    pub migration: Option<crate::migrate::MigrationReport>,
}

/// Точечный патч. UI применяет его к своему зеркалу без полного ререндера.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase", rename_all_fields = "camelCase")]
pub enum Change {
    Settings { settings: Settings },
    ServerAdded { server: ServerView },
    ServerUpdated { meta: ServerMeta },
    ServerRemoved { id: String },
    AccountAdded { server_id: String, account: AccountView },
    AccountUpdated { server_id: String, account: AccountView },
    AccountRemoved { server_id: String, id: String },
    AccountMoved { server_id: String, id: String, to: usize },
}

/// Единственная точка записи. Один IPC-вызов на любое действие.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "op", rename_all = "camelCase", rename_all_fields = "camelCase")]
pub enum Op {
    AddServer { name: String, client_path: Option<String> },
    RenameServer { id: String, name: String },
    SetClientPath { id: String, path: Option<String> },
    /// `keep_accounts = true` — аккаунты остаются в библиотеке (старая версия
    /// складывала их в `kept_accounts`, откуда их нельзя было достать).
    DeleteServer { id: String, keep_accounts: bool },
    AddAccount { server_id: String, draft: AccountDraft },
    UpdateAccount { server_id: String, id: String, draft: AccountDraft },
    DeleteAccount { server_id: String, id: String },
    MoveAccount { server_id: String, id: String, to: usize },
    SetSettings { patch: SettingsPatch },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn account_view_has_no_password_field() {
        let a = Account::new(
            AccountDraft { login: "u".into(), password: Some("hunter2".into()), ..Default::default() },
            Secret::Plain("hunter2".into()),
        );
        let json = serde_json::to_string(&a.view()).unwrap();
        assert!(!json.contains("hunter2"));
        assert!(!json.contains("secret"));
        assert!(json.contains("\"hasPassword\":true"));
    }

    #[test]
    fn emblem_is_deterministic() {
        let s = Server::new("RU-1", None);
        let (a, b) = (s.view(), s.view());
        assert_eq!((a.art, a.glyph), (b.art, b.glyph));
        assert!(a.art < ART_VARIANTS && a.glyph < GLYPH_VARIANTS);
    }

    #[test]
    fn op_roundtrip_from_json() {
        let op: Op = serde_json::from_str(
            r#"{"op":"addAccount","serverId":"srv_1","draft":{"login":"u","password":"p","class":"mag"}}"#,
        )
        .unwrap();
        match op {
            Op::AddAccount { server_id, draft } => {
                assert_eq!(server_id, "srv_1");
                assert_eq!(draft.password.as_deref(), Some("p"));
                assert!(!draft.auto_role);
            }
            _ => panic!("не тот вариант"),
        }
    }

    #[test]
    fn settings_patch_keeps_unset_fields() {
        let patch: SettingsPatch = serde_json::from_str(r#"{"theme":"light"}"#).unwrap();
        assert_eq!(patch.theme, Some(Theme::Light));
        assert_eq!(patch.minimize_to_tray, None);
    }
}