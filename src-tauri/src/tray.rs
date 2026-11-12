//! Системный трей средствами Tauri. Ни pystray, ни Pillow — иконка берётся
//! из ресурсов приложения, а живёт в том же процессе, что и окно.

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

pub const TRAY_ID: &str = "pwl-tray";
const SHOW: &str = "tray-show";
const QUIT: &str = "tray-quit";

pub fn build(app: &AppHandle, visible: bool) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, SHOW, "Открыть PWL", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, QUIT, "Выход", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    let tray = TrayIconBuilder::with_id(TRAY_ID)
        .icon(tauri::image::Image::from_bytes(include_bytes!(
            "../icons/32x32.png"
        ))?)
        .tooltip("PWL by Kotecy")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            SHOW => show_window(app),
            QUIT => {
                if let Some(state) = app.try_state::<std::sync::Arc<crate::state::AppState>>() {
                    crate::commands::quit(app.clone(), state);
                } else {
                    app.exit(0);
                }
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_window(tray.app_handle());
            }
        })
        .build(app)?;
    // В Tauri 2 у билдера нет `visible`: видимость выставляется на готовой иконке.
    tray.set_visible(visible)?;
    Ok(())
}

pub fn sync(app: &AppHandle, visible: bool) {
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_visible(visible);
    }
}

pub fn show_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}