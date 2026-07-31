"""PWL by Kotecy — compact Windows UI."""
import json
import os
import sys
import tkinter as tk
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import ctypes

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.2.2"
WINDOW_W, WINDOW_H = 900, 620
TITLEBAR_H = 22
CORNER_RADIUS = 20
CARD_RADIUS = 30

VK = {
    "A": 0x41, "D": 0x44, "E": 0x45, "F": 0x46, "L": 0x4C,
    "N": 0x4E, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54, "W": 0x57,
}

THEMES = {
    "dark": {
        "bg": "#1B1D21", "halo": "#202329",
        "shadow_far": "#17191D", "shadow_near": "#202329",
        "bar": "#24272D", "line": "#3A3F48",
        "text": "#F0F1F2", "muted": "#A7ABB3", "faint": "#7D838D",
        "hover": "#30343C", "accent": "#4493F8", "accent_hover": "#2F81F7",
        "danger": "#FF6B66", "danger_soft": "#49292C",
        "card": "#24272D", "card_line": "#3A3F48",
        "card_text": "#F0F1F2", "card_muted": "#A7ABB3",
        "pill": "#26384F", "btn": "#4493F8", "btn_hover": "#2F81F7",
        "btn_text": "#FFFFFF", "panel": "#24272D",
    },
    "light": {
        "bg": "#F6F8FA", "halo": "#EDF1F5",
        "shadow_far": "#E7EBF0", "shadow_near": "#DDE3EA",
        "bar": "#FFFFFF", "line": "#D0D7DE",
        "text": "#1F2328", "muted": "#656D76", "faint": "#8C959F",
        "hover": "#EAEEF2", "accent": "#0969DA", "accent_hover": "#0550AE",
        "danger": "#CF222E", "danger_soft": "#FFEBE9",
        "card": "#FFFFFF", "card_line": "#D0D7DE",
        "card_text": "#1F2328", "card_muted": "#656D76",
        "pill": "#DDF4FF", "btn": "#0969DA", "btn_hover": "#0550AE",
        "btn_text": "#FFFFFF", "panel": "#FFFFFF",
    },
}

F_TITLE = ("Segoe UI Semibold", 8)
F_VERSION = ("Segoe UI", 7)
F_PILL = ("Segoe UI Semibold", 8)
F_H1 = ("Segoe UI Semibold", 17)
F_H2 = ("Segoe UI Semibold", 12)
F_BODY = ("Segoe UI", 10)
F_SMALL = ("Segoe UI", 8)
F_BTN = ("Segoe UI Semibold", 11)
F_THEME_ICON = ("Segoe UI Symbol", 11)


def config_path():
    return Path(os.environ.get("APPDATA") or os.path.expanduser("~")) / "PWL" / "config.json"


def load_config():
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data):
    try:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
              x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def soft_elevation(canvas, x1, y1, x2, y2, r, theme, spread=3):
    for pad, color in ((spread*6, theme["shadow_far"]), (spread*3, theme["shadow_near"])):
        rounded_rect(canvas, x1-pad, y1-pad+pad/2, x2+pad, y2+pad+pad/2,
                     r+pad/2, fill=color, outline="")


class CanvasButton:
    counter = 0
    def __init__(self, canvas, cx, cy, w, h, text, command, theme,
                 radius=14, fill=None, hover=None, fg=None, font=F_BTN, outline=""):
        CanvasButton.counter += 1
        tag = f"cbtn{CanvasButton.counter}"
        self.canvas, self.command = canvas, command
        self.fill, self.hover = fill or theme["btn"], hover or theme["btn_hover"]
        x1, y1 = cx-w/2, cy-h/2
        self.shape = rounded_rect(canvas, x1, y1, x1+w, y1+h, radius,
                                  fill=self.fill, outline=outline, tags=tag)
        canvas.create_text(cx, cy, text=text, fill=fg or theme["btn_text"], font=font, tags=tag)
        canvas.tag_bind(tag, "<Enter>", self._enter)
        canvas.tag_bind(tag, "<Leave>", self._leave)
        canvas.tag_bind(tag, "<ButtonRelease-1>", lambda _e: self.command())
    def _enter(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.hover)
        self.canvas.configure(cursor="hand2")
    def _leave(self, _e):
        self.canvas.itemconfigure(self.shape, fill=self.fill)
        self.canvas.configure(cursor="")


def window_handle(root):
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    return hwnd or root.winfo_id()


def strip_native_caption(root):
    if not IS_WINDOWS:
        root.overrideredirect(True)
        return
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_THICKFRAME = 0x00040000
    SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020
    user32 = ctypes.windll.user32
    hwnd = window_handle(root)
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    user32.SetWindowLongW(hwnd, GWL_STYLE,
                          (style & ~WS_CAPTION) | WS_SYSMENU | WS_MINIMIZEBOX | WS_THICKFRAME)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)


def round_top_corners(root, w, h, radius=CORNER_RADIUS):
    if not IS_WINDOWS:
        return
    gdi32 = ctypes.windll.gdi32
    top = gdi32.CreateRoundRectRgn(0, 0, w+1, h+1, radius*2, radius*2)
    bottom = gdi32.CreateRectRgn(0, radius, w+1, h+1)
    gdi32.CombineRgn(top, top, bottom, 2)
    gdi32.DeleteObject(bottom)
    ctypes.windll.user32.SetWindowRgn(window_handle(root), top, True)


class PwlApp:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.theme_name = self.config.get("theme", "dark")
        self.screen = "workspace" if self.config.get("accepted") else "welcome"
        self._drag = (0, 0)
        self._region = None
        self._region_job = None
        self.hotkeys = {}
        self.body = None

        root.title(APP_TITLE)
        root.attributes("-alpha", 0.0)
        self._center()
        self.build_ui()
        root.bind("<Escape>", lambda _e: self.close())
        root.bind("<Return>", self._on_enter)
        root.bind("<Control-KeyPress>", self._on_control_key)
        root.bind("<Configure>", self._on_configure)
        root.after(20, self._apply_chrome)
        root.after(60, self._fade_in)

    @property
    def theme(self):
        return THEMES[self.theme_name]

    def _center(self):
        x = int((self.root.winfo_screenwidth()-WINDOW_W)/2)
        y = int((self.root.winfo_screenheight()-WINDOW_H)/2)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{max(y, 0)}")

    def _fade_in(self, value=0.0):
        value = min(value+0.12, 1.0)
        try:
            self.root.attributes("-alpha", value)
        except Exception:
            return
        if value < 1:
            self.root.after(12, lambda: self._fade_in(value))

    def _apply_chrome(self):
        strip_native_caption(self.root)
        self.root.after(40, lambda: self._refresh_region(True))

    def _on_configure(self, event):
        # Tk sends Configure for every child too. Ignore them and position-only moves.
        if event.widget is not self.root:
            return
        size = (event.width, event.height)
        if size == self._region or min(size) < 10:
            return
        if self._region_job:
            self.root.after_cancel(self._region_job)
        self._region_job = self.root.after(50, lambda: self._refresh_region(True))

    def _refresh_region(self, force=False):
        self._region_job = None
        size = (self.root.winfo_width(), self.root.winfo_height())
        if min(size) >= 10 and (force or size != self._region):
            self._region = size
            round_top_corners(self.root, *size)

    def minimize(self): self.root.iconify()
    def close(self): self.root.destroy()

    def _on_control_key(self, event):
        action = self.hotkeys.get(event.keycode)
        if action:
            action()
            return "break"

    def _on_enter(self, _event):
        if self.screen == "welcome":
            self.on_accept()

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.config["theme"] = self.theme_name
        save_config(self.config)
        self.build_ui()

    def build_ui(self):
        theme = self.theme
        self.root.configure(bg=theme["bg"])
        if self.body:
            self.body.destroy()
        self.body = tk.Frame(self.root, bg=theme["bg"])
        self.body.pack(fill="both", expand=True)
        self._build_titlebar()
        self.content = tk.Frame(self.body, bg=theme["bg"])
        self.content.pack(fill="both", expand=True)
        self.show_welcome() if self.screen == "welcome" else self.show_workspace()

    def _build_titlebar(self):
        theme = self.theme
        bar = tk.Frame(self.body, bg=theme["bar"], height=TITLEBAR_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        logo = tk.Canvas(bar, bg=theme["bar"], width=12, height=12, highlightthickness=0)
        logo.pack(side="left", padx=(8,6))
        rounded_rect(logo, 0,0,12,12,4, fill=theme["accent"], outline="")
        logo.create_text(6,6, text="P", fill="#FFFFFF", font=("Segoe UI Semibold",6))
        title = tk.Label(bar, text=APP_TITLE, bg=theme["bar"], fg=theme["text"], font=F_TITLE)
        title.pack(side="left")
        version = tk.Label(bar, text=f"v{APP_VERSION}", bg=theme["bar"], fg=theme["faint"], font=F_VERSION)
        version.pack(side="left", padx=(6,0))
        self._control(bar, "✕", self.close, theme["danger"], theme["danger_soft"])
        self._control(bar, "–", self.minimize, theme["muted"], theme["hover"])
        self._theme_switch(bar)
        tk.Frame(self.body, bg=theme["line"], height=1).pack(fill="x", side="top")
        for widget in (bar, title, version, logo):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _control(self, bar, glyph, command, fg, hover_bg):
        theme = self.theme
        btn = tk.Label(bar, text=glyph, bg=theme["bar"], fg=fg,
                       font=("Segoe UI",8), width=4, cursor="hand2")
        btn.pack(side="right", fill="y")
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover_bg, fg=theme["text"]))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=theme["bar"], fg=fg))

    def _theme_switch(self, bar):
        theme = self.theme
        cell = tk.Canvas(bar, bg=theme["bar"], width=30, height=TITLEBAR_H,
                         highlightthickness=0, cursor="hand2")
        cell.pack(side="right", fill="y")
        # System font glyphs are rasterized by Windows and stay sharper than thin Canvas arcs.
        glyph = "☀" if self.theme_name == "dark" else "☾"
        def render(bg, fg):
            cell.delete("all")
            cell.configure(bg=bg)
            cell.create_text(15, TITLEBAR_H//2, text=glyph, fill=fg, font=F_THEME_ICON)
        render(theme["bar"], theme["text"])
        cell.bind("<Enter>", lambda _e: render(theme["hover"], theme["accent"]))
        cell.bind("<Leave>", lambda _e: render(theme["bar"], theme["text"]))
        cell.bind("<Button-1>", lambda _e: self.toggle_theme())

    def _start_drag(self, event):
        # Stable 0.1-style drag. No SendMessage/Win32 move loop: that caused the silent crash.
        self._drag = (event.x_root-self.root.winfo_x(), event.y_root-self.root.winfo_y())

    def _on_drag(self, event):
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root-dx}+{event.y_root-dy}")

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
            t = self.theme
            canvas.delete("all")
            w,h = canvas.winfo_width(), canvas.winfo_height()
            cw,ch = 460,330
            x1,y1 = (w-cw)/2,(h-ch)/2-10
            x2,y2,cx = x1+cw,y1+ch,w/2
            rounded_rect(canvas,x1-70,y1-50,x2+70,y2+50,90,fill=t["halo"],outline="")
            soft_elevation(canvas,x1,y1,x2,y2,CARD_RADIUS,t)
            rounded_rect(canvas,x1,y1,x2,y2,CARD_RADIUS,fill=t["card"],outline=t["card_line"])
            rounded_rect(canvas,cx-76,y1+30,cx+76,y1+54,12,fill=t["pill"],outline="")
            canvas.create_text(cx,y1+42,text="PERFECT WORLD",fill=t["accent"],font=F_PILL)
            canvas.create_text(cx,y1+86,text="Добро пожаловать в PWL",fill=t["card_text"],font=F_H1)
            canvas.create_text(cx,y1+124,text="Автоматический вход в аккаунт без .bat-файлов\nи ручного ввода паролей",
                               fill=t["card_muted"],font=F_BODY,justify="center")
            canvas.create_line(x1+46,y1+168,x2-46,y1+168,fill=t["card_line"])
            canvas.create_text(cx,y1+206,text="Добавьте прямо сейчас свой\nпервый сервер и аккаунт",
                               fill=t["card_text"],font=F_H2,justify="center")
            CanvasButton(canvas,cx,y1+276,232,44,"Принять",self.on_accept,t,radius=14)
            canvas.create_text(cx,y2+30,text=f"v{APP_VERSION}",fill=t["faint"],font=F_SMALL)
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
            t = self.theme
            canvas.delete("all")
            w,h = canvas.winfo_width(),canvas.winfo_height()
            cx = w/2
            canvas.create_text(40,42,text="Серверы и аккаунты",anchor="w",fill=t["text"],font=F_H1)
            canvas.create_text(40,68,text="Управляйте входом в любой из своих аккаунтов",anchor="w",fill=t["muted"],font=F_BODY)
            bw,bh = 520,250
            x1,y1 = (w-bw)/2,(h-bh)/2+16
            x2,y2 = x1+bw,y1+bh
            soft_elevation(canvas,x1,y1,x2,y2,24,t,spread=2)
            rounded_rect(canvas,x1,y1,x2,y2,24,fill=t["panel"],outline=t["card_line"])
            gx,gy = cx,y1+62
            rounded_rect(canvas,gx-26,gy-20,gx+26,gy+20,12,fill=t["pill"],outline="")
            canvas.create_line(gx-12,gy,gx+12,gy,fill=t["accent"],width=2,capstyle="round")
            canvas.create_line(gx,gy-12,gx,gy+12,fill=t["accent"],width=2,capstyle="round")
            canvas.create_text(cx,y1+118,text="Здесь пока пусто",fill=t["text"],font=F_H2)
            canvas.create_text(cx,y1+146,text="Добавьте первый сервер, чтобы начать",fill=t["muted"],font=F_BODY)
            CanvasButton(canvas,cx,y1+198,232,44,"+   Добавить сервер",lambda:None,t,radius=14,
                         fill=t["accent"],hover=t["accent_hover"],fg="#FFFFFF")
            canvas.create_text(w-40,h-26,text=f"v{APP_VERSION}",anchor="e",fill=t["faint"],font=F_SMALL)
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
