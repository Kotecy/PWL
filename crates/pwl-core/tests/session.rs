//! Полный цикл: старые данные → миграция → работа → запись → перезапуск.

use std::fs;
use std::sync::Arc;

use pwl_core::domain::{AccountDraft, Op, SettingsPatch, Theme};
use pwl_core::{migrate, persist, NoopProtector, Store};

fn tmp_dir(tag: &str) -> std::path::PathBuf {
    let d = std::env::temp_dir().join(format!("pwl_it_{tag}_{}", pwl_core::ids::new_id("t")));
    fs::create_dir_all(&d).unwrap();
    d
}

#[test]
fn legacy_library_survives_full_session() {
    let dir = tmp_dir("session");
    fs::write(
        dir.join("config.json"),
        r#"{"accepted":true,"theme":"light","minimize_to_tray":true,"accounts_file":"5551234.json"}"#,
    )
    .unwrap();
    fs::write(
        dir.join("5551234.json"),
        r#"{"servers":[{"name":"RU-1","path":"","accounts":[
            {"login":"a","password":"pa","nick":"Alpha","auto":true,"class":"Убийца"},
            {"login":"b","password":"pb","nick":"Beta","auto":false,"class":"Жрец","comment":"твин"}]}],
            "kept_accounts":{"Забытый":[{"login":"c","password":"pc","nick":"Gamma","class":"Бард"}]}}"#,
    )
    .unwrap();

    // 1. Первый запуск новой версии: миграция.
    assert!(migrate::legacy_present(&dir));
    let (snapshot, report) = migrate::run(&dir, &NoopProtector).unwrap();
    assert_eq!(report.accounts, 3);
    assert_eq!(report.restored_accounts, 1);
    let path = persist::library_path(&dir);
    persist::save_atomic(&path, &snapshot, false).unwrap();

    // 2. Работаем: правим, перетаскиваем, добавляем, меняем настройки.
    let mut store = Store::new(snapshot, Arc::new(NoopProtector));
    let sid = store.servers()[0].id.clone();
    let first = store.servers()[0].accounts[0].id.clone();
    store
        .apply(Op::SetClientPath { id: sid.clone(), path: Some("/games/pw".into()) })
        .unwrap();
    store
        .apply(Op::MoveAccount { server_id: sid.clone(), id: first.clone(), to: 1 })
        .unwrap();
    store
        .apply(Op::UpdateAccount {
            server_id: sid.clone(),
            id: first.clone(),
            draft: AccountDraft {
                login: "a".into(),
                password: None, // поле пароля не трогали
                nick: "Alpha2".into(),
                auto_role: true,
                class: "sin".into(),
                comment: String::new(),
            },
        })
        .unwrap();
    store
        .apply(Op::AddAccount {
            server_id: sid.clone(),
            draft: AccountDraft {
                login: "d".into(),
                password: Some("pd".into()),
                nick: "Delta".into(),
                class: "kosa".into(),
                ..Default::default()
            },
        })
        .unwrap();
    store
        .apply(Op::SetSettings {
            patch: SettingsPatch { theme: Some(Theme::Dark), ..Default::default() },
        })
        .unwrap();

    // Одна запись на всю пачку правок.
    assert!(store.is_dirty());
    persist::save_atomic(&path, store.snapshot(), true).unwrap();
    store.mark_saved();
    assert!(!store.is_dirty());

    // 3. «Перезапуск»: читаем с диска и проверяем, что всё на месте.
    let (loaded, warning) = persist::load_with_recovery(&path).unwrap();
    assert!(warning.is_none());
    let store2 = Store::new(loaded, Arc::new(NoopProtector));
    let boot = store2.bootstrap(None);
    assert_eq!(boot.servers.len(), 2);
    assert_eq!(boot.settings.theme, Theme::Dark);
    assert!(boot.settings.accepted);

    let srv = &boot.servers[0];
    assert_eq!(srv.client_path.as_deref(), Some("/games/pw"));
    assert_eq!(srv.accounts.len(), 3);
    assert_eq!(srv.accounts[1].id, first, "порядок после перетаскивания сохранён");
    assert_eq!(srv.accounts[1].nick, "Alpha2");
    assert!(srv.accounts[1].has_password, "пароль не должен затираться пустым полем");
    assert_eq!(srv.accounts[1].class, "sin");

    // Пароли не утекают в UI-представление.
    let wire = serde_json::to_string(&boot).unwrap();
    for pw in ["pa", "pb", "pc", "pd"] {
        assert!(!wire.contains(&format!("\"{pw}\"")), "пароль {pw} утёк в bootstrap");
    }
    assert!(!wire.contains("\"secret\""), "в UI не должно быть поля secret");

    // Эмблема стабильна между запусками.
    let again = store2.bootstrap(None);
    assert_eq!(again.servers[0].art, srv.art);
    assert_eq!(again.servers[0].glyph, srv.glyph);

    fs::remove_dir_all(dir).ok();
}

#[test]
fn second_start_does_not_migrate_again() {
    let dir = tmp_dir("nomigrate");
    let path = persist::library_path(&dir);
    let mut snap = pwl_core::Snapshot::default();
    snap.servers.push(pwl_core::Server::new("Fresh", None));
    persist::save_atomic(&path, &snap, false).unwrap();

    // Как это делает хост: миграция только если library.json ещё нет.
    let loaded = persist::load(&path).unwrap();
    assert!(loaded.is_some());
    assert_eq!(loaded.unwrap().servers[0].name, "Fresh");
    fs::remove_dir_all(dir).ok();
}