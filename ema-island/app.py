"""EMA Island: EMA Lightning TTS living in the MacBook notch.

Run:  .venv/bin/python ema-island/app.py

A borderless, transparent, always-on-top Tk window sits on top of the menu bar, centered on the
notch. Collapsed it is a black pill hugging the notch; hovering springs it open into a small panel
with the text box, player and voice settings. Moving the pointer away folds it back.

Tk can't do this alone, so a tiny ctypes bridge to the Objective-C runtime raises the window above
the menu bar, lets the borderless window take keyboard focus, and reads the notch size.
"""
import ctypes
import ctypes.util
import math
import platform
import queue
import random
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog

import numpy as np
import sounddevice as sd

HERE = Path(__file__).resolve().parent
REPO_URL = "https://github.com/kaanklcrsln/ema-lightning-gui"


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# ---------- palette ----------
ISLAND = "#000000"  # matches the notch
TEXT = "#FBFEF9"
MUTED = blend(ISLAND, TEXT, 0.55)
DIM = blend(ISLAND, TEXT, 0.32)
FIELD = blend(ISLAND, TEXT, 0.08)
CHIP = blend(ISLAND, TEXT, 0.12)
CHIP_HI = blend(ISLAND, TEXT, 0.2)
LINE = blend(ISLAND, TEXT, 0.18)
WAVE = blend(ISLAND, TEXT, 0.28)
DANGER = "#FF8F8F"
THEMES = {"Mavi": "#8EC5FF", "Yeşil": "#93E2B0", "Turuncu": "#FFAE85", "Mor": "#C4A7FF"}

RATES = (8000, 16000, 24000, 48000)
SPEED_MIN, SPEED_MAX = 0.25, 4.0

WING = 42  # collapsed pill width on each side of the notch
EXP_W = 460  # expanded island width
NSWindowLevel = 26  # one above the menu bar (NSMainMenuWindowLevel = 24, NSStatusWindowLevel = 25)

# GitHub mark (Primer Octicons mark-github-16, MIT), 16x16 viewBox
GITHUB_PATH = (
    "M6.766 11.328c-2.063-.25-3.516-1.734-3.516-3.656 0-.781.281-1.625.75-2.188-.203-.515-.172-1.609.063-2.062"
    ".625-.078 1.468.25 1.968.703.594-.187 1.219-.281 1.985-.281.765 0 1.39.094 1.953.265.484-.437 1.344-.765"
    " 1.969-.687.218.422.25 1.515.046 2.047.5.593.766 1.39.766 2.203 0 1.922-1.453 3.375-3.547 3.64.531.344.89"
    " 1.094.89 1.954v1.625c0 .468.391.734.86.547C13.781 14.359 16 11.53 16 8.03 16 3.61 12.406 0 7.984 0 3.563 0"
    " 0 3.61 0 8.031a7.88 7.88 0 0 0 5.172 7.422c.422.156.828-.125.828-.547v-1.25c-.219.094-.5.156-.75.156-1.031"
    " 0-1.64-.562-2.078-1.609-.172-.422-.36-.672-.719-.719-.187-.015-.25-.093-.25-.187 0-.188.313-.328.625-.328"
    ".453 0 .844.281 1.25.86.313.452.64.655 1.031.655s.641-.14 1-.5c.266-.265.47-.5.657-.656"
)


def svg_polygon(d, steps=6):
    """Flatten a single-contour SVG path (M L H V C S A Z) into polygon points."""
    toks = re.findall(r"[MmLlHhVvCcSsAaZz]|-?(?:\d+\.\d*|\.\d+|\d+)(?:e-?\d+)?", d)
    pts, i, cmd, x, y, ctrl = [], 0, "M", 0.0, 0.0, None

    def num():
        nonlocal i
        i += 1
        return float(toks[i - 1])

    def bezier(c1, c2, e):
        for k in range(1, steps + 1):
            t = k / steps
            u = 1 - t
            pts.append((u ** 3 * x + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * e[0],
                        u ** 3 * y + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * e[1]))

    def arc(rx, ry, large, sweep, ex, ey):  # rotation is 0 in this path
        hx, hy = (x - ex) / 2, (y - ey) / 2
        lam = hx * hx / (rx * rx) + hy * hy / (ry * ry)
        if lam > 1:
            rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
        num_ = rx * rx * ry * ry - rx * rx * hy * hy - ry * ry * hx * hx
        co = math.sqrt(max(num_ / (rx * rx * hy * hy + ry * ry * hx * hx), 0)) * (-1 if large == sweep else 1)
        cxp, cyp = co * rx * hy / ry, -co * ry * hx / rx
        cx, cy = cxp + (x + ex) / 2, cyp + (y + ey) / 2
        t1 = math.atan2((hy - cyp) / ry, (hx - cxp) / rx)
        dt = math.atan2((-hy - cyp) / ry, (-hx - cxp) / rx) - t1
        if sweep and dt < 0:
            dt += 2 * math.pi
        elif not sweep and dt > 0:
            dt -= 2 * math.pi
        n = max(4, int(abs(dt) / (math.pi / 16)))
        pts.extend((cx + rx * math.cos(t1 + dt * k / n), cy + ry * math.sin(t1 + dt * k / n)) for k in range(1, n + 1))

    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        c, rel = cmd.upper(), cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "Z":
            break
        if c == "M":
            x, y = ox + num(), oy + num()
            pts.append((x, y))
            cmd, ctrl = ("l" if rel else "L"), None
        elif c == "L":
            x, y = ox + num(), oy + num()
            pts.append((x, y))
            ctrl = None
        elif c == "H":
            x = ox + num()
            pts.append((x, y))
            ctrl = None
        elif c == "V":
            y = oy + num()
            pts.append((x, y))
            ctrl = None
        elif c in "CS":
            c1 = (ox + num(), oy + num()) if c == "C" else ((2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl else (x, y))
            c2, e = (ox + num(), oy + num()), (ox + num(), oy + num())
            bezier(c1, c2, e)
            x, y, ctrl = e[0], e[1], c2
        elif c == "A":
            rx, ry, _, large, sweep = num(), num(), num(), num(), num()
            ex, ey = ox + num(), oy + num()
            arc(rx, ry, large, sweep, ex, ey)
            x, y, ctrl = ex, ey, None
    return pts


GITHUB = svg_polygon(GITHUB_PATH)


# ---------- Objective-C bridge ----------
class Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]


class Insets(ctypes.Structure):
    _fields_ = [("top", ctypes.c_double), ("left", ctypes.c_double), ("bottom", ctypes.c_double),
                ("right", ctypes.c_double)]


class Cocoa:
    """Just enough Objective-C over ctypes to place and tame the Tk window (no PyObjC needed)."""

    def __init__(self):
        self.lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        for fn, rt, at in (("objc_getClass", ctypes.c_void_p, [ctypes.c_char_p]),
                           ("sel_registerName", ctypes.c_void_p, [ctypes.c_char_p]),
                           ("class_replaceMethod", ctypes.c_void_p,
                            [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p])):
            getattr(self.lib, fn).restype, getattr(self.lib, fn).argtypes = rt, at
        self.x86 = platform.machine() == "x86_64"  # large structs come back through objc_msgSend_stret there
        self._yes = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(lambda s, c: True)

    def cls(self, name):
        return self.lib.objc_getClass(name.encode())

    def send(self, obj, sel, *args, restype=ctypes.c_void_p, argtypes=()):
        big = isinstance(restype, type) and issubclass(restype, ctypes.Structure) and ctypes.sizeof(restype) > 16
        f = self.lib.objc_msgSend_stret if self.x86 and big else self.lib.objc_msgSend
        f.restype, f.argtypes = restype, [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
        return f(obj, self.lib.sel_registerName(sel.encode()), *args)

    def responds(self, obj, sel):
        return self.send(obj, "respondsToSelector:", self.lib.sel_registerName(sel.encode()),
                         restype=ctypes.c_bool, argtypes=(ctypes.c_void_p,))

    def allow_key_window(self):
        """Tk's borderless windows refuse keyboard focus; let them take it so the text box works."""
        tkwin = self.cls("TKWindow")
        if tkwin:
            for sel in (b"canBecomeKeyWindow", b"canBecomeMainWindow"):
                self.lib.class_replaceMethod(tkwin, self.lib.sel_registerName(sel),
                                             ctypes.cast(self._yes, ctypes.c_void_p), b"c@:")

    @property
    def app(self):
        return self.send(self.cls("NSApplication"), "sharedApplication")

    def notch(self):
        """(screen width, notch left x, notch right x, notch/menu-bar height) in points."""
        scr = self.send(self.cls("NSScreen"), "mainScreen")
        w = self.send(scr, "frame", restype=Rect).w
        top = self.send(scr, "safeAreaInsets", restype=Insets).top if self.responds(scr, "safeAreaInsets") else 0
        if top > 0 and self.responds(scr, "auxiliaryTopLeftArea"):
            left = self.send(scr, "auxiliaryTopLeftArea", restype=Rect).w
            right = self.send(scr, "auxiliaryTopRightArea", restype=Rect).w
            return w, left, w - right, top
        bar = self.send(self.send(self.cls("NSStatusBar"), "systemStatusBar"), "thickness", restype=ctypes.c_double)
        return w, w / 2 - 60, w / 2 + 60, bar or 24  # no notch: float a pill of the same idea at top center

    def float_windows(self):
        """Above the menu bar, on every Space and over full-screen apps, without a window shadow."""
        wins = self.send(self.app, "windows")
        for i in range(self.send(wins, "count", restype=ctypes.c_ulong)):
            w = self.send(wins, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,))
            self.send(w, "setLevel:", NSWindowLevel, argtypes=(ctypes.c_long,))
            self.send(w, "setCollectionBehavior:", (1 << 0) | (1 << 4) | (1 << 8), argtypes=(ctypes.c_ulong,))
            self.send(w, "setHasShadow:", False, argtypes=(ctypes.c_bool,))

    def accessory(self):
        """No Dock icon, like a menu bar utility."""
        self.send(self.app, "setActivationPolicy:", 1, argtypes=(ctypes.c_long,))

    def deactivate(self):
        """Hand keyboard focus back to the app that had it."""
        self.send(self.app, "deactivate")


# ---------- drawing helpers ----------
def pick_font(root, *names):
    fams = set(tkfont.families(root))
    for n in names:
        if n in fams:
            return n
    return "Helvetica"


def rrect(cv, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for k in range(9):
            a = math.radians(a0 + 90 * k / 8)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return cv.create_polygon(pts, **kw)


def island(cv, cx, w, h, r, s, **kw):
    """Notch-like shape hanging from the top edge: square top, rounded bottom (r), concave shoulders (s)."""
    lx, rx = cx - w / 2, cx + w / 2
    r = max(0, min(r, w / 2, h))
    pts = []

    def arc(ox, oy, rad, a0, a1, n=8):
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            pts.extend((ox + rad * math.cos(a), oy + rad * math.sin(a)))

    arc(lx - s, s, s, -90, 0)  # left shoulder
    arc(lx + r, h - r, r, 180, 90)  # bottom left
    arc(rx - r, h - r, r, 90, 0)  # bottom right
    arc(rx + s, s, s, 180, 270)  # right shoulder
    return cv.create_polygon(pts, **kw)


def draw_icon(cv, name, cx, cy, col, s=1.0, tags=()):
    """Line icons centered on (cx, cy), ~16px at s=1."""
    line = dict(fill=col, width=max(1.5, 2 * s), capstyle="round", joinstyle="round", tags=tags)

    def P(*xy):
        return [c + v * s for c, v in zip((cx, cy) * (len(xy) // 2), xy)]

    if name == "download":
        cv.create_line(*P(0, -8, 0, 3), **line)
        cv.create_line(*P(-5, -2, 0, 3, 5, -2), **line)
        cv.create_line(*P(-8, 3, -8, 8, 8, 8, 8, 3), **line)
    elif name == "dice":
        rrect(cv, *P(-8, -8, 8, 8), 4 * s, fill="", outline=col, width=line["width"], tags=tags)
        for dx, dy in ((-3.5, -3.5), (3.5, 3.5), (0, 0), (3.5, -3.5), (-3.5, 3.5)):
            cv.create_oval(*P(dx - 1.4, dy - 1.4, dx + 1.4, dy + 1.4), fill=col, outline="", tags=tags)
    elif name in ("lock", "unlock"):
        up = 0 if name == "lock" else 3
        cv.create_arc(*P(-5, -11 - up, 5, -1 - up), start=0, extent=180, style="arc", outline=col,
                      width=line["width"], tags=tags)
        cv.create_line(*P(-5, -6 - up, -5, -1), **line)
        cv.create_line(*P(5, -6 - up, 5, -1 - up * 2), **line)
        rrect(cv, *P(-7, -1, 7, 8), 3 * s, fill=col if name == "lock" else "", outline=col, width=line["width"],
              tags=tags)
    elif name == "github":
        cv.create_polygon([v for px, py in GITHUB for v in P(px - 8, py - 8)], fill=col, outline="", tags=tags)
    elif name == "power":
        cv.create_arc(*P(-7, -7, 7, 7), start=120, extent=300, style="arc", outline=col, width=line["width"],
                      tags=tags)
        cv.create_line(*P(0, -9, 0, -2), **line)
    elif name == "sliders":
        for y, k in ((-5, -3), (0, 4), (5, -1)):
            cv.create_line(*P(-8, y, 8, y), **line)
            cv.create_oval(*P(k - 2.4, y - 2.4, k + 2.4, y + 2.4), fill=ISLAND, outline=col, width=line["width"],
                           tags=tags)


def ease_out_back(t, c=0.9):
    t -= 1
    return 1 + (c + 1) * t ** 3 + c * t ** 2


def ease_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out(t):
    return 1 - (1 - t) ** 3


# ---------- app ----------
class Island:
    def __init__(self, root):
        self.root = root
        self.mac = Cocoa()
        self.mac.allow_key_window()
        self.screen_w, self.notch_l, self.notch_r, self.nh = self.mac.notch()
        self.notch_cx = (self.notch_l + self.notch_r) / 2

        fam = pick_font(root, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "Helvetica")
        mono = pick_font(root, "SF Mono", "Menlo", "Monaco", "Courier")
        self.f_s, self.f_xs, self.f_text = (fam, 11), (fam, 10, "bold"), (fam, 14)
        self.f_mono, self.f_mono_s = (mono, 11), (mono, 10)

        # geometry: collapsed pill, expanded panel heights
        self.cw = (self.notch_r - self.notch_l) + 2 * WING
        self.fy1 = self.nh + 12
        self.fy2 = self.fy1 + 68
        self.row = self.fy2 + 26
        self.eh_closed, self.eh_open = self.row + 34, self.row + 141

        # state
        self.tts = self.speech = self.speech_key = self.bars = None
        self.playing = self.busy = self.seed_locked = self.settings_open = False
        self.expanded = self.tweening = self.modal = False
        self.play_t0 = self.play_off = self.progress = 0.0
        self.speed, self.rate, self.theme = 1.0, 48000, "Turuncu"
        self.status_text, self.status_col = "Model yükleniyor…", MUTED
        self.events = queue.Queue()
        self.hits, self.hover, self.pressed = {}, None, None
        self.hover_since, self.last_inside = None, 0.0
        self.cur = self._target()
        self.win_w = self.win_h = self.win_x = 0

        root.title("EMA Island")
        root.overrideredirect(True)
        root.attributes("-transparent", True)
        root.configure(bg="systemTransparent")
        self.cv = tk.Canvas(root, bg="systemTransparent", highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.text = tk.Text(self.cv, wrap="word", bg=FIELD, fg=TEXT, relief="flat", highlightthickness=0, bd=0,
                            font=self.f_text, padx=0, pady=0, undo=True, selectforeground=TEXT, spacing2=3)
        self.text.insert("1.0", "Merhaba! Ben EMA, çentiğinde yaşayan sesin.")
        self.seed_entry = tk.Entry(self.cv, bg=FIELD, fg=DIM, relief="flat", highlightthickness=0, bd=0,
                                   font=self.f_mono)
        self.seed_entry.bind("<FocusIn>", self._seed_focus_in)
        self.seed_entry.bind("<FocusOut>", lambda e: self.seed_entry.get().strip() or self._seed_set(""))
        self.seed_ph = False
        self._seed_set("")

        cv = self.cv
        cv.bind("<Motion>", self._motion)
        cv.bind("<Leave>", lambda e: self._unhover())
        cv.bind("<ButtonPress-1>", self._press)
        cv.bind("<B1-Motion>", self._drag)
        cv.bind("<ButtonRelease-1>", self._release)
        cv.bind("<Double-Button-1>", self._double)
        cv.bind("<MouseWheel>", self._wheel)
        root.bind("<Command-Return>", lambda e: self.play())
        root.bind("<Control-Return>", lambda e: self.play())
        root.bind("<Escape>", lambda e: self.stop() if self.playing else self.collapse())
        root.bind("<Command-q>", lambda e: self.quit())

        self.mac.accessory()
        self._resize(self._collapsed_size())
        root.update()  # the NSWindow exists only once Tk has mapped it
        self.mac.float_windows()  # level first: only above the menu bar may the window sit at y = 0
        self._resize(self._collapsed_size(), force=True)
        self.draw()
        self._poll()
        threading.Thread(target=self._load_model, daemon=True).start()

    @property
    def accent(self):
        return THEMES[self.theme]

    @property
    def accent2(self):
        return blend(self.accent, TEXT, 0.45)

    # ----- window -----
    def _collapsed_size(self):
        return int(self.cw + 2 * 6 + 8), int(self.nh + 4)

    def _expanded_size(self):
        return int(EXP_W + 2 * 12 + 24), int(self.eh_open + 20)

    def _resize(self, size, force=False):
        w, h = size
        if (w, h) == (self.win_w, self.win_h) and not force:
            return
        self.win_w, self.win_h = w, h
        self.win_x = int(round(self.notch_cx - w / 2))
        self.cv.configure(width=w, height=h)
        self.root.geometry(f"{w}x{h}+{self.win_x}+0")
        self.root.update_idletasks()

    # ----- island shape animation -----
    def _target(self):
        if not self.expanded:
            return dict(w=self.cw, h=self.nh, r=10, s=6)
        return dict(w=EXP_W, h=self.eh_open if self.settings_open else self.eh_closed, r=26, s=12)

    def _animate(self, dur, ease):
        self.tw_from, self.tw_t0, self.tw_dur, self.tw_ease = dict(self.cur), time.perf_counter(), dur, ease
        if not self.tweening:
            self.tweening = True
            self._tween()

    def _tween(self):
        t = min((time.perf_counter() - self.tw_t0) / self.tw_dur, 1)
        e, tgt = self.tw_ease(t), self._target()
        self.cur = {k: self.tw_from[k] + (tgt[k] - self.tw_from[k]) * e for k in tgt}
        self.draw()
        if t < 1:
            self.root.after(12, self._tween)
            return
        self.tweening = False
        if not self.expanded:  # shrink the window to the pill so it never blocks clicks underneath
            self._resize(self._collapsed_size())
            self.draw()

    def expand(self):
        if self.expanded:
            return
        self.expanded = True
        self._resize(self._expanded_size())
        self._animate(0.42, ease_out_back)

    def collapse(self):
        if not self.expanded:
            return
        self.expanded = False
        self._unhover()
        self.cv.focus_set()
        self.mac.deactivate()
        self._animate(0.3, ease_in_out)

    def toggle_settings(self):
        self.settings_open = not self.settings_open
        self._animate(0.32, ease_out)

    # ----- hit testing -----
    def hit(self, key, box, **handlers):
        handlers["box"] = box
        self.hits[key] = handlers

    def _hit_at(self, x, y):
        for h in reversed(list(self.hits.values())):
            x1, y1, x2, y2 = h["box"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return h
        return None

    def _motion(self, e):
        h = self._hit_at(e.x, e.y)
        if h is self.hover:
            return
        self._unhover()
        self.hover = h
        if h:
            if h.get("enter"):
                h["enter"]()
            self.cv.configure(cursor=h.get("cursor", "hand2"))

    def _unhover(self):
        if self.hover and self.hover.get("leave"):
            self.hover["leave"]()
        self.hover = None
        self.cv.configure(cursor="")

    def _press(self, e):
        self.cv.focus_set()
        self.pressed = h = self._hit_at(e.x, e.y)
        if not self.expanded:
            self.expand()
        elif h and h.get("press"):
            h["press"](e.x, e.y)

    def _drag(self, e):
        if self.pressed and self.pressed.get("drag"):
            self.pressed["drag"](e.x, e.y)

    def _release(self, e):
        h, self.pressed = self.pressed, None
        if h and h is self._hit_at(e.x, e.y) and h.get("click"):
            h["click"]()

    def _double(self, e):
        h = self._hit_at(e.x, e.y)
        if h and h.get("double"):
            h["double"]()

    def _wheel(self, e):
        h = self._hit_at(e.x, e.y)
        if h and h.get("wheel") and e.delta:
            h["wheel"](1 if e.delta > 0 else -1)

    # ----- drawing -----
    def draw(self):
        cv, c = self.cv, self.cur
        cv.delete("all")
        self.hits, self.hover = {}, None
        cx = self.win_w / 2
        self.lx, self.rx = cx - c["w"] / 2, cx + c["w"] / 2
        island(cv, cx, c["w"], c["h"], c["r"], c["s"], fill=ISLAND, outline="")
        if self.expanded and abs(c["w"] - EXP_W) < 3:
            self._header()
            self._body()
        elif not self.expanded and abs(c["w"] - self.cw) < 3 and not self.tweening:
            self.draw_ind()

    def draw_ind(self, phase=0.0):
        """Collapsed pill: little bars left of the notch, status right of it."""
        cv, t = self.cv, ("ind",)
        cv.delete("ind")
        y = self.nh / 2
        nl, nr = self.notch_l - self.win_x, self.notch_r - self.win_x
        lx = (self.lx + nl) / 2
        for i, base in enumerate((4, 8, 6, 3)):
            if self.playing or self.busy:
                hh = 2 + 5 * (0.5 + 0.5 * math.sin(phase * (9 if self.playing else 5) + i * 1.3))
                col = self.accent
            else:
                hh, col = base / 2, DIM
            x = lx - 7 + i * 4.7
            cv.create_line(x, y - hh, x, y + hh, fill=col, width=2.5, capstyle="round", tags=t)
        rx = (nr + self.rx) / 2
        if self.busy:
            cv.create_arc(rx - 6, y - 6, rx + 6, y + 6, start=-phase * 360, extent=270, style="arc",
                          outline=self.accent, width=2, tags=t)
        elif self.playing:
            pos = self.play_off + time.perf_counter() - self.play_t0
            cv.create_text(rx, y, text=f"{int(pos // 60)}:{int(pos % 60):02d}", fill=MUTED, font=self.f_mono_s,
                           tags=t)
        else:
            cv.create_oval(rx - 3.5, y - 3.5, rx + 3.5, y + 3.5, fill=self.accent, outline="", tags=t)

    def _header(self):
        cv, y = self.cv, self.nh / 2
        x1, x2 = self.lx + 22, self.rx - 22
        for i, name in enumerate(THEMES):
            self._theme_dot(name, x1 + 6 + i * 18, y)
        for i, (key, icon, cmd) in enumerate((("quit", "power", self.quit),
                                              ("gh", "github", lambda: webbrowser.open(REPO_URL)),
                                              ("set", "sliders", self.toggle_settings))):
            self._header_icon(key, icon, x2 - 8 - i * 30, y, cmd)

    def _header_icon(self, key, icon, x, y, cmd):
        cv = self.cv

        def draw(col):
            cv.delete(key)
            draw_icon(cv, icon, x, y, col, 0.85, (key,))

        on = key == "set" and self.settings_open
        draw(self.accent if on else MUTED)
        self.hit(key, (x - 13, y - 13, x + 13, y + 13), click=cmd,
                 enter=lambda: draw(TEXT), leave=lambda: draw(self.accent if on else MUTED))

    def _theme_dot(self, name, x, y):
        cv, tag = self.cv, f"theme{name}"

        def draw(hover):
            cv.delete(tag)
            if name == self.theme or hover:
                cv.create_oval(x - 8, y - 8, x + 8, y + 8, outline=TEXT if name == self.theme else MUTED,
                               width=1.5, tags=(tag,))
            cv.create_oval(x - 5, y - 5, x + 5, y + 5, fill=THEMES[name], outline="", tags=(tag,))

        draw(False)
        self.hit(tag, (x - 9, y - 9, x + 9, y + 9), click=lambda: self.set_theme(name),
                 enter=lambda: draw(True), leave=lambda: draw(False))

    def _body(self):
        cv, h = self.cv, self.cur["h"]
        x1, x2 = self.lx + 22, self.rx - 22
        first = cv.find_all()[-1]  # rows below the sliding bottom edge get hidden

        # text box + generate button
        rrect(cv, x1, self.fy1, x2 - 56, self.fy2, 14, fill=FIELD, outline="")
        self.text.configure(insertbackground=self.accent, selectbackground=blend(FIELD, self.accent, 0.4))
        if self.fy2 <= h - 8:
            cv.create_window(x1 + 12, self.fy1 + 9, window=self.text, anchor="nw", width=x2 - 56 - x1 - 24,
                             height=self.fy2 - self.fy1 - 16)
        self.gen_geo = (x2 - 22, (self.fy1 + self.fy2) / 2)
        self.draw_gen()

        # player row
        y = self.row
        self.play_geo = (x1 + 15, y)
        self.draw_play()
        self.save_geo = (x2 - 11, y)
        self.draw_save()
        self.time_id = cv.create_text(x2 - 32, y, text=self._time_text(), anchor="e", fill=MUTED, font=self.f_mono,
                                      tags=("time",))
        a, b = x1 + 42, x2 - 72
        self.wave_geo = (a, b, y, 26)
        self.draw_wave()
        self.hit("wave", (a, y - 14, b, y + 14), press=lambda px, py: self.seek((px - a) / (b - a)))

        if self.settings_open or h > self.eh_closed + 2:
            self._settings(x1, x2, h)
        for i in cv.find_all():
            if i > first and (cv.bbox(i) or (0, 0, 0, 0))[3] > h - 6:
                cv.itemconfigure(i, state="hidden")

    def _settings(self, x1, x2, h):
        cv = self.cv
        y = self.row + 38
        cv.create_line(x1, y - 19, x2, y - 19, fill=LINE)
        cv.create_text(x1, y, text="Hız", anchor="w", fill=MUTED, font=self.f_s)
        self.speed_lbl = cv.create_text(x2, y, anchor="e", fill=self.accent2, font=self.f_mono)
        self.speed_geo = (x1 + 100, x2 - 62, y)
        self.draw_speed()
        self.hit("speed", (x1 + 90, y - 13, x2 - 52, y + 13), press=self._speed_at, drag=self._speed_at,
                 double=lambda: self.set_speed(1.0), wheel=lambda d: self.set_speed(self.speed + 0.05 * d))

        y += 34
        cv.create_text(x1, y, text="Örnekleme", anchor="w", fill=MUTED, font=self.f_s)
        self.rate_lbl = cv.create_text(x2, y, anchor="e", fill=self.accent2, font=self.f_mono)
        self.rate_geo = (x1 + 100, x2 - 62, y)
        self.draw_rate()
        self.hit("rate", (x1 + 90, y - 13, x2 - 52, y + 13), press=self._rate_at, drag=self._rate_at,
                 wheel=lambda d: self.set_rate_index(RATES.index(self.rate) + d))

        y += 36
        cv.create_text(x1, y, text="Seed", anchor="w", fill=MUTED, font=self.f_s)
        rrect(cv, x1 + 92, y - 15, x2 - 72, y + 15, 10, fill=FIELD, outline="")
        self.seed_entry.configure(insertbackground=self.accent)
        if y + 15 <= h - 8:
            cv.create_window(x1 + 104, y, window=self.seed_entry, anchor="w", width=x2 - 72 - x1 - 92 - 24)
        self._icon_btn("dice", x2 - 50, y, 14, "dice", self._random_seed, scale=0.8)
        self.lock_geo = (x2 - 14, y)
        self.draw_lock()

    # ----- controls -----
    def _icon_btn(self, tag, cx, cy, r, icon, cmd, enabled=True, color=TEXT, scale=1.0):
        cv = self.cv

        def draw(hover):
            cv.delete(tag)
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CHIP_HI if hover and enabled else CHIP, outline="",
                           tags=(tag,))
            draw_icon(cv, icon, cx, cy, color if enabled else DIM, scale, (tag,))

        draw(False)
        self.hit(tag, (cx - r, cy - r, cx + r, cy + r), click=cmd if enabled else None, enter=lambda: draw(True),
                 leave=lambda: draw(False), cursor="hand2" if enabled else "")

    def _slider(self, tag, geo, frac, ticks=(), mark=None):
        cv, (a, b, y), t = self.cv, geo, (tag,)
        cv.delete(tag)
        x = a + frac * (b - a)
        rrect(cv, a, y - 2.5, b, y + 2.5, 2.5, fill=LINE, outline="", tags=t)
        if mark is not None:
            mx = a + mark * (b - a)
            cv.create_line(mx, y - 6, mx, y + 6, fill=DIM, tags=t)
        if x > a + 3:
            rrect(cv, a, y - 2.5, x, y + 2.5, 2.5, fill=self.accent, outline="", tags=t)
        for f in ticks:
            tx = a + f * (b - a)
            cv.create_oval(tx - 2, y - 2, tx + 2, y + 2, fill=ISLAND if tx <= x else DIM, outline="", tags=t)
        cv.create_oval(x - 7, y - 7, x + 7, y + 7, fill=TEXT, outline=self.accent, width=2, tags=t)

    def draw_speed(self):
        f = math.log(self.speed / SPEED_MIN) / math.log(SPEED_MAX / SPEED_MIN)
        self._slider("speed", self.speed_geo, f, mark=0.5)
        self.cv.itemconfigure(self.speed_lbl, text=f"{self.speed:.2f}×")

    def draw_rate(self):
        n = len(RATES) - 1
        self._slider("rate", self.rate_geo, RATES.index(self.rate) / n, ticks=[k / n for k in range(n + 1)])
        self.cv.itemconfigure(self.rate_lbl, text=f"{self.rate // 1000} kHz")

    def draw_lock(self):
        self._icon_btn("lock", *self.lock_geo, 14, "lock" if self.seed_locked else "unlock", self._toggle_lock,
                       color=self.accent if self.seed_locked else TEXT, scale=0.8)

    def draw_gen(self, phase=0.0):
        cv, (x, y), t = self.cv, self.gen_geo, ("gen",)
        cv.delete("gen")

        def draw(hover):
            cv.delete("gen")
            if self.busy:
                cv.create_oval(x - 22, y - 22, x + 22, y + 22, fill=CHIP, outline="", tags=t)
                cv.create_arc(x - 9, y - 9, x + 9, y + 9, start=-phase * 360, extent=270, style="arc",
                              outline=self.accent, width=2.5, tags=t)
                return
            cv.create_oval(x - 22, y - 22, x + 22, y + 22, fill=blend(self.accent, TEXT, 0.3) if hover else self.accent,
                           outline="", tags=t)
            cv.create_polygon(x - 5, y - 9, x - 5, y + 9, x + 9, y, fill=ISLAND, outline="", tags=t)

        draw(False)
        self.hit("gen", (x - 22, y - 22, x + 22, y + 22), click=None if self.busy else self.play,
                 enter=lambda: draw(True), leave=lambda: draw(False), cursor="" if self.busy else "hand2")

    def draw_play(self):
        cv, (x, y), t = self.cv, self.play_geo, ("play",)
        cv.delete("play")
        cv.create_oval(x - 15, y - 15, x + 15, y + 15, fill=CHIP_HI if self.busy else TEXT, outline="", tags=t)
        if self.playing:
            cv.create_rectangle(x - 4, y - 4, x + 4, y + 4, fill=ISLAND, outline="", tags=t)
        else:
            cv.create_polygon(x - 3, y - 6, x - 3, y + 6, x + 6, y, fill=ISLAND, outline="", tags=t)
        self.hit("play", (x - 15, y - 15, x + 15, y + 15), click=self.toggle)

    def draw_save(self):
        self._icon_btn("save", *self.save_geo, 11, "download", self.save, enabled=self.speech is not None, scale=0.6)

    def draw_wave(self, phase=None):
        cv, (a, b, y, hgt), t = self.cv, self.wave_geo, ("wave",)
        cv.delete("wave")
        ww = b - a
        if phase is not None:  # generating
            n = int(ww // 4)
            for i in range(n):
                x = a + (i + 0.5) * ww / n
                v = (math.sin(i * 0.35 - phase) * 0.5 + 0.5) * (math.sin(i * 0.11 + phase * 0.5) * 0.3 + 0.7)
                hh = 1.5 + v * hgt * 0.4
                cv.create_line(x, y - hh, x, y + hh, fill=blend(WAVE, self.accent, v), width=2, capstyle="round",
                               tags=t)
        elif self.status_text:
            cv.create_text(a, y, text=self.status_text, anchor="w", fill=self.status_col, font=self.f_s, tags=t)
        elif self.bars is None:
            n = int(ww // 4)
            for i in range(n):
                x = a + (i + 0.5) * ww / n
                cv.create_line(x, y - 1, x, y + 1, fill=LINE, width=2, capstyle="round", tags=t)
        else:
            n = len(self.bars)
            for i, v in enumerate(self.bars):
                x = a + (i + 0.5) * ww / n
                hh = 1.5 + v * hgt * 0.45
                col = blend(self.accent, self.accent2, i / n) if i / n < self.progress else WAVE
                cv.create_line(x, y - hh, x, y + hh, fill=col, width=2, capstyle="round", tags=t)
            if 0 < self.progress < 1:
                px = a + self.progress * ww
                cv.create_line(px, y - hgt / 2, px, y + hgt / 2, fill=TEXT, tags=t)

    def _time_text(self):
        pos = self.progress * self.speech.duration if self.speech else 0
        return f"{int(pos // 60)}:{int(pos % 60):02d}"

    # ----- state -----
    def _ready(self):
        """True when the expanded body is on screen (so partial redraws have something to update)."""
        return self.expanded and not self.tweening

    def set_theme(self, name):
        if name != self.theme:
            self.theme = name
            self.draw()

    def _speed_at(self, x, _y):
        a, b, _ = self.speed_geo
        t = min(max((x - a) / (b - a), 0), 1)
        v = SPEED_MIN * (SPEED_MAX / SPEED_MIN) ** t
        self.set_speed(1.0 if abs(v - 1.0) < 0.04 else round(v / 0.05) * 0.05)  # magnet at normal speed

    def set_speed(self, v):
        self.speed = round(min(max(v, SPEED_MIN), SPEED_MAX), 2)
        if self._ready() and self.settings_open:
            self.draw_speed()

    def _rate_at(self, x, _y):
        a, b, _ = self.rate_geo
        self.set_rate_index(round((x - a) / (b - a) * (len(RATES) - 1)))

    def set_rate_index(self, i):
        i = min(max(i, 0), len(RATES) - 1)
        if RATES[i] != self.rate:
            self.rate = RATES[i]
            if self._ready() and self.settings_open:
                self.draw_rate()

    def status(self, txt, col=MUTED):
        if len(txt) > 44:  # one short line; the full text goes to the terminal
            print(txt, file=sys.stderr)
            txt = txt[:43] + "…"
        self.status_text, self.status_col = txt, col
        if self._ready():
            self.draw_wave()

    def _seed_get(self):
        return "" if self.seed_ph else self.seed_entry.get().strip()

    def _seed_set(self, value):
        self.seed_entry.delete(0, "end")
        self.seed_ph = not value
        self.seed_entry.configure(fg=DIM if self.seed_ph else TEXT)
        self.seed_entry.insert(0, "rastgele" if self.seed_ph else value)

    def _seed_focus_in(self, _):
        if self.seed_ph:
            self.seed_entry.delete(0, "end")
            self.seed_entry.configure(fg=TEXT)
            self.seed_ph = False

    def _random_seed(self):
        self._seed_set(str(random.randrange(0, 2 ** 31)))

    def _toggle_lock(self):
        self.seed_locked = not self.seed_locked
        self.draw_lock()
        if self.seed_locked and not self._seed_get() and self.speech:
            self._seed_set(str(self.speech.seed))

    def _params(self):
        text = self.text.get("1.0", "end-1c").strip()
        s = self._seed_get()
        if s and not s.isdigit():
            raise ValueError("Seed pozitif bir tam sayı olmalı")
        return text, self.speed, int(s) if s else None, self.rate

    # ----- model -----
    def _load_model(self):
        try:
            import torch
            from ema_lightning import EMA
            from ema_lightning.decoder import load_decoder
            from ema_lightning.frontend import Frontend
            from ema_lightning.model import load_acoustic

            dev = "cuda" if torch.cuda.is_available() else "cpu"
            # local weights next to this file or in the repo root; otherwise download from the Hub
            local = next((d for d in (HERE, HERE.parent) if (d / "ema.pt").exists() and (d / "decoder.pt").exists()),
                         None)
            if local:
                m = load_acoustic(str(local / "ema.pt"), dev)
                tts = EMA._from_parts(m, load_decoder(str(local / "decoder.pt"), dev), Frontend(m.vocab), dev)
            else:
                tts = EMA(dev)
            self.events.put(("status", ("Isınıyor…", MUTED)))
            tts.say("Merhaba.", seed=0)  # warm-up so the first real request is fast
            self.tts = tts
            self.events.put(("ready", dev))
        except Exception as e:
            self.events.put(("error", f"Model yüklenemedi: {e}"))

    def _generate(self, key):
        text, speed, seed, rate = key
        try:
            sp = self.tts.say(text, speed=speed, seed=seed, sample_rate=rate)
            self.events.put(("done", (key, sp)))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(val)
        except queue.Empty:
            pass
        now = time.perf_counter()
        self._track_pointer(now)
        if self.playing:
            pos = self.play_off + now - self.play_t0
            if pos >= self.speech.duration:
                self.playing, self.progress = False, 1.0
                if self._ready():
                    self.draw_play()
            else:
                self.progress = pos / self.speech.duration
        if self._ready():
            if self.busy:
                self.draw_wave(now * 6)
                self.draw_gen(now)
            elif self.playing or self.progress == 1.0:
                self.draw_wave()
                self.cv.itemconfigure(self.time_id, text=self._time_text())
        elif not self.expanded and not self.tweening:
            self.draw_ind(now)
        self.root.after(33, self._poll)

    def _track_pointer(self, now):
        """Hover is read from the global pointer: clicks over transparent pixels pass through the window."""
        px, py = self.root.winfo_pointerxy()
        c = self.cur
        inside = abs(px - (self.win_x + self.win_w / 2)) <= c["w"] / 2 + c["s"] and 0 <= py <= c["h"] + 4
        if inside:
            self.last_inside = now
        if not self.expanded:
            if not inside:
                self.hover_since = None
            elif self.hover_since is None:
                self.hover_since = now
            elif now - self.hover_since > 0.08:
                self.hover_since = None
                self.expand()
        elif not inside and now - self.last_inside > 0.45 and not self.modal and self.pressed is None:
            self.collapse()

    def _on_status(self, v):
        self.status(*v)

    def _on_ready(self, _dev):
        self.status("")

    def _on_error(self, msg):
        self.busy = False
        self.status(msg, DANGER)
        if self._ready():
            self.draw_gen()
            self.draw_play()

    def _on_done(self, val):
        key, sp = val
        self.busy = False
        self.speech, self.speech_key = sp, key
        n = int((self.wave_geo[1] - self.wave_geo[0]) // 3) if hasattr(self, "wave_geo") else 100
        peaks = np.array([c.max() if len(c) else 0 for c in np.array_split(np.abs(sp.audio), n)])
        self.bars, self.progress = peaks / (peaks.max() or 1), 0.0
        if self.seed_locked:
            self._seed_set(str(sp.seed))
        self.status_text = ""
        self._start(0.0)
        if self._ready():
            self.draw_gen()
            self.draw_save()
            self.draw_wave()

    # ----- actions -----
    def play(self):
        if self.busy:
            return
        if self.tts is None:
            self.status("Model henüz yüklenmedi, bekle…")
            return
        try:
            key = self._params()
        except ValueError as e:
            self.status(str(e), DANGER)
            return
        if not key[0]:
            self.status("Önce bir metin yaz", DANGER)
            return
        self.stop()
        if self.speech is not None and key == self.speech_key and key[2] is not None:
            self._start(0.0)  # same text + same fixed seed: replay without regenerating
            return
        self.busy = True
        self.status_text = ""
        if self._ready():
            self.draw_play()
        threading.Thread(target=self._generate, args=(key,), daemon=True).start()

    def toggle(self):
        if self.busy:
            return
        if self.playing:
            self.stop()
        elif self.speech is not None and self.speech_key == self._safe_params():
            self._start(0.0 if self.progress >= 1 else self.progress * self.speech.duration)
        else:
            self.play()

    def _safe_params(self):
        try:
            p = self._params()
        except ValueError:
            return None
        # a random seed never matches; compare ignoring it so ▶ replays the current clip
        return p if p[2] is not None else (p[0], p[1], self.speech_key[2] if self.speech_key else None, p[3])

    def _start(self, offset):
        sp = self.speech
        sd.stop()
        sd.play(sp.audio[int(offset * sp.sample_rate):], sp.sample_rate)
        self.play_off, self.play_t0, self.playing = offset, time.perf_counter(), True
        if self._ready():
            self.draw_play()

    def stop(self):
        if self.playing:
            sd.stop()
            self.playing = False
            if self._ready():
                self.draw_play()

    def seek(self, frac):
        if self.speech is None or self.busy:
            return
        self._start(min(max(frac, 0), 1) * self.speech.duration)

    def save(self):
        if self.speech is None:
            return
        from ema_lightning.audio import write_wav

        self.modal = True  # keep the island open behind the dialog
        try:
            path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile="ema.wav",
                                                filetypes=[("WAV", "*.wav")])
        finally:
            self.modal = False
            self.last_inside = time.perf_counter()
        if path:
            write_wav(path, self.speech.audio, self.speech.sample_rate)
            self.status(f"Kaydedildi: {Path(path).name}")

    def quit(self):
        sd.stop()
        self.root.destroy()


if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("EMA Island sadece macOS'ta çalışır; diğer sistemlerde ema-gui/app.py kullan.")
    root = tk.Tk()
    Island(root)
    root.mainloop()
