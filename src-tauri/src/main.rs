//! PWL 1.0 — нативная оболочка.
//!
//! Порядок запуска важен для скорости: окно показывается сразу (Tauri рисует
//! его до загрузки JS), данные отдаются одним вызовом `bootstrap`, тяжёлые
//! подсистемы (трей) поднимаются только если включены в настройках.

#![cfg_attr(all(not(debug_assertions), windows), windows_subsystem = "windows")]

mod commands;
mod secrets;
mod state;
mod tray;

use std::sync::Arc;

use tauri::{Manager, WindowEvent};

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Второй запуск не плодит процессы и не портит файл данных.
            tray::show_window(app);
        }))
        .setup(|app| {
            let handle = app.handle().clone();
            let state = state::init(&handle).map_err(|e| {
                eprintln!("PWL: не удалось загрузить данные: {e}");
                Box::new(e) as Box<dyn std::error::Error>
            })?;

            let tray_enabled = state
                .store
                .lock()
                .map(|s| s.settings().minimize_to_tray)
                .unwrap_or(false);
            app.manage(state);
            tray::build(&handle, tray_enabled)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let to_tray = app
                    .try_state::<Arc<state::AppState>>()
                    .and_then(|s| s.store.lock().ok().map(|g| g.settings().minimize_to_tray))
                    .unwrap_or(false);
                if to_tray {
                    api.prevent_close();
                    let _ = window.hide();
                } else if let Some(state) = app.try_state::<Arc<state::AppState>>() {
                    api.prevent_close();
                    commands::quit(app.clone(), state);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::bootstrap,
            commands::apply,
            commands::apply_batch,
            commands::launch,
            commands::pick_client,
            commands::data_dir,
            commands::open_data_dir,
            commands::flush,
            commands::win_minimize,
            commands::win_toggle_maximize,
            commands::win_close,
            commands::quit,
        ])
        .build(tauri::generate_context!())
        .expect("не удалось собрать приложение PWL");

    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            if let Some(state) = app.try_state::<Arc<state::AppState>>() {
                state.flush_blocking(std::time::Duration::from_secs(3));
            }
        }
    });
}