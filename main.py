"""PWL by Kotecy - main window.

- Borderless window, rounded top corners (radius 20), square bottom
- Always present in the Windows taskbar
- Slim 30px title bar with drag, theme switch, minimize and close
- Light / dark theme with an animated sun-moon toggle, remembered on disk
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
APP_VERSION = "0.1.0"

WINDOW_W = 900
WINDOW_H = 620
TITLEBAR_H = 30
CORNER_RADIUS = 20
CARD_RADIUS = 30

THEMES = {
    "dark": {
        "bg": "#0A0A0D",
        "halo": "#101018",
        "shadow_far": "#111117",
        "shadow_near": "#17171F",
        "bar": "#101014",
        "line": "#20202A",
        "text": "#F3F3F6",
        "muted": "#8A8A96",
        "faint": "#4E4E5A",
        "hover": "#20202A",
        "accent": "#4C8DFF",
        "accent_hover": "#3A79E8",
        "danger": "#FF5A5A",
        "danger_soft": "#301316",
        "card": "#15151B",
        "card_line": "#25252F",
        "card_text": "#F3F3F6",
        "card_muted": "#8A8A96",
        "pill": "#1D1D26",
        "btn": "#4C8DFF",
        "btn_hover": "#3A79E8",
        "btn_text": "#FFFFFF",
        "panel": "#101015",
    },
    "light": {
        "bg": "#F1F2F5",
        "halo": "#E9EAEF",
        "shadow_far": "#E2E3E9",
        "shadow_near": "#D8D9E1",
        "bar": "#FFFFFF",
        "line": "#E3E4EA",
        "text": "#14141A",
        "muted": "#6B6B78",
        "faint": "#9A9AA6",
        "hover": "#EDEEF2",
        "accent": "#2F6FE4",
        "accent_hover": "#255CC4",
        "danger": "#E03B3B",
        "danger_soft": "#FBE3E3",
        "card": "#FFFFFF",
        "card_line": "#E6E7ED",
        "card_text": "#14141A",
        "card_muted": "#6B6B78",
        "pill": "#EEF2FB",
        "btn": "#14141A",
        "btn_hover": "#2B2B36",
        "btn_text": "#FFFFFF",
        "panel": "#FFFFFF",
    },
}

F_TITLE = ("Segoe UI Semibold", 9)
F_PILL = ("Segoe UI Semibold", 8)
F_H1 = ("Segoe UI Semibold", 17)
F_H2 = ("Segoe UI Semibold", 12)
F_BODY = ("Segoe UI", 10)
F_SMALL = ("Segoe UI", 8)
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


def soft_elevation(canvas, x1, y1, x2, y2, r, theme, spread=3):
    """Fake soft shadow: stacked rounded rects behind the card."""
    layers = [(spread * 6, theme["shadow_far"]), (spread * 3, theme["shadow_near"])]
    for pad, color in layers:
        rounded_rect(canvas, x1 - pad, y1 - pad + pad / 2, x2 + pad, y2 + pad + pad / 2,
                     r + pad / 2, fill=color, outline="")


class CanvasButton:
    """Rounded button drawn directly on a canvas, with hover and press states."""

    _counter = 0

    def __init__(self, canvas, cx, cy, w, h, text, command, theme,
                 radius=14, fill=None, hover=None, fg=None, font=F_BTN, outline=""):
        CanvasButton._counter += 1
        tag = f"cbtn{CanvasButton._counter}"
        self.canvas = canvas
        self.fill = fill or theme["btn"]
        self.hover = hover or theme["btn_hover"]
        self.command = command
        x1, y1 = cx - w / 2, cy - h / 2
        self.shape = rounded_rect(canvas, x1, y1, x1 + w, y1 + h, radius,
                                  fill=self.fill, outline=outline, tags=tag)
        canvas.create_text(cx, cy, text=text, fill=fg or theme["btn_text"],
                           font=font, tags=tag)
        canvas.tag_bind(tag, "<Enter>", self._enter)
        canvas.tag_bind(tag, "<Leave>", self._leave)
        canvas.tag_bind(tag, "<ButtonRelease-1>", self._release)

    def _enter(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.hover)
        self.canvas.configure(cursor="hand2")

    def _leave(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.fill)
        self.canvas.configure(cursor="")

    def _release(self, _e):
        self.command()


def draw_sun(canvas, cx, cy, color, r=4):
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=1.4)
    for i in range(8):
        import math
        a = math.pi * i / 4
        x0, y0 = cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2)
        x1, y1 = cx + math.cos(a) * (r + 4), cy + math.sin(a) * (r + 4)
        canvas.create_line(x0, y0, x1, y1, fill=color, width=1.4, capstyle="round")


def draw_moon(canvas, cx, cy, color, bg, r=6):
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=color)
    canvas.create_oval(cx - r + 4, cy - r - 3, cx + r + 4, cy + r - 3,
                       fill=bg, outline=bg)


# ------------------------------------------------------------- win32 chrome
def window_handle(root):
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    return hwnd or root.winfo_id()


def show_in_taskbar(root):
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
        self.theme_name = self.config.get("theme", "dark")
        self.screen = "workspace" if self.config.get("accepted") else "welcome"
        self._drag = (0, 0)
        self._region = None

        root.title(APP_TITLE)
        root.overrideredirect(True)
        root.attributes("-alpha", 0.0)
        self._center()

        self.body = None
        self.build_ui()

        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Return>", self._on_enter)
        root.bind("<Control-t>", lambda _e: self.toggle_theme())
        root.bind("<Configure>", lambda _e: self._refresh_region())
        root.after(30, self._apply_chrome)
        root.after(60, self._fade_in)

    @property
    def theme(self):
        return THEMES[self.theme_name]

    # -- window ------------------------------------------------------------
    def _center(self):
        x = int((self.root.winfo_screenwidth() - WINDOW_W) / 2)
        y = int((self.root.winfo_screenheight() - WINDOW_H) / 2)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{max(y, 0)}")

    def _fade_in(self, value=0.0):
        value = min(value + 0.12, 1.0)
        try:
            self.root.attributes("-alpha", value)
        except Exception:
            return
        if value < 1.0:
            self.root.after(12, lambda: self._fade_in(value))

    def _apply_chrome(self):
        show_in_taskbar(self.root)
        self.root.after(60, lambda: self._refresh_region(force=True))

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

    # -- theme -------------------------------------------------------------
    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.config["theme"] = self.theme_name
        save_config(self.config)
        self.build_ui()

    # -- layout ------------------------------------------------------------
    def build_ui(self):
        theme = self.theme
        self.root.configure(bg=theme["bg"])
        if self.body is not None:
            self.body.destroy()

        self.body = tk.Frame(self.root, bg=theme["bg"])
        self.body.pack(fill="both", expand=True)

        self._build_titlebar()
        self.content = tk.Frame(self.body, bg=theme["bg"])
        self.content.pack(fill="both", expand=True)

        if self.screen == "welcome":
            self.show_welcome()
        else:
            self.show_workspace()

    def _build_titlebar(self):
        theme = self.theme
        bar = tk.Frame(self.body, bg=theme["bar"], height=TITLEBAR_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        logo = tk.Canvas(bar, bg=theme["bar"], width=16, height=16, highlightthickness=0)
        logo.pack(side="left", padx=(10, 8))
        rounded_rect(logo, 0, 0, 16, 16, 5, fill=theme["accent"], outline="")
        logo.create_text(8, 8, text="P", fill="#FFFFFF", font=("Segoe UI Semibold", 8))

        title = tk.Label(bar, text=APP_TITLE, bg=theme["bar"], fg=theme["text"], font=F_TITLE)
        title.pack(side="left")

        self._control(bar, "\u2715", self.close, theme["danger"], theme["danger_soft"])
        self._control(bar, "\u2013", self.minimize, theme["muted"], theme["hover"])
        self._theme_switch(bar)

        tk.Frame(self.body, bg=theme["line"], height=1).pack(fill="x", side="top")

        for widget in (bar, title, logo):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _control(self, bar, glyph, command, fg, hover_bg):
        theme = self.theme
        btn = tk.Label(bar, text=glyph, bg=theme["bar"], fg=fg,
                       font=("Segoe UI", 10), width=4, cursor="hand2")
        btn.pack(side="right", fill="y")
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover_bg, fg=theme["text"]))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=theme["bar"], fg=fg))
        return btn

    def _theme_switch(self, bar):
        """Sun in dark mode, moon in light mode - the icon shows what you switch to."""
        theme = self.theme
        cell = tk.Canvas(bar, bg=theme["bar"], width=34, height=TITLEBAR_H,
                         highlightthickness=0, cursor="hand2")
        cell.pack(side="right", fill="y")
        cx, cy = 17, TITLEBAR_H / 2

        def render(bg, fg):
            cell.delete("all")
            cell.configure(bg=bg)
            rounded_rect(cell, 3, 4, 31, TITLEBAR_H - 4, 8,
                         fill=bg, outline="")
            if self.theme_name == "dark":
                draw_sun(cell, cx, cy, fg)
            else:
                draw_moon(cell, cx, cy, fg, bg)

        render(theme["bar"], theme["muted"])
        cell.bind("<Enter>", lambda _e: render(theme["hover"], theme["accent"]))
        cell.bind("<Leave>", lambda _e: render(theme["bar"], theme["muted"]))
        cell.bind("<Button-1>", lambda _e: self.toggle_theme())

    def _start_drag(self, event):
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _on_enter(self, _event):
        if self.screen == "welcome":
            self.on_accept()

    # -- screens -----------------------------------------------------------
    def _new_canvas(self):
        for child in self.content.winfo_children():
            child.destroy()
        canvas = tk.Canvas(self.content, bg=self.theme["bg"], highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        return canvas

    def show_welcome(self):
        self.screen = "welcome"
        canvas = self._new_canvas()

        def draw(_event=None):
            theme = self.theme
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            cw, ch = 460, 330
            x1, y1 = (w - cw) / 2, (h - ch) / 2 - 8
            x2, y2 = x1 + cw, y1 + ch
            cx = w / 2

            # ambient halo behind the card
            rounded_rect(canvas, x1 - 70, y1 - 50, x2 + 70, y2 + 50, 90,
                         fill=theme["halo"], outline="")
            soft_elevation(canvas, x1, y1, x2, y2, CARD_RADIUS, theme)
            rounded_rect(canvas, x1, y1, x2, y2, CARD_RADIUS,
                         fill=theme["card"], outline=theme["card_line"])

            # pill badge
            pw, ph = 152, 24
            rounded_rect(canvas, cx - pw / 2, y1 + 30, cx + pw / 2, y1 + 30 + ph, 12,
                         fill=theme["pill"], outline="")
            canvas.create_text(cx, y1 + 42, text="PERFECT WORLD",
                               fill=theme["accent"], font=F_PILL)

            canvas.create_text(cx, y1 + 88, text="\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0432 PWL",
                               fill=theme["card_text"], font=F_H1)
            canvas.create_text(
                cx, y1 + 128,
                text="\u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0432\u0445\u043e\u0434 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442 \u0431\u0435\u0437 .bat-\u0444\u0430\u0439\u043b\u043e\u0432\n\u0438 \u0440\u0443\u0447\u043d\u043e\u0433\u043e \u0432\u0432\u043e\u0434\u0430 \u043f\u0430\u0440\u043e\u043b\u0435\u0439",
                fill=theme["card_muted"], font=F_BODY, justify="center", spacing1=5,
            )
            canvas.create_line(x1 + 46, y1 + 176, x2 - 46, y1 + 176, fill=theme["card_line"])
            canvas.create_text(
                cx, y1 + 212,
                text="\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0440\u044f\u043c\u043e \u0441\u0435\u0439\u0447\u0430\u0441 \u0441\u0432\u043e\u0439\n\u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440 \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442",
                fill=theme["card_text"], font=F_H2, justify="center", spacing1=5,
            )
            CanvasButton(canvas, cx, y1 + 276, 232, 44, "\u041f\u0440\u0438\u043d\u044f\u0442\u044c",
                         self.on_accept, theme, radius=14)
            canvas.create_text(cx, y2 + 34, text=f"v{APP_VERSION}  \u00b7  Enter \u2014 \u043f\u0440\u0438\u043d\u044f\u0442\u044c  \u00b7  Ctrl+T \u2014 \u0442\u0435\u043c\u0430",
                               fill=theme["faint"], font=F_SMALL)

        canvas.bind("<Configure>", draw)
        self.root.after(40, draw)

    def on_accept(self):
        self.config["accepted"] = True
        save_config(self.config)
        self.show_workspace()

    def show_workspace(self):
        self.screen = "workspace"
        canvas = self._new_canvas()

        def draw(_event=None):
            theme = self.theme
            canvas.delete("all")
            w, h = canvas.winfo_width(), canvas.winfo_height()
            cx = w / 2

            canvas.create_text(40, 42, text="\u0421\u0435\u0440\u0432\u0435\u0440\u044b \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u044b",
                               anchor="w", fill=theme["text"], font=F_H1)
            canvas.create_text(40, 68, text="\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u0439\u0442\u0435 \u0432\u0445\u043e\u0434\u043e\u043c \u0432 \u043b\u044e\u0431\u043e\u0439 \u0438\u0437 \u0441\u0432\u043e\u0438\u0445 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u043e\u0432",
                               anchor="w", fill=theme["muted"], font=F_BODY)

            bw, bh = 520, 250
            x1, y1 = (w - bw) / 2, (h - bh) / 2 + 16
            x2, y2 = x1 + bw, y1 + bh
            soft_elevation(canvas, x1, y1, x2, y2, 24, theme, spread=2)
            rounded_rect(canvas, x1, y1, x2, y2, 24,
                         fill=theme["panel"], outline=theme["card_line"])

            # empty-state glyph
            gx, gy = cx, y1 + 62
            rounded_rect(canvas, gx - 26, gy - 20, gx + 26, gy + 20, 12,
                         fill=theme["pill"], outline="")
            canvas.create_line(gx - 12, gy, gx + 12, gy, fill=theme["accent"], width=2,
                               capstyle="round")
            canvas.create_line(gx, gy - 12, gx, gy + 12, fill=theme["accent"], width=2,
                               capstyle="round")

            canvas.create_text(cx, y1 + 118, text="\u0417\u0434\u0435\u0441\u044c \u043f\u043e\u043a\u0430 \u043f\u0443\u0441\u0442\u043e",
                               fill=theme["text"], font=F_H2)
            canvas.create_text(cx, y1 + 146, text="\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c",
                               fill=theme["muted"], font=F_BODY)
            CanvasButton(canvas, cx, y1 + 198, 232, 44,
                         "+   \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440", lambda: None, theme,
                         radius=14, fill=theme["accent"], hover=theme["accent_hover"],
                         fg="#FFFFFF")

        canvas.bind("<Configure>", draw)
        self.root.after(40, draw)


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
