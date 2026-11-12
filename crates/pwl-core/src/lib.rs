//! Ядро PWL. Ни GUI, ни платформенных зависимостей — только домен, хранилище,
//! миграция и планирование запуска. Всё, что здесь есть, тестируется на любой ОС.
//!
//! Правила слоя:
//! * чтение состояния — из памяти, ноль обращений к диску;
//! * запись — атомарная, отложенная, целиком один раз на пачку правок;
//! * пароль никогда не покидает бэкенд (в UI уходит `AccountView` без него);
//! * идентичность аккаунта — стабильный id, а не индекс в массиве.

pub mod catalog;
pub mod domain;
pub mod error;
pub mod flush;
pub mod ids;
pub mod launch;
pub mod migrate;
pub mod persist;
pub mod secret;
pub mod store;

pub use domain::{
    Account, AccountDraft, AccountView, Bootstrap, Change, Op, Server, ServerMeta, ServerView, Settings,
    SettingsPatch, Snapshot, Theme, SCHEMA,
};
pub use error::{Error, Result};
pub use launch::LaunchPlan;
pub use secret::{NoopProtector, Protector, Secret};
pub use store::Store;

/// Версия приложения. Одна на весь проект, UI получает её из `bootstrap`.
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const APP_TITLE: &str = "PWL by Kotecy";