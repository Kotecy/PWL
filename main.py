"""PWL by Kotecy - UI mockup.

A frameless dark window with a custom title bar and a welcome card.
The "Принять" button closes the card and opens the (empty) workspace.
The choice is remembered in %APPDATA%/PWL/config.json.
"""

import json
import os
import tkinter as tk
from pathlib import Path

APP_TITLE = "PWL by Kotecy"

WINDOW_W = 940
WINDOW_H = 870
TITLEBAR_H = 52

COLOR_BG = "#0B0B0D"
COLOR_TITLEBAR = "#000000"
COLOR_BORDER = "#FFFFFF"
COLOR_TEXT = "#FFFFFF"
COLOR_MUTED = "#8A8A8F"
COLOR_CARD = "#D2D2D2"
COLOR_CARD_TEXT = "#000000"
COLOR_BTN = "#000000"
COLOR_BTN_HOVER = "#1E1E22"
COLOR_MIN = "#2F80ED"
COLOR_CLOSE = "#E03131"

FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_CARD = ("Segoe UI", 14, "bold")
FONT_BTN = ("Segoe UI", 12, "bold")
FONT_HINT = ("Segoe UI", 11)


def config_path() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / "PWL" / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class PwlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = load_config()
        self._drag = (0, 0)

        root.title(APP_TITLE)
        root.overrideredirect(True)
        root.configure(bg=COLOR_BORDER)
        self._center()

        outer = tk.Frame(root, bg=COLOR_BORDER)
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        self.body = tk.Frame(outer, bg=COLOR_BG)
        self.body.pack(fill="both", expand=True)

        self._build_titlebar()
        self._build_content()

        root.bind("<Map>", self._on_map)
        root.bind("<Escape>", lambda _e: self.close())

        if self.config.get("accepted"):
            self.show_workspace()
        else:
            self.show_welcome()

    def _center(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = int((sw - WINDOW_W) / 2)
        y = int((sh - WINDOW_H) / 2)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{max(y, 0)}")

    def _build_titlebar(self):
        bar = tk.Frame(self.body, bg=COLOR_TITLEBAR, height=TITLEBAR_H)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        self.titlebar = bar

        logo = tk.Frame(bar, bg="#D9D9D9", width=28, height=28)
        logo.pack(side="left", padx=(14, 12))
        logo.pack_propagate(False)

        label = tk.Label(bar, text=APP_TITLE, bg=COLOR_TITLEBAR, fg=COLOR_TEXT, font=FONT_TITLE)
        label.pack(side="left")

        close = tk.Label(bar, text="\u2715", bg=COLOR_TITLEBAR, fg=COLOR_CLOSE,
                         font=("Segoe UI", 16, "bold"), width=4)
        close.pack(side="right", fill="y")
        close.bind("<Button-1>", lambda _e: self.close())
        close.bind("<Enter>", lambda _e: close.configure(bg="#2A0F0F"))
        close.bind("<Leave>", lambda _e: close.configure(bg=COLOR_TITLEBAR))

        sep1 = tk.Frame(bar, bg="#333338", width=1)
        sep1.pack(side="right", fill="y", pady=6)

        minimize = tk.Label(bar, text="\u2014", bg=COLOR_TITLEBAR, fg=COLOR_MIN,
                            font=("Segoe UI", 14, "bold"), width=4)
        minimize.pack(side="right", fill="y")
        minimize.bind("<Button-1>", lambda _e: self.minimize())
        minimize.bind("<Enter>", lambda _e: minimize.configure(bg="#101828"))
        minimize.bind("<Leave>", lambda _e: minimize.configure(bg=COLOR_TITLEBAR))

        sep2 = tk.Frame(bar, bg="#333338", width=1)
        sep2.pack(side="right", fill="y", pady=6)

        for widget in (bar, label, logo):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _build_content(self):
        self.content = tk.Frame(self.body, bg=COLOR_BG)
        self.content.pack(fill="both", expand=True)

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_welcome(self):
        self._clear_content()
        canvas = tk.Canvas(self.content, bg=COLOR_BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        accept = tk.Button(
            canvas, text="\u041f\u0440\u0438\u043d\u044f\u0442\u044c", command=self.on_accept,
            bg=COLOR_BTN, fg=COLOR_TEXT, activebackground=COLOR_BTN_HOVER,
            activeforeground=COLOR_TEXT, font=FONT_BTN, relief="flat",
            bd=0, cursor="hand2", highlightthickness=0,
        )
        accept.bind("<Enter>", lambda _e: accept.configure(bg=COLOR_BTN_HOVER))
        accept.bind("<Leave>", lambda _e: accept.configure(bg=COLOR_BTN))

        def draw(_event=None):
            canvas.delete("all")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            cw, ch = 452, 256
            x1 = (w - cw) / 2
            y1 = (h - ch) / 2
            rounded_rect(canvas, x1, y1, x1 + cw, y1 + ch, 26, fill=COLOR_CARD, outline="")

            cx = w / 2
            canvas.create_text(
                cx, y1 + 62,
                text=(
                    "\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0432 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0443\n"
                    "\u0434\u043b\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0432\u0445\u043e\u0434\u0430\n"
                    "\u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442 Perfect World"
                ),
                fill=COLOR_CARD_TEXT, font=FONT_CARD, justify="center",
            )
            canvas.create_text(
                cx, y1 + 148,
                text=(
                    "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043f\u0440\u044f\u043c\u043e \u0441\u0435\u0439\u0447\u0430\u0441 \u0441\u0432\u043e\u0439\n"
                    "\u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u0435\u0440\u0432\u0435\u0440 \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442 !"
                ),
                fill=COLOR_CARD_TEXT, font=FONT_CARD, justify="center",
            )
            canvas.create_window(cx, y1 + 210, window=accept, width=220, height=34)

        canvas.bind("<Configure>", draw)
        self.root.after(50, draw)

    def on_accept(self):
        self.config["accepted"] = True
        save_config(self.config)
        self.show_workspace()

    def show_workspace(self):
        self._clear_content()
        wrap = tk.Frame(self.content, bg=COLOR_BG)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            wrap, text="\u0421\u0435\u0440\u0432\u0435\u0440\u044b \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u044b",
            bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 16, "bold"),
        ).pack(pady=(0, 6))

        tk.Label(
            wrap,
            text="\u0417\u0434\u0435\u0441\u044c \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0441\u043f\u0438\u0441\u043e\u043a \u0432\u0430\u0448\u0438\u0445 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u043e\u0432",
            bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_HINT,
        ).pack(pady=(0, 22))

        add = tk.Button(
            wrap, text="+  \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0435\u0440\u0432\u0435\u0440",
            bg=COLOR_CARD, fg=COLOR_CARD_TEXT, activebackground="#BFBFBF",
            font=FONT_BTN, relief="flat", bd=0, cursor="hand2",
            highlightthickness=0, padx=26, pady=9,
            command=lambda: None,
        )
        add.pack()

    def _start_drag(self, event):
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def minimize(self):
        self.root.overrideredirect(False)
        self.root.iconify()

    def _on_map(self, _event):
        if self.root.state() == "normal":
            self.root.overrideredirect(True)

    def close(self):
        self.root.destroy()


def main():
    root = tk.Tk()
    PwlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
