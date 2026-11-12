//! Замер нового ядра на том же сценарии, что и замеры старой версии в AUDIT.md.
//! Запуск: cargo run --release --example bench -p pwl-core

use std::sync::Arc;
use std::time::Instant;

use pwl_core::domain::{AccountDraft, Op, SettingsPatch, Theme};
use pwl_core::{persist, NoopProtector, Store};

fn draft(i: usize) -> AccountDraft {
    AccountDraft {
        login: format!("u{i}"),
        password: Some("p".into()),
        nick: format!("n{i}"),
        class: "mag".into(),
        ..Default::default()
    }
}

fn measure<T>(label: &str, n: usize, mut f: impl FnMut(usize) -> T) -> f64 {
    let t = Instant::now();
    for i in 0..n {
        f(i);
    }
    let per_op = t.elapsed().as_secs_f64() * 1000.0 / n as f64;
    println!("{label:<34} {per_op:>9.4} ms/op   (n={n})");
    per_op
}

fn main() {
    let dir = std::env::temp_dir().join(format!("pwl_bench_{}", pwl_core::ids::new_id("b")));
    std::fs::create_dir_all(&dir).unwrap();
    let path = persist::library_path(&dir);
    let mut store = Store::new(pwl_core::Snapshot::default(), Arc::new(NoopProtector));

    println!("=== PWL 1.0 core (Rust, состояние в памяти) ===\n");
    store
        .apply(Op::AddServer { name: "RU-1".into(), client_path: Some("C:\\Games\\PW\\elementclient.exe".into()) })
        .unwrap();
    let sid = store.servers()[0].id.clone();

    measure("bootstrap() (1 сервер)", 2000, |_| store.bootstrap(None));
    measure("add_account()", 200, |i| {
        store.apply(Op::AddAccount { server_id: sid.clone(), draft: draft(i) }).unwrap()
    });
    let ids: Vec<String> = store.servers()[0].accounts.iter().map(|a| a.id.clone()).collect();
    measure("update_account()", 200, |i| {
        store
            .apply(Op::UpdateAccount {
                server_id: sid.clone(),
                id: ids[i % ids.len()].clone(),
                draft: draft(i),
            })
            .unwrap()
    });

    for s in 1..20 {
        let name = format!("RU-{}", s + 1);
        store.apply(Op::AddServer { name: name.clone(), client_path: None }).unwrap();
        let id = store.servers().iter().find(|x| x.name == name).unwrap().id.clone();
        for i in 0..50 {
            store.apply(Op::AddAccount { server_id: id.clone(), draft: draft(i) }).unwrap();
        }
    }

    let total: usize = store.servers().iter().map(|s| s.accounts.len()).sum();
    persist::save_atomic(&path, store.snapshot(), false).unwrap();
    let size = std::fs::metadata(&path).unwrap().len() as f64 / 1024.0;
    println!("\n--- dataset: 20 серверов, {total} аккаунтов, файл {size:.1} KB ---");

    measure("bootstrap() (20 серверов)", 500, |_| store.bootstrap(None));
    let sid5 = store.servers()[5].id.clone();
    measure("add_account() big library", 200, |i| {
        store.apply(Op::AddAccount { server_id: sid5.clone(), draft: draft(i) }).unwrap()
    });
    measure("set_theme() (settings)", 2000, |i| {
        store
            .apply(Op::SetSettings {
                patch: SettingsPatch {
                    theme: Some(if i % 2 == 0 { Theme::Light } else { Theme::Dark }),
                    ..Default::default()
                },
            })
            .unwrap()
    });

    println!();
    let t = Instant::now();
    persist::save_atomic(&path, store.snapshot(), false).unwrap();
    println!("{:<34} {:>9.4} ms      (одна запись на всю пачку правок)", "save_atomic() — вся база", t.elapsed().as_secs_f64() * 1000.0);
    let t = Instant::now();
    let loaded = persist::load(&path).unwrap().unwrap();
    println!("{:<34} {:>9.4} ms      (чтение при старте)", "load() — вся база", t.elapsed().as_secs_f64() * 1000.0);
    assert_eq!(loaded.servers.len(), 20);

    println!("\nДисковых чтений на вызов моста: 0 (состояние в памяти).");
    println!("Дисковых записей на пачку правок: 1 (дебаунс 150 мс / максимум 1 с).");

    std::fs::remove_dir_all(dir).ok();
}