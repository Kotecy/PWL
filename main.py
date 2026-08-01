"""PWL desktop host: Python backend + HTML/CSS UI through pywebview."""
import ctypes
import json
import os
import random
import sys
import threading
from pathlib import Path

import webview

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.8.0"
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
        return {
            "accepted": bool(data.get("accepted", False)),
            "theme": data.get("theme", "dark"),
            "minimize_to_tray": bool(data.get("minimize_to_tray", False)),
            "launch_mode": data.get("launch_mode", "bat"),
            "version": APP_VERSION,
        }

    def set_launch_mode(self, mode: str) -> dict:
        if mode not in ("auto", "bat"):
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

    def pick_elementclient(self) -> dict:
        """Native file picker for elementclient.exe itself (returns full file path).

        A folder-only dialog hides files entirely on Windows, so the user
        could never actually see elementclient.exe while browsing. We pick
        the .exe directly instead, which also guarantees launch() always
        finds it right away (no more "path saved but still not found")."""
        try:
            import webview as _wv
            # pywebview's winforms backend falls back to os.environ['HOMEPATH']
            # when directory is empty, which on Windows is a drive-less path
            # like '\\Users\\aleks'. Pass an explicit, valid directory instead.
            start = self._pick_start_dir()
            result = self._window.create_file_dialog(
                _wv.FileDialog.OPEN,
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

        threading.Thread(target=self._launch_and_login, args=(str(exe), account), daemon=True).start()
        return {"ok": True}

    def _launch_and_login(self, exe: str, account: dict) -> None:
        import subprocess
        import time

        with self._lock:
            data = self._read()
        mode = data.get("launch_mode", "bat")

        if mode == "bat":
            self._launch_via_bat(exe, account)
            return

        try:
            proc = subprocess.Popen([exe], cwd=str(Path(exe).parent))
        except Exception:
            return
        hwnd = self._wait_for_login_window(proc.pid, timeout=25.0)
        if not hwnd:
            return
        try:
            self._type_login(hwnd, account.get("login", ""), account.get("password", ""))
        except Exception:
            pass

    def _launch_via_bat(self, exe: str, account: dict) -> None:
        import subprocess
        import tempfile

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

    def _type_login(self, hwnd: int, login: str, password: str) -> None:
        import time

        if hwnd:
            self._force_foreground(hwnd)
            time.sleep(0.3)
            self._ensure_english_layout(hwnd)

        def key(vk):
            self._send_vk(vk)

        def send_text(text):
            for ch in text:
                self._send_unicode(ch)
                time.sleep(0.02)

        send_text(login)
        time.sleep(0.2)
        key(0x09)  # Tab
        time.sleep(0.2)
        send_text(password)
        time.sleep(0.2)
        key(0x0D)  # Enter

    def _force_foreground(self, hwnd: int) -> bool:
        """Plain SetForegroundWindow can silently fail (Windows blocks a
        background process from stealing focus unless certain conditions
        are met), which would make every subsequent keystroke go nowhere
        with no error at all. AttachThreadInput briefly merges our input
        queue with the target window's, which is the standard, reliable
        way around that restriction."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        SW_RESTORE = 9

        if user32.GetForegroundWindow() == hwnd:
            return True

        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        attached = False
        try:
            if target_thread and target_thread != current_thread:
                attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        except Exception:
            pass
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)
        return user32.GetForegroundWindow() == hwnd

    def _ensure_english_layout(self, hwnd: int) -> None:
        """Switch the target window's keyboard layout to English (US) if it
        isn't already active, so typed credentials aren't garbled by a
        non-Latin layout. No-ops quietly if English isn't among the user's
        installed input languages (LoadKeyboardLayoutW returns NULL)."""
        import time
        try:
            user32 = ctypes.windll.user32
            ENGLISH_US_LANGID = 0x0409
            thread_id = user32.GetWindowThreadProcessId(hwnd, None)
            current_hkl = user32.GetKeyboardLayout(thread_id)
            # Low word of HKL is the language identifier.
            if (current_hkl & 0xFFFF) == ENGLISH_US_LANGID:
                return
            KLF_ACTIVATE = 0x00000001
            hkl = user32.LoadKeyboardLayoutW("00000409", KLF_ACTIVATE)
            if not hkl:
                return
            WM_INPUTLANGCHANGEREQUEST = 0x0050
            user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
            time.sleep(0.2)
        except Exception:
            pass

    def _send_vk(self, vk: int) -> None:
        """Send a virtual-key press via SendInput (same modern API used for
        unicode text), rather than the older keybd_event, for consistency."""
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]

        user32 = ctypes.windll.user32
        inputs = (INPUT * 2)()
        for i, flag in enumerate((0, KEYEVENTF_KEYUP)):
            inputs[i].type = 1  # INPUT_KEYBOARD
            inputs[i].ki.wVk = vk
            inputs[i].ki.wScan = 0
            inputs[i].ki.dwFlags = flag
            inputs[i].ki.dwExtraInfo = None
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

    def _send_unicode(self, char: str) -> None:
        user32 = ctypes.windll.user32
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT)]

        inputs = (INPUT * 2)()
        for i, flag in enumerate((KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)):
            inputs[i].type = 1  # INPUT_KEYBOARD
            inputs[i].ki.wVk = 0
            inputs[i].ki.wScan = ord(char)
            inputs[i].ki.dwFlags = flag
            inputs[i].ki.dwExtraInfo = None
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

    def _enum_process_windows(self, pid: int) -> list:
        """All visible top-level windows belonging to a specific pid, as
        (hwnd, width, height) tuples."""
        user32 = ctypes.windll.user32
        results = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _lparam):
            owner_pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value == pid and user32.IsWindowVisible(hwnd):
                rect = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w, h = rect.right - rect.left, rect.bottom - rect.top
                if w > 0 and h > 0:
                    results.append((hwnd, w, h))
            return True

        user32.EnumWindows(WNDENUMPROC(callback), None)
        return results

    def _wait_for_login_window(self, pid: int, timeout: float = 25.0) -> int:
        """Poll the launched process for its windows. Splash screens, update
        notices, or "already running" prompts that pop up alongside the real
        login window get closed automatically (they're smaller); once a
        single window remains stable for a moment, treat it as the login
        window and return its handle."""
        import time
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        deadline = time.time() + timeout
        stable_hwnd = 0
        stable_since = 0.0

        while time.time() < deadline:
            windows = self._enum_process_windows(pid)
            if windows:
                windows.sort(key=lambda item: item[1] * item[2], reverse=True)
                main_hwnd = windows[0][0]
                for extra_hwnd, _w, _h in windows[1:]:
                    try:
                        user32.PostMessageW(extra_hwnd, WM_CLOSE, 0, 0)
                    except Exception:
                        pass
                if main_hwnd == stable_hwnd:
                    if time.time() - stable_since > 1.0:
                        return main_hwnd
                else:
                    stable_hwnd = main_hwnd
                    stable_since = time.time()
            time.sleep(0.4)
        return stable_hwnd

    def minimize(self) -> None:
        if self._window:
            if self._tray_enabled:
                try:
                    self._window.hide()
                except Exception:
                    self._window.minimize()
            else:
                self._window.minimize()

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
        if api._tray_enabled:
            api._set_tray_mode(True)

    webview.start(on_start, gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()