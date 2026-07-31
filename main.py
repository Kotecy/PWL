"""PWL by Kotecy — stable borderless Windows UI."""
import json
import os
import sys
import tkinter as tk
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import ctypes

APP_TITLE = "PWL by Kotecy"
APP_VERSION = "0.2.3"
WINDOW_W, WINDOW_H = 900, 620
TITLEBAR_H = 22
CORNER_RADIUS = 20
CARD_RADIUS = 30

VK = {letter: ord(letter) for letter in "ADEF LNQRSTW" if letter != " "}

THEMES = {
    "dark": {
        "bg":"#1B1D21", "halo":"#202329", "shadow_far":"#17191D",
        "shadow_near":"#202329", "bar":"#24272D", "line":"#3A3F48",
        "text":"#F0F1F2", "muted":"#A7ABB3", "faint":"#6F747D",
        "hover":"#30343C", "accent":"#4493F8", "accent_hover":"#2F81F7",
        "danger":"#FF6B66", "danger_soft":"#49292C", "card":"#24272D",
        "card_line":"#3A3F48", "card_text":"#F0F1F2", "card_muted":"#A7ABB3",
        "pill":"#26384F", "btn":"#4493F8", "btn_hover":"#2F81F7",
        "btn_text":"#FFFFFF", "panel":"#24272D"
    },
    "light": {
        "bg":"#F6F8FA", "halo":"#EDF1F5", "shadow_far":"#E7EBF0",
        "shadow_near":"#DDE3EA", "bar":"#FFFFFF", "line":"#D0D7DE",
        "text":"#1F2328", "muted":"#656D76", "faint":"#9AA1AA",
        "hover":"#EAEEF2", "accent":"#0969DA", "accent_hover":"#0550AE",
        "danger":"#CF222E", "danger_soft":"#FFEBE9", "card":"#FFFFFF",
        "card_line":"#D0D7DE", "card_text":"#1F2328", "card_muted":"#656D76",
        "pill":"#DDF4FF", "btn":"#0969DA", "btn_hover":"#0550AE",
        "btn_text":"#FFFFFF", "panel":"#FFFFFF"
    }
}

F_TITLE=("Segoe UI Semibold",8); F_PILL=("Segoe UI Semibold",8)
F_H1=("Segoe UI Semibold",17); F_H2=("Segoe UI Semibold",12)
F_BODY=("Segoe UI",10); F_SMALL=("Segoe UI",8); F_VERSION=("Segoe UI",7)
F_BTN=("Segoe UI Semibold",11); F_THEME=("Segoe UI Symbol",11)


def config_path():
    return Path(os.environ.get("APPDATA") or os.path.expanduser("~"))/"PWL"/"config.json"


def load_config():
    try: return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception: return {}


def save_config(data):
    try:
        p=config_path(); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception: pass


def rounded_rect(c,x1,y1,x2,y2,r,**kw):
    pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
         x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    return c.create_polygon(pts,smooth=True,**kw)


def soft_elevation(c,x1,y1,x2,y2,r,t,spread=3):
    for pad,color in ((spread*6,t["shadow_far"]),(spread*3,t["shadow_near"])):
        rounded_rect(c,x1-pad,y1-pad+pad/2,x2+pad,y2+pad+pad/2,r+pad/2,
                     fill=color,outline="")


class CanvasButton:
    counter=0
    def __init__(self,c,cx,cy,w,h,text,command,t,radius=14,fill=None,hover=None,fg=None):
        CanvasButton.counter+=1; tag=f"cbtn{CanvasButton.counter}"
        self.c=c; self.fill=fill or t["btn"]; self.hover=hover or t["btn_hover"]
        x1,y1=cx-w/2,cy-h/2
        self.shape=rounded_rect(c,x1,y1,x1+w,y1+h,radius,fill=self.fill,outline="",tags=tag)
        c.create_text(cx,cy,text=text,fill=fg or t["btn_text"],font=F_BTN,tags=tag)
        c.tag_bind(tag,"<Enter>",self.enter); c.tag_bind(tag,"<Leave>",self.leave)
        c.tag_bind(tag,"<ButtonRelease-1>",lambda _e:command())
    def enter(self,_e):
        self.c.itemconfigure(self.shape,fill=self.hover); self.c.configure(cursor="hand2")
    def leave(self,_e):
        self.c.itemconfigure(self.shape,fill=self.fill); self.c.configure(cursor="")


def window_handle(root):
    root.update_idletasks()
    hwnd=ctypes.windll.user32.GetParent(root.winfo_id())
    return hwnd or root.winfo_id()


def show_in_taskbar(root):
    """Exact taskbar setup used by the stable 0.1 window."""
    if not IS_WINDOWS: return
    GWL_EXSTYLE=-20; WS_EX_APPWINDOW=0x00040000; WS_EX_TOOLWINDOW=0x00000080
    user32=ctypes.windll.user32; hwnd=window_handle(root)
    style=user32.GetWindowLongW(hwnd,GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd,GWL_EXSTYLE,(style & ~WS_EX_TOOLWINDOW)|WS_EX_APPWINDOW)
    root.withdraw(); root.after(10,root.deiconify)


def round_top_corners(root,w,h,radius=CORNER_RADIUS):
    if not IS_WINDOWS: return
    gdi=ctypes.windll.gdi32; hwnd=window_handle(root)
    top=gdi.CreateRoundRectRgn(0,0,w+1,h+1,radius*2,radius*2)
    bottom=gdi.CreateRectRgn(0,radius,w+1,h+1)
    gdi.CombineRgn(top,top,bottom,2); gdi.DeleteObject(bottom)
    ctypes.windll.user32.SetWindowRgn(hwnd,top,True)


class PwlApp:
    def __init__(self,root):
        self.root=root; self.config=load_config()
        self.theme_name=self.config.get("theme","dark")
        self.screen="workspace" if self.config.get("accepted") else "welcome"
        self._drag=(0,0); self._region=None; self.hotkeys={}; self.body=None
        root.title(APP_TITLE)
        # Restored verbatim from 0.1: do not mutate GWL_STYLE/client geometry.
        root.overrideredirect(True)
        root.attributes("-alpha",0.0)
        self.center(); self.build_ui()
        root.bind("<Escape>",lambda _e:self.close())
        root.bind("<Return>",self.on_enter)
        root.bind("<Control-KeyPress>",self.on_control_key)
        root.bind("<Configure>",lambda _e:self.refresh_region())
        root.after(30,self.apply_chrome); root.after(60,self.fade_in)

    @property
    def theme(self): return THEMES[self.theme_name]

    def center(self):
        x=int((self.root.winfo_screenwidth()-WINDOW_W)/2)
        y=int((self.root.winfo_screenheight()-WINDOW_H)/2)
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{max(y,0)}")

    def fade_in(self,value=0.0):
        value=min(value+0.12,1.0)
        try: self.root.attributes("-alpha",value)
        except Exception: return
        if value<1: self.root.after(12,lambda:self.fade_in(value))

    def apply_chrome(self):
        show_in_taskbar(self.root)
        self.root.after(60,lambda:self.refresh_region(True))

    def refresh_region(self,force=False):
        size=(self.root.winfo_width(),self.root.winfo_height())
        if min(size)<10:return
        if force or size!=self._region:
            self._region=size; round_top_corners(self.root,*size)

    def minimize(self):
        if IS_WINDOWS: ctypes.windll.user32.ShowWindow(window_handle(self.root),6)
        else:
            self.root.overrideredirect(False); self.root.iconify()

    def close(self): self.root.destroy()

    def on_control_key(self,event):
        action=self.hotkeys.get(event.keycode)
        if action: action(); return "break"

    def on_enter(self,_e):
        if self.screen=="welcome": self.on_accept()

    def toggle_theme(self):
        self.theme_name="light" if self.theme_name=="dark" else "dark"
        self.config["theme"]=self.theme_name; save_config(self.config); self.build_ui()

    def build_ui(self):
        t=self.theme; self.root.configure(bg=t["bg"])
        if self.body:self.body.destroy()
        self.body=tk.Frame(self.root,bg=t["bg"]); self.body.pack(fill="both",expand=True)
        self.build_titlebar()
        self.content=tk.Frame(self.body,bg=t["bg"]); self.content.pack(fill="both",expand=True)
        self.show_welcome() if self.screen=="welcome" else self.show_workspace()

    def build_titlebar(self):
        t=self.theme
        bar=tk.Frame(self.body,bg=t["bar"],height=TITLEBAR_H)
        bar.pack(fill="x",side="top"); bar.pack_propagate(False)
        logo=tk.Canvas(bar,bg=t["bar"],width=12,height=12,highlightthickness=0)
        logo.pack(side="left",padx=(8,6))
        rounded_rect(logo,0,0,12,12,4,fill=t["accent"],outline="")
        logo.create_text(6,6,text="P",fill="#FFF",font=("Segoe UI Semibold",6))
        title=tk.Label(bar,text=APP_TITLE,bg=t["bar"],fg=t["text"],font=F_TITLE)
        title.pack(side="left")
        self.control(bar,"✕",self.close,t["danger"],t["danger_soft"])
        self.control(bar,"–",self.minimize,t["muted"],t["hover"])
        self.theme_switch(bar)
        tk.Frame(self.body,bg=t["line"],height=1).pack(fill="x",side="top")
        for widget in (bar,title,logo):
            widget.bind("<Button-1>",self.start_drag)
            widget.bind("<B1-Motion>",self.drag)

    def control(self,bar,glyph,command,fg,hover):
        t=self.theme
        b=tk.Label(bar,text=glyph,bg=t["bar"],fg=fg,font=("Segoe UI",8),width=4,cursor="hand2")
        b.pack(side="right",fill="y"); b.bind("<Button-1>",lambda _e:command())
        b.bind("<Enter>",lambda _e:b.configure(bg=hover,fg=t["text"]))
        b.bind("<Leave>",lambda _e:b.configure(bg=t["bar"],fg=fg))

    def theme_switch(self,bar):
        t=self.theme
        c=tk.Canvas(bar,bg=t["bar"],width=30,height=TITLEBAR_H,highlightthickness=0,cursor="hand2")
        c.pack(side="right",fill="y"); glyph="☀" if self.theme_name=="dark" else "☾"
        def render(bg,fg):
            c.delete("all"); c.configure(bg=bg)
            c.create_text(15,TITLEBAR_H//2,text=glyph,fill=fg,font=F_THEME)
        render(t["bar"],t["text"])
        c.bind("<Enter>",lambda _e:render(t["hover"],t["accent"]))
        c.bind("<Leave>",lambda _e:render(t["bar"],t["text"]))
        c.bind("<Button-1>",lambda _e:self.toggle_theme())

    def start_drag(self,event):
        self._drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())

    def drag(self,event):
        dx,dy=self._drag
        self.root.geometry(f"+{event.x_root-dx}+{event.y_root-dy}")

    def new_canvas(self):
        for child in self.content.winfo_children():child.destroy()
        c=tk.Canvas(self.content,bg=self.theme["bg"],highlightthickness=0)
        c.pack(fill="both",expand=True); return c

    def show_welcome(self):
        self.screen="welcome"; c=self.new_canvas()
        def draw(_e=None):
            t=self.theme; c.delete("all"); w,h=c.winfo_width(),c.winfo_height()
            cw,ch=460,330; x1,y1=(w-cw)/2,(h-ch)/2-8; x2,y2=x1+cw,y1+ch; cx=w/2
            rounded_rect(c,x1-70,y1-50,x2+70,y2+50,90,fill=t["halo"],outline="")
            soft_elevation(c,x1,y1,x2,y2,CARD_RADIUS,t)
            rounded_rect(c,x1,y1,x2,y2,CARD_RADIUS,fill=t["card"],outline=t["card_line"])
            rounded_rect(c,cx-76,y1+30,cx+76,y1+54,12,fill=t["pill"],outline="")
            c.create_text(cx,y1+42,text="PERFECT WORLD",fill=t["accent"],font=F_PILL)
            c.create_text(cx,y1+86,text="Добро пожаловать в PWL",fill=t["card_text"],font=F_H1)
            c.create_text(cx,y1+124,text="Автоматический вход в аккаунт без .bat-файлов\nи ручного ввода паролей",
                          fill=t["card_muted"],font=F_BODY,justify="center")
            c.create_line(x1+46,y1+168,x2-46,y1+168,fill=t["card_line"])
            c.create_text(cx,y1+206,text="Добавьте прямо сейчас свой\nпервый сервер и аккаунт",
                          fill=t["card_text"],font=F_H2,justify="center")
            CanvasButton(c,cx,y1+276,232,44,"Принять",self.on_accept,t)
            # Before acceptance the version exists only beneath the confirmation card.
            c.create_text(cx,y2+34,text=f"v{APP_VERSION}",fill=t["faint"],font=F_VERSION)
        c.bind("<Configure>",draw); self.root.after(40,draw)

    def on_accept(self):
        self.config["accepted"]=True; save_config(self.config); self.show_workspace()

    def show_workspace(self):
        self.screen="workspace"; c=self.new_canvas()
        def draw(_e=None):
            t=self.theme; c.delete("all"); w,h=c.winfo_width(),c.winfo_height(); cx=w/2
            c.create_text(40,42,text="Серверы и аккаунты",anchor="w",fill=t["text"],font=F_H1)
            c.create_text(40,68,text="Управляйте входом в любой из своих аккаунтов",anchor="w",fill=t["muted"],font=F_BODY)
            bw,bh=520,250; x1,y1=(w-bw)/2,(h-bh)/2+16; x2,y2=x1+bw,y1+bh
            soft_elevation(c,x1,y1,x2,y2,24,t,2)
            rounded_rect(c,x1,y1,x2,y2,24,fill=t["panel"],outline=t["card_line"])
            gx,gy=cx,y1+62
            rounded_rect(c,gx-26,gy-20,gx+26,gy+20,12,fill=t["pill"],outline="")
            c.create_line(gx-12,gy,gx+12,gy,fill=t["accent"],width=2,capstyle="round")
            c.create_line(gx,gy-12,gx,gy+12,fill=t["accent"],width=2,capstyle="round")
            c.create_text(cx,y1+118,text="Здесь пока пусто",fill=t["text"],font=F_H2)
            c.create_text(cx,y1+146,text="Добавьте первый сервер, чтобы начать",fill=t["muted"],font=F_BODY)
            CanvasButton(c,cx,y1+198,232,44,"+   Добавить сервер",lambda:None,t,
                         fill=t["accent"],hover=t["accent_hover"],fg="#FFF")
            # After acceptance: always present, subdued, bottom-right.
            c.create_text(w-18,h-14,text=f"v{APP_VERSION}",anchor="se",fill=t["faint"],font=F_VERSION)
        c.bind("<Configure>",draw); self.root.after(40,draw)


def main():
    if IS_WINDOWS:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root=tk.Tk(); PwlApp(root); root.mainloop()


if __name__=="__main__": main()
