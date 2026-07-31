"""PWL desktop host: Python backend + HTML/CSS UI through pywebview."""
import json
import os
import sys
import threading
from pathlib import Path

import webview

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.3.0"
WINDOW_W = 900
WINDOW_H = 620


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "PWL" / "config.json"


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


class Api:
    def __init__(self):
        self.window = None
        self.lock = threading.Lock()

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
        with self.lock:
            data = self._read()
        return {
            "accepted": bool(data.get("accepted", False)),
            "theme": data.get("theme", "dark"),
            "version": APP_VERSION,
        }

    def accept_welcome(self) -> dict:
        with self.lock:
            data = self._read()
            data["accepted"] = True
            self._write(data)
        return {"ok": True}

    def set_theme(self, theme: str) -> dict:
        if theme not in ("dark", "light"):
            return {"ok": False}
        with self.lock:
            data = self._read()
            data["theme"] = theme
            self._write(data)
        return {"ok": True}

    def minimize(self) -> None:
        if self.window:
            self.window.minimize()

    def close(self) -> None:
        if self.window:
            self.window.destroy()


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
        shadow=True,
        background_color="#1b1d21",
    )
    api.window = window
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
