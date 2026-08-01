"""PWL desktop host: Python backend + HTML/CSS UI through pywebview."""
import ctypes
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import webview

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.9.0"
WINDOW_W = 900
WINDOW_H = 620

IS_WINDOWS = sys.platform.startswith("win")


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "PWL" / "config.json"


def _random_accounts_name() -> str:
    """7–15 random digits for the accounts file name."""
    return "".join(str(random.randint(0, 9)) for _ in range(random.randint(7, 15)))


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


class Api:
    """JS bridge. IMPORTANT: keep every attribute private or pywebview will
    recursively introspect it. A public `window` attribute made pywebview walk
    the whole .NET object graph on startup, which froze and crashed the app."""

    def __init__(self):
        self._window = None
        self._lock = threading.Lock()
        self._tray_enabled = False
        self._tray_icon = None

    def _read(self) -> dict:
        try:
            return json.loads(config_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _accounts_path(self) -> Path:
        """Path of the accounts file. If config has no remembered path yet,
        create one with a random 7–15 digit name and remember it."""
        data = self._read()
        remembered = data.get("accounts_file")
        if remembered and Path(remembered).exists():
            return Path(remembered)
        path = config_path().parent / f"{_random_accounts_name()}.json"
        data["accounts_file"] = str(path)
        self._write(data)
        return path

    def _read_accounts(self) -> dict:
        try:
            return json.loads(self._accounts_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_accounts(self, data: dict) -> None:
        path = self._accounts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_state(self) -> dict:
        with self._lock:
            data = self._read()
        launch_mode = data.get("launch_mode", "bat")
        if launch_mode != "bat":
            launch_mode = "bat"
        return {
            "accepted": bool(data.get("accepted", False)),
            "theme": data.get("theme", "dark"),
            "minimize_to_tray": bool(data.get("minimize_to_tray", False)),
            "launch_mode": launch_mode,
            "version": APP_VERSION,
        }

    def set_launch_mode(self, mode: str) -> dict:
        if mode != "bat":
            return {"ok": False}
        with self._lock:
            data = self._read()
            data["launch_mode"] = mode
            self._write(data)
        return {"ok": True}

    def get_data(self) -> dict:
        with self._lock:
            data = self._read_accounts()
        return {"servers": data.get("servers", [])}

    def add_server(self, name: str, path: str = "") -> dict:
        with self._lock:
            data = self._read_accounts()
            servers = data.setdefault("servers", [])
            if any(s.get("name") == name for s in servers):
                return {"ok": False, "error": "Сервер с таким названием уже есть"}
            servers.append({"name": name, "path": path, "accounts": []})
            self._write_accounts(data)
        return {"ok": True}

    def set_server_path(self, name: str, path: str) -> dict:
        with self._lock:
            data = self._read_accounts()
            for s in data.setdefault("servers", []):
                if s.get("name") == name:
                    s["path"] = path
                    self._write_accounts(data)
                    return {"ok": True}
        return {"ok": False, "error": "Сервер не найден"}

    def delete_server(self, name: str, keep_accounts: bool = False) -> dict:
        """Remove a server. If keep_accounts is True, its accounts are kept in
        the config file (moved aside), otherwise they are deleted too."""
        with self._lock:
            data = self._read_accounts()
            servers = data.get("servers", [])
            for i, s in enumerate(servers):
                if s.get("name") == name:
                    if keep_accounts:
                        kept = data.setdefault("kept_accounts", {})
                        kept.setdefault(name, []).extend(s.get("accounts", []))
                    del servers[i]
                    self._write_accounts(data)
                    return {"ok": True}
        return {"ok": False, "error": "Сервер не найден"}

    def pick_elementclient(self) -> dict:
        """Native file picker for elementclient.exe itself (returns full file path).

        A folder-only dialog hides files entirely on Windows, so the user
        could never actually see elementclient.exe while browsing. We pick
        the .exe directly instead, which also guarantees launch() always
        finds it right away (no more "path saved but still not found")."""
        try:
            # pywebview's winforms backend falls back to os.environ['HOMEPATH']
            # when directory is empty, which on Windows is a drive-less path
            # like '\\Users\\aleks'. Pass an explicit, valid directory instead.
            start = self._pick_start_dir()
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=start,
                allow_multiple=False,
                file_types=(
                    "Elementclient (*.exe)",
                    "Все файлы (*.*)",
                ),
            )
            if result and result[0]:
                return {"ok": True, "path": result[0]}
            return {"ok": False, "path": ""}
        except Exception as exc:
            return {"ok": False, "path": "", "error": str(exc)}

    def _pick_start_dir(self) -> str:
        """Start the folder dialog somewhere useful: the folder of a known
        Elementclient, or the user profile as a sane fallback."""
        with self._lock:
            data = self._read_accounts()
        for s in data.get("servers", []):
            p = s.get("path", "")
            if p:
                cand = Path(p)
                if cand.is_file():
                    cand = cand.parent
                if cand.is_dir():
                    return str(cand)
        return os.path.expanduser("~")

    def add_account(self, server_name: str, account: dict) -> dict:
        with self._lock:
            data = self._read_accounts()
            for s in data.setdefault("servers", []):
                if s.get("name") == server_name:
                    s.setdefault("accounts", []).append(account)
                    self._write_accounts(data)
                    return {"ok": True}
        return {"ok": False, "error": "Сервер не найден"}

    def update_account(self, server_name: str, index: int, account: dict) -> dict:
        with self._lock:
            data = self._read_accounts()
            for s in data.setdefault("servers", []):
                if s.get("name") == server_name:
                    accounts = s.setdefault("accounts", [])
                    if 0 <= index < len(accounts):
                        accounts[index] = account
                        self._write_accounts(data)
                        return {"ok": True}
        return {"ok": False, "error": "Аккаунт не найден"}

    def delete_account(self, server_name: str, index: int) -> dict:
        with self._lock:
            data = self._read_accounts()
            for s in data.setdefault("servers", []):
                if s.get("name") == server_name:
                    accounts = s.setdefault("accounts", [])
                    if 0 <= index < len(accounts):
                        del accounts[index]
                        self._write_accounts(data)
                        return {"ok": True}
        return {"ok": False, "error": "Аккаунт не найден"}

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

    def set_minimize_to_tray(self, enabled: bool) -> dict:
        with self._lock:
            data = self._read()
            data["minimize_to_tray"] = bool(enabled)
            self._write(data)
        self._set_tray_mode(bool(enabled))
        return {"ok": True}

    def _set_tray_mode(self, enabled: bool) -> None:
        self._tray_enabled = enabled
        if enabled and _HAS_TRAY and self._tray_icon is None:
            self._tray_icon = self._make_tray_icon()
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        elif not enabled and self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _make_tray_icon(self):
        def make_image():
            try:
                icon_path = resource_path("web", "launcher.ico")
                if icon_path.is_file():
                    img = Image.open(icon_path)
                    img = img.convert("RGBA")
                    img = img.resize((64, 64), Image.LANCZOS)
                    return img
            except Exception:
                pass
            size = 64
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse((4, 4, size - 4, size - 4), fill="#4493f8")
            draw.text((size / 2, size / 2), "P", fill="white", anchor="mm")
            return image

        def show_window(icon=None, item=None):
            if self._window:
                try:
                    self._window.show()
                    self._window.restore()
                except Exception:
                    pass

        def quit_app(icon=None, item=None):
            self._set_tray_mode(False)
            if self._window:
                try:
                    self._window.destroy()
                except Exception:
                    pass

        return pystray.Icon(
            "pwl",
            make_image(),
            APP_TITLE,
            menu=pystray.Menu(
                pystray.MenuItem("Открыть PWL", show_window, default=True),
                pystray.MenuItem("Выход", quit_app),
            ),
        )

    def launch(self, server_name: str, index: int) -> dict:
        with self._lock:
            data = self._read_accounts()
            server = next((s for s in data.get("servers", []) if s.get("name") == server_name), None)
        if not server:
            return {"ok": False, "error": "Сервер не найден"}
        accounts = server.get("accounts", [])
        if not (0 <= index < len(accounts)):
            return {"ok": False, "error": "Аккаунт не найден"}
        account = accounts[index]
        path = server.get("path", "")
        if not path:
            return {"ok": False, "error": "Путь к Elementclient не задан"}
        exe = Path(path)
        if not exe.is_file():
            exe = exe / "elementclient.exe"
        if not exe.is_file():
            return {"ok": False, "error": f"elementclient.exe не найден по пути {exe}"}

        threading.Thread(target=self._launch_via_bat, args=(str(exe), account), daemon=True).start()
        return {"ok": True}

    def _launch_via_bat(self, exe: str, account: dict) -> None:
        login = account.get("login", "")
        password = account.get("password", "")
        nick = account.get("nick", "")
        auto_role = bool(account.get("auto", False))
        args = "startbypatcher nocheck"
        if login:
            args += f' user:{login}'
        if password:
            args += f' pwd:{password}'
        if auto_role and nick:
            args += f' role:{nick}'
        exe_dir = str(Path(exe).parent)
        bat = (
            "@echo off\r\n"
            "chcp 1251 >nul\r\n"
            f'cd /d "{exe_dir}"\r\n'
            f'start "" "{exe}" {args}\r\n'
        )
        try:
            # Write to the system temp dir, not exe_dir: many game installs
            # (e.g. under Program Files) aren't writable by a normal user,
            # which made file creation fail silently here before.
            fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="pwl_launch_")
            with os.fdopen(fd, "w", encoding="cp1251") as f:
                f.write(bat)
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                cwd=exe_dir,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    def minimize(self) -> None:
        if self._window:
            if self._tray_enabled:
                try:
                    self._window.hide()
                except Exception:
                    self._window.minimize()
            else:
                self._window.minimize()

    def show_window(self) -> None:
        if self._window:
            try:
                self._window.show()
                self._window.restore()
            except Exception:
                pass

    def close(self) -> None:
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        if self._window:
            self._window.destroy()


def main() -> None:
    api = Api()
    try:
        api._tray_enabled = bool(json.loads(config_path().read_text(encoding="utf-8")).get("minimize_to_tray", False))
    except Exception:
        api._tray_enabled = False
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
        hidden=True,
        background_color="#1b1d21",
    )
    api._window = window

    def on_start():
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

        window.events.shown += ensure_minimizebox
        ensure_minimizebox()
        if api._tray_enabled:
            api._set_tray_mode(True)

    webview.start(on_start, gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()