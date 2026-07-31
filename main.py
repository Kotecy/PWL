"""PWL desktop host: Python backend + HTML/CSS UI through pywebview."""
import ctypes
import json
import os
import sys
import threading
from pathlib import Path

import webview

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.5.2"
WINDOW_W = 900
WINDOW_H = 620
CORNER_RADIUS = 20

IS_WINDOWS = sys.platform.startswith("win")
RGN_OR = 2


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "PWL" / "config.json"


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def _window_hwnd() -> int:
    """Get the native window handle without touching pywebview internals."""
    if not IS_WINDOWS:
        return 0
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, APP_TITLE)
    if hwnd:
        return hwnd
    pid = os.getpid()
    holder = ctypes.c_void_p(0)
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        if user32.GetWindowThreadProcessId(hwnd, None) == pid and user32.IsWindowVisible(hwnd):
            holder.value = hwnd
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), None)
    return holder.value


def round_window_corners() -> None:
    """Round the real window instead of the page.

    WebView2 renders into an opaque rectangle, so a CSS border-radius would only
    reveal the page background behind the corners and read as a stacked layer.
    """
    if not IS_WINDOWS:
        return
    try:
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = _window_hwnd()
        if not hwnd:
            return
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w < 10 or h < 10:
            return
        region = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1,
                                          CORNER_RADIUS * 2, CORNER_RADIUS * 2)
        square_bottom = gdi32.CreateRectRgn(0, CORNER_RADIUS, w + 1, h + 1)
        gdi32.CombineRgn(region, region, square_bottom, RGN_OR)
        gdi32.DeleteObject(square_bottom)
        user32.SetWindowRgn(hwnd, region, True)
    except Exception:
        pass


class Api:
    """JS bridge. IMPORTANT: keep every attribute private or pywebview will
    recursively introspect it. A public `window` attribute made pywebview walk
    the whole .NET object graph on startup, which froze and crashed the app."""

    def __init__(self):
        self._window = None
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(config_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_state(self) -> dict:
        with self._lock:
            data = self._read()
        return {
            "accepted": bool(data.get("accepted", False)),
            "theme": data.get("theme", "dark"),
            "version": APP_VERSION,
        }

    def accept_welcome(self) -> dict:
        with self._lock:
            data = self._read()
            data["accepted"] = True
            self._write(data)
        return {"ok": True}

    def set_theme(self, theme: str) -> dict:
        if theme not in ("dark", "light"):
            return {"ok": False}
        with self._lock:
            data = self._read()
            data["theme"] = theme
            self._write(data)
        return {"ok": True}

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def close(self) -> None:
        if self._window:
            self._window.destroy()


def main() -> None:
    api = Api()
    window = webview.create_window(
        APP_TITLE,
        str(resource_path("web", "index.html")),
        js_api=api,
        width=WINDOW_W,
        height=WINDOW_H,
        min_size=(760, 520),
        frameless=True,
        easy_drag=False,
        resizable=True,
        background_color="#1b1d21",
    )
    api._window = window

    def on_start():
        # Round corners after the window is up; re-apply on resize.
        def reapply():
            try:
                round_window_corners()
            except Exception:
                pass

        # Frameless windows drop WS_MINIMIZEBOX, so clicking the taskbar icon
        # no longer toggles minimize/restore. Restore it after the window shows.
        def ensure_minimizebox():
            if not IS_WINDOWS:
                return
            try:
                user32 = ctypes.windll.user32
                hwnd = _window_hwnd()
                if hwnd:
                    style = user32.GetWindowLongW(hwnd, -16)
                    user32.SetWindowLongW(hwnd, -16, style | 0x00020000)
                    # Rebuild the non-client area so the taskbar learns the
                    # window is now minimizable and enables the smooth
                    # minimize/restore animation.
                    user32.SetWindowPos(
                        hwnd, None, 0, 0, 0, 0,
                        0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
                    )
            except Exception:
                pass

        window.events.shown += reapply
        window.events.resized += reapply
        window.events.shown += ensure_minimizebox
        reapply()
        ensure_minimizebox()

    webview.start(on_start, gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
