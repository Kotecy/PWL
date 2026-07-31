"""PWL by Kotecy - main window.

- Borderless dark window, no outer stroke
- Rounded top corners (radius 20), square bottom
- Always present in the Windows taskbar
- Compact custom title bar with drag, minimize and close
- Welcome card (radius 30) with a working "Accept" button
"""

import json
import os
import sys
import tkinter as tk
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import ctypes

APP_TITLE = "PWL by Kotecy"

WINDOW_W = 940
WINDOW_H = 660
TITLEBAR_H = 40
CORNER_RADIUS = 20
CARD_RADIUS = 30

# palette
BG = "#0B0B0E"
BAR = "#141419"
BAR_LINE = "#24242C"
TEXT = "#F2F2F5"
MUTED = "#8B8B96"
ACCENT = "#3B82F6"
ACCENT_SOFT = "#16213A"
DANGER = "#EF4444"
DANGER_SOFT = "#2A1113"
HOVER = "#22222A"

CARD = "#ECECEF"
CARD_LINE = "#D3D3D9"
CARD_TEXT = "#0B0B0E"
CARD_MUTED = "#5C5C68"
BTN = "#111116"
BTN_HOVER = "#2C2C36"

F_TITLE = ("Segoe UI Semibold", 11)
F_H1 = ("Segoe UI Semibold", 17)
F_H2 = ("Segoe UI Semibold", 13)
F_BODY = ("Segoe UI", 11)
F_BTN = ("Segoe UI Semibold", 11)


# ----------------------------------------------------------------- config io
def config_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / "PWL" / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict) -> None:
    try:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ------------------------------------------------------------- canvas shapes
def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kwargs)


class CanvasButton:
    """Rounded button drawn directly on a canvas."""

    _counter = 0

    def __init__(self, canvas, cx, cy, w, h, text, command,
                 radius=12, fill=BTN, hover=BTN_HOVER, fg="#FFFFFF", font=F_BTN):
        CanvasButton._counter += 1
        tag = f"cbtn{CanvasButton._counter}"
        self.canvas = canvas
        self.fill = fill
        self.hover = hover
        x1, y1 = cx - w / 2, cy - h / 2
        self.shape = rounded_rect(canvas, x1, y1, x1 + w, y1 + h, radius,
                                  fill=fill, outline="", tags=tag)
        canvas.create_text(cx, cy, text=text, fill=fg, font=font, tags=tag)
        canvas.tag_bind(tag, "<Button-1>", lambda _e: command())
        canvas.tag_bind(tag, "<Enter>", self._enter)
        canvas.tag_bind(tag, "<Leave>", self._leave)

    def _enter(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.hover)
        self.canvas.configure(cursor="hand2")

    def _leave(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.fill)
        self.canvas.configure(cursor="")


# ------------------------------------------------------------ win32 chrome
def window_handle(root):
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    return hwnd or root.winfo_id()


def show_in_taskbar(root):
    """Keep a borderless window visible in the taskbar at all times."""
    if not IS_WINDOWS:
        return
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    user32 = ctypes.windll.user32
    hwnd = window_handle(root)
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    root.withdraw()
    root.after(10, root.deiconify)


def round_top_corners(root, w, h, radius=CORNER_RADIUS):
    """Clip the window so only the top corners are rounded."""
    if not IS_WINDOWS:
        return
    gdi32 = ctypes.windll.gdi32
    hwnd = window_handle(root)
    top = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius * 2, radius * 2)
    bottom = gdi32.CreateRectRgn(0, radius, w + 1, h + 1)
    gdi32.CombineRgn(top, top, bottom, 2)  # RGN_OR
    gdi32.DeleteObject(bottom)
    ctypes.windll.user32.SetWindowRgn(hwnd, top, True)


# ------------------------------------------------------------------- the app
class PwlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = load_config()
        self._drag = (0, 0)
        self._region = None

        root.title(APP_TITLE)
        root.configure(bg=BG)
        root.overrideredirect(True)
        self._center()

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True)

        self._build_titlebar()
        self.content = tk.Frame(self.body, bg=BG)
        self.content.pack(fill="both", expand=True)

        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Configure>", self._on_configure)
        root.after(30, self._apply_chrome)

        if self.config.get("accepted"):
            self.show_workspace()
        else:
            self.show_welcome()

    # -- window ------------------------------------------------------------
    def _center(self):
        x = int((self.root.winfo_screenwidth() - WINDOW_W) / 2)
        y = int((self.root.winfo_screenheight() - WINDOW_H) / 2)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{max(y, 0)}")

    def _apply_chrome(self):
        show_in_taskbar(self.root)
        self.root.after(60, lambda: self._refresh_region(force=True))

    def _on_configure(self, _event=None):
        self._refresh_region()

    def _refresh_region(self, force=False):
        size = (self.root.winfo_width(), self.root.winfo_height())
        if size[0] < 10 or size[1] < 10:
            return
        if force or size != self._region:
            self._region = size
            round_top_corners(self.root, size[0], size[1])

    def minimize(self):
        if IS_WINDOWS:
            ctypes.windll.user32.ShowWindow(window_handle(self.root), 6)  # SW_MINIMIZE
        else:
            self.root.overrideredirect(False)
            self.root.iconify()

    def close(self):
        self.root.destroy()

    # -- title bar ---------------------------------------------------------
    def _build_titlebar(self):
        bar = tk.Frame(self.body, bg=BAR, height=TITLEBAR_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        logo = tk.Canvas(bar, bg=BAR, width=20, height=20, highlightthickness=0)
        logo.pack(side="left", padx=(14, 10))
        rounded_rect(logo, 0, 0, 20, 20, 6, fill=ACCENT, outline="")
        logo.create_text(10, 10, text="P", fill="#FFFFFF", font=("Segoe UI Semibold", 10))

        title = tk.Label(bar, text=APP_TITLE, bg=BAR, fg=TEXT, font=F_TITLE)
        title.pack(side="left")

        self._control(bar, "\u2715", self.close, DANGER, DANGER_SOFT)
        self._control(bar, "\u2013", self.minimize, MUTED, HOVER)

        line = tk.Frame(self.body, bg=BAR_LINE, height=1)
        line.pack(fill="x", side="top")

        for widget in (bar, title, logo):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _control(self, bar, glyph, command, fg, hover_bg):
        btn = tk.Label(bar, text=glyph, bg=BAR, fg=fg,
                       font=("Segoe UI", 11), width=5, cursor="hand2")
        btn.pack(side="right", fill="y")
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover_bg, fg=TEXT))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=BAR, fg=fg))
        return btn

    def _start_drag(self, event):
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    # -- screens -----------------------------------------------------------
    def _new_canvas(self):
        for child in self.content.winfo_children():
            child.destroy()
        canvas = tk.Canvas(self.content, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        return canvas

    def show_welcome(self):
        canvas = self._new_canvas()

        def draw(_event=None):
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            cw, ch = 470, 300
            x1, y1 = (w - cw) / 2, (h - ch) / 2
            cx = w / 2

            rounded_rect(canvas, x1, y1, x1 + cw, y1 + ch, CARD_RADIUS,
                         fill=CARD, outline="")

            canvas.create_text(cx, y1 + 54, text="\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0432 PWL",
                               fill=CARD_TEXT, font=F_H1)
            canvas.create_text(
                cx, y1 + 100,
                text="\u041f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430 \u0434\u043b\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0432\u0445\u043e\u0434\u0430\n\u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442 Perfect World",
                fill=CARD_MUTED, font=F_BODY, justify="center", spacing1=4,
            )
            canvas.create_line(x1 + 44, y1 + 146, x1 + cw - 44, y1 + 146, fill=CARD_LINE)
            canvas.create_text(
                cx, y1 + 186,
                text="\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0440\u044f\u043c\u043e \u0441\u0435\u0439\u0447\u0430\u0441 \u0441\u0432\u043e\u0439\n\u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440 \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442",
                fill=CARD_TEXT, font=F_H2, justify="center", spacing1=4,
            )
            CanvasButton(canvas, cx, y1 + 248, 230, 44,
                         "\u041f\u0440\u0438\u043d\u044f\u0442\u044c", self.on_accept, radius=14)

        canvas.bind("<Configure>", draw)
        self.root.after(50, draw)

    def on_accept(self):
        self.config["accepted"] = True
        save_config(self.config)
        self.show_workspace()

    def show_workspace(self):
        canvas = self._new_canvas()

        def draw(_event=None):
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            cx = w / 2
            bw, bh = 460, 220
            x1, y1 = (w - bw) / 2, (h - bh) / 2

            rounded_rect(canvas, x1, y1, x1 + bw, y1 + bh, 24,
                         fill="#101014", outline=BAR_LINE)
            canvas.create_text(cx, y1 + 62, text="\u0421\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442",
                               fill=TEXT, font=F_H2)
            canvas.create_text(
                cx, y1 + 98,
                text="\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0441\u0435\u0440\u0432\u0435\u0440 \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c",
                fill=MUTED, font=F_BODY,
            )
            CanvasButton(canvas, cx, y1 + 156, 230, 44,
                         "+  \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440", lambda: None,
                         radius=14, fill=ACCENT, hover="#2E6FE0")

        canvas.bind("<Configure>", draw)
        self.root.after(50, draw)


def main():
    if IS_WINDOWS:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    PwlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
