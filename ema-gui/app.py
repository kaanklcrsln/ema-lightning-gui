"""EMA Lightning Studio: dark glass Tkinter GUI for Turkish TTS.

Run:  .venv/bin/python app.py

Everything except the two text inputs is drawn on one canvas: a numpy-rendered background
(drifting white glow seen through frosted panels) with vector controls on top. Tk widgets
can't be translucent, so the text and seed inputs sit in solid inset fields.
"""
import math
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
BG = "#080F0F"
TEXT = "#FBFEF9"
MUTED = blend(BG, TEXT, 0.55)
DIM = blend(BG, TEXT, 0.32)
FIELD = blend(BG, "#000000", 0.3)  # solid inset behind the text and seed inputs
CHIP = blend(BG, TEXT, 0.10)
CHIP_HI = blend(BG, TEXT, 0.18)
LINE = blend(BG, TEXT, 0.16)
WAVE = blend(BG, TEXT, 0.25)
EDGE = blend(BG, TEXT, 0.20)  # glass panel border
DANGER = "#FF8F8F"
THEMES = {"Mavi": "#8EC5FF", "Yeşil": "#93E2B0", "Turuncu": "#FFAE85", "Mor": "#C4A7FF"}

RATES = (8000, 16000, 24000, 48000)
SPEED_MIN, SPEED_MAX = 0.25, 4.0
FPS = 12  # background frame rate; the glow drifts slowly so this still looks smooth

TIPS = {
    "Hız": "0.25× ile 4× arası. 1.0 normal hız. Çift tıklayınca 1.0'a döner.",
    "Örnekleme hızı": "Çıkış kalitesi. 48 kHz en yüksek kalite; 8 kHz telefon hattı içindir. "
                      "Model her zaman 48 kHz üretir, diğerleri yeniden örneklenir.",
    "Seed": "Aynı seed + aynı metin = birebir aynı ses. Boş bırakırsan her seferinde rastgele seçilir; "
            "kullanılan seed altta gösterilir. Zar yeni rastgele seed yazar, kilit sabitler.",
}

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


def pick_font(root, *names):
    fams = set(tkfont.families(root))
    for n in names:
        if n in fams:
            return n
    return "Helvetica"


def rrect(cv, x1, y1, x2, y2, r, **kw):
    """Rounded rect with true circular corners, so it lines up with the glass mask in GlassBackground."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for k in range(9):
            a = math.radians(a0 + 90 * k / 8)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return cv.create_polygon(pts, **kw)


def draw_icon(cv, name, cx, cy, col, s=1.0, tags=()):
    """Line icons drawn on a canvas, centered on (cx, cy), ~16px at s=1."""
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


class GlassBackground:
    """White glow drifting behind frosted panels, rendered with numpy into one PhotoImage per frame."""

    # x/y swing (fraction of size), x/y angular speed (rad/s), phase, gaussian width (fraction of w), strength
    BLOBS = ((0.36, 0.30, 0.23, 0.17, 0.0, 0.62, 1.0),
             (0.32, 0.34, 0.15, 0.21, 2.1, 0.52, 0.8),
             (0.40, 0.24, 0.27, 0.12, 4.2, 0.44, 0.7))

    PAD = 24  # shadow reach around a panel

    def __init__(self, cv):
        self.cv, self.photo, self.key, self.cache = cv, None, None, {}
        self.noise = np.zeros((0, 0, 1), np.float32)
        self.item = cv.create_image(0, 0, anchor="nw", tags="bg")

    @staticmethod
    def _sdf(xs, ys, w, h, r):
        dx = np.maximum(np.abs(xs - w / 2) - (w / 2 - r), 0)
        dy = np.maximum(np.abs(ys - h / 2) - (h / 2 - r), 0)
        return np.hypot(dx, dy) - r

    def _local(self, pw, ph, r):
        """Mask, top sheen and drop shadow for one panel size, in a box padded by PAD (cached)."""
        k = (pw, ph, r)
        if k not in self.cache:
            if len(self.cache) > 64:  # slide animation makes many sizes
                self.cache.clear()
            p = self.PAD
            xs = np.arange(-p, pw + p, dtype=np.float32) + 0.5
            ys = (np.arange(-p, ph + p + 6, dtype=np.float32) + 0.5)[:, None]
            m = np.clip(0.5 - self._sdf(xs, ys, pw, ph, r), 0, 1)
            sheen = m * np.clip(1 - ys / 90, 0, 1) ** 1.5  # light catching the top edge
            shadow = np.clip(1 - self._sdf(xs, ys - 6, pw, ph, r) / 22, 0, 1) ** 2
            self.cache[k] = (m, sheen, shadow)
        return self.cache[k]

    @staticmethod
    def _place(dst, src, x, y):
        h, w = dst.shape
        ax1, ay1, ax2, ay2 = max(x, 0), max(y, 0), min(x + src.shape[1], w), min(y + src.shape[0], h)
        if ax1 < ax2 and ay1 < ay2:
            view = dst[ay1:ay2, ax1:ax2]
            np.maximum(view, src[ay1 - y:ay2 - y, ax1 - x:ax2 - x], out=view)

    def layout(self, w, h, panels):
        panels = [tuple(int(round(v)) for v in p) for p in panels]
        if self.key == (w, h, tuple(panels)):
            return
        self.key = (w, h, tuple(panels))
        inside, sheen, shadow = (np.zeros((h, w), np.float32) for _ in range(3))
        for x1, y1, x2, y2, r in panels:
            for dst, src in zip((inside, sheen, shadow), self._local(x2 - x1, y2 - y1, r)):
                self._place(dst, src, x1 - self.PAD, y1 - self.PAD)
        shadow *= 1 - inside
        if self.noise.shape[0] < h or self.noise.shape[1] < w:  # grain hides banding
            self.noise = np.random.default_rng(7).normal(0, 0.7, (h + 200, w)).astype(np.float32)
        base = np.array([int(BG[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        frost = base * 0.85 + 5  # panels: lifted a little
        # per-pixel scalars first, then one broadcast each to RGB (keeps the full-size temporaries few)
        outside = (1 - 0.5 * shadow) * (1 - inside)
        self.base = (outside[..., None] * base + inside[..., None] * frost
                     + (9 * sheen + self.noise[:h, :w])[..., None])
        self.gain = ((30 + 10 * inside) * (1 - 0.6 * shadow))[..., None]  # frosted glass catches more glow
        self.xs, self.ys, self.w, self.h = np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32), w, h
        self.header = f"P6 {w} {h} 255 ".encode()
        if self.photo is None or (self.photo.width(), self.photo.height()) != (w, h):
            self.photo = tk.PhotoImage(width=w, height=h)
            self.cv.itemconfigure(self.item, image=self.photo)

    def frame(self, t):
        w, h = self.w, self.h
        g = np.zeros((h, w), np.float32)
        for ax, ay, fx, fy, ph, size, k in self.BLOBS:
            cx = w * (0.5 + ax * math.sin(t * fx + ph))
            cy = h * (0.5 + ay * math.cos(t * fy + ph * 1.3))
            s = size * w
            g += k * np.outer(np.exp(-((self.ys - cy) / s) ** 2), np.exp(-((self.xs - cx) / s) ** 2))
        px = np.clip(self.base + self.gain * g[..., None], 0, 255).astype(np.uint8)
        self.photo.configure(data=self.header + px.tobytes(), format="PPM")


class Tooltip:
    def __init__(self, root, font):
        self.root, self.font, self.win = root, font, None

    def show(self, x, y, text):
        self.hide()
        self.win = tk.Toplevel(self.root)
        self.win.wm_overrideredirect(True)
        self.win.configure(bg=EDGE)
        tk.Label(self.win, text=text, bg=CHIP, fg=TEXT, font=self.font, justify="left",
                 wraplength=240, padx=10, pady=8).pack(padx=1, pady=1)
        self.win.wm_geometry(f"+{x}+{y}")

    def hide(self):
        if self.win:
            self.win.destroy()
            self.win = None


# ---------- app ----------
class App:
    W, M = 340, 24  # window width, side margin (cards are 292 wide)

    def __init__(self, root):
        self.root = root
        root.title("EMA GUI")
        root.resizable(False, False)
        root.configure(bg=BG)

        fam = pick_font(root, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "Inter", "Helvetica")
        mono = pick_font(root, "SF Mono", "Menlo", "Monaco", "Courier")
        self.f_h = (fam, 13, "bold")
        self.f_s = (fam, 11)
        self.f_xs = (fam, 10, "bold")
        self.f_text = (fam, 15)
        self.f_mono = (mono, 12)

        self.tts = self.speech = self.speech_key = self.bars = None
        self.playing = self.busy = self.seed_locked = self.settings_open = False
        self.play_t0 = self.play_off = self.progress = 0.0
        self.speed, self.rate, self.theme = 1.0, 48000, "Turuncu"
        self.status_text, self.status_col = "Model yükleniyor…", MUTED
        self.last_seed_id = None
        self.events = queue.Queue()
        self.H = 0
        self.settings_h, self.animating = 48, False  # settings panel height, animated by _slide
        self.hits, self.hover, self.pressed = {}, None, None

        self.cv = tk.Canvas(root, width=self.W, height=600, bg=BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.bg = GlassBackground(self.cv)
        self.tip = Tooltip(root, self.f_s)

        self.text = tk.Text(self.cv, wrap="word", bg=FIELD, fg=TEXT, relief="flat", highlightthickness=0, bd=0,
                            font=self.f_text, padx=2, pady=2, undo=True, selectforeground=TEXT, spacing2=4)
        self.text.insert("1.0", "Merhaba! Ben EMA. Yazdığın her şeyi saniyeler içinde Türkçe seslendirebilirim.")
        self.text.bind("<<Modified>>", self._text_changed)
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
        root.bind("<space>", self._space)
        root.bind("<Escape>", lambda e: self.stop())

        self.build()
        self.t0 = time.perf_counter()
        self._animate()
        self._poll()
        threading.Thread(target=self._load_model, daemon=True).start()

    @property
    def accent(self):
        return THEMES[self.theme]

    @property
    def accent2(self):
        return blend(self.accent, TEXT, 0.45)

    # ----- hit testing: one table of boxes instead of per-widget bindings -----
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
            if h.get("tip"):
                x1, _, _, y2 = h["box"]
                self.tip.show(self.cv.winfo_rootx() + int(x1), self.cv.winfo_rooty() + int(y2) + 6, h["tip"])
            self.cv.configure(cursor=h.get("cursor", "hand2"))

    def _unhover(self):
        if self.hover and self.hover.get("leave"):
            self.hover["leave"]()
        self.hover = None
        self.tip.hide()
        self.cv.configure(cursor="")

    def _press(self, e):
        self.cv.focus_set()
        self.pressed = h = self._hit_at(e.x, e.y)
        if h and h.get("press"):
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

    # ----- layout -----
    def build(self):
        """(Re)draw every control; called at start, on theme change and when settings open/close."""
        self.cv.delete("ui")
        self.hits, self.hover, self.pressed, self.panels = {}, None, None, []
        self.tip.hide()
        x1, x2 = self.M, self.W - self.M
        y = self._nav(x1, 14, x2) + 14
        y = self._settings(x1, y, x2) + 14
        y = self._editor(x1, y, x2) + 14
        y = self._player(x1, y, x2) + 20
        # resizing the window is slow: while sliding, grow once up front and shrink once at the end
        h = max(y, y + self._settings_target() - round(self.settings_h), self.H) if self.animating else y
        if h != self.H:
            self.H = h
            self.cv.configure(height=h)
            self.root.geometry(f"{self.W}x{h}")
        self.bg.layout(self.W, self.H, self.panels)
        self.bg.frame(time.perf_counter() - getattr(self, "t0", time.perf_counter()))

    def _panel(self, x1, y1, x2, y2, r=18):
        self.panels.append((x1, y1, x2, y2, r))
        rrect(self.cv, x1, y1, x2, y2, r, fill="", outline=EDGE, tags="ui")

    def _nav(self, x1, y1, x2):
        cv, y2 = self.cv, y1 + 46
        self._panel(x1, y1, x2, y2, 16)
        cy = (y1 + y2) / 2
        gx = x2 - 26

        def github(col):
            cv.delete("gh")
            draw_icon(cv, "github", gx, cy, col, 1.15, ("ui", "gh"))

        github(MUTED)
        self.hit("gh", (gx - 14, cy - 14, gx + 14, cy + 14), click=lambda: webbrowser.open(REPO_URL),
                 enter=lambda: github(TEXT), leave=lambda: github(MUTED), tip="GitHub reposu")
        for i, name in enumerate(THEMES):
            self._theme_dot(name, x1 + 26 + i * 20, cy)
        return y2

    def _theme_dot(self, name, x, y):
        cv, tag = self.cv, f"theme{name}"

        def draw(hover):
            cv.delete(tag)
            if name == self.theme or hover:
                cv.create_oval(x - 9.5, y - 9.5, x + 9.5, y + 9.5, outline=TEXT if name == self.theme else MUTED,
                               width=1.5, tags=("ui", tag))
            cv.create_oval(x - 6, y - 6, x + 6, y + 6, fill=THEMES[name], outline="", tags=("ui", tag))

        draw(False)
        self.hit(tag, (x - 10, y - 10, x + 10, y + 10), click=lambda: self.set_theme(name),
                 enter=lambda: draw(True), leave=lambda: draw(False))

    def _settings(self, x1, y1, x2):
        cv, y2 = self.cv, y1 + round(self.settings_h)
        self._panel(x1, y1, x2, y2)
        cx, w = x1 + 22, x2 - x1 - 44
        cv.create_text(cx, y1 + 24, text="SES AYARLARI", anchor="w", fill=MUTED, font=self.f_xs, tags="ui")

        def chevron(col):
            cv.delete("chev")
            d = -2.5 if self.settings_open else 2.5
            cv.create_line(x2 - 29, y1 + 24 - d, x2 - 24, y1 + 24 + d, x2 - 19, y1 + 24 - d, fill=col, width=2,
                           capstyle="round", joinstyle="round", tags=("ui", "chev"))

        chevron(MUTED)
        self.hit("chev", (x1, y1, x2, y1 + 48), click=self.toggle_settings,
                 enter=lambda: chevron(TEXT), leave=lambda: chevron(MUTED))
        self.last_seed_id = None
        if self.settings_h <= 48:
            if not self.settings_open:
                cv.create_text(x2 - 38, y1 + 24, text=f"{self.speed:.2f}×  ·  {self.rate // 1000} kHz",
                               anchor="e", fill=DIM, font=self.f_s, tags="ui")
            return y2
        first = cv.find_all()[-1]  # body items get higher ids; rows below the sliding edge are hidden

        # speed
        self._label(cx, y1 + 54, "Hız")
        self.speed_lbl = cv.create_text(x2 - 22, y1 + 54, anchor="e", fill=self.accent2, font=self.f_mono, tags="ui")
        self.speed_geo = (cx + 10, cx + w - 10, y1 + 82)
        self.draw_speed()
        self.hit("speed", (cx, y1 + 68, cx + w, y1 + 96), press=self._speed_at, drag=self._speed_at,
                 double=lambda: self.set_speed(1.0), wheel=lambda d: self.set_speed(self.speed + 0.05 * d))
        cv.create_text(cx + 8, y1 + 102, text="Yavaş", anchor="w", fill=DIM, font=self.f_s, tags="ui")
        cv.create_text(x2 - 30, y1 + 102, text="Hızlı", anchor="e", fill=DIM, font=self.f_s, tags="ui")

        # sample rate
        self._label(cx, y1 + 134, "Örnekleme hızı")
        self.rate_lbl = cv.create_text(x2 - 22, y1 + 134, anchor="e", fill=self.accent2, font=self.f_mono, tags="ui")
        self.rate_geo = (cx + 10, cx + w - 10, y1 + 162)
        self.draw_rate()
        self.hit("rate", (cx, y1 + 148, cx + w, y1 + 176), press=self._rate_at, drag=self._rate_at,
                 wheel=lambda d: self.set_rate_index(RATES.index(self.rate) + d))

        # seed
        self._label(cx, y1 + 202, "Seed")
        fy = y1 + 234
        rrect(cv, cx, fy - 19, cx + w - 92, fy + 19, 10, fill=FIELD, outline=LINE, tags="ui")
        self.seed_entry.configure(insertbackground=self.accent)
        if fy + 19 <= y2 - 6:  # embedded widgets can't be hidden like items, so only place when visible
            cv.create_window(cx + 12, fy, window=self.seed_entry, anchor="w", width=w - 116, tags="ui")
        self._icon_btn("dice", cx + w - 66, fy, 19, "dice", self._random_seed, square=True,
                       tip="Yeni rastgele seed")
        self.lock_geo = (cx + w - 19, fy)
        self.draw_lock()
        self.last_seed_id = cv.create_text(cx, y1 + 266, text=self._last_seed_text(), anchor="w", fill=DIM,
                                           font=self.f_s, tags="ui")
        for i in cv.find_all():
            if i > first and (cv.bbox(i) or (0, 0, 0, 0))[3] > y2 - 6:
                cv.itemconfigure(i, state="hidden")
        return y2

    def _editor(self, x1, y1, x2):
        cv, y2 = self.cv, y1 + 274
        self._panel(x1, y1, x2, y2)
        cx, w = x1 + 22, x2 - x1 - 44
        cv.create_text(cx, y1 + 24, text="METİN", anchor="w", fill=MUTED, font=self.f_xs, tags="ui")
        self.status_id = cv.create_text(x2 - 22, y1 + 24, text=self.status_text, anchor="e", fill=self.status_col,
                                        font=self.f_s, tags="ui")
        rrect(cv, x1 + 14, y1 + 40, x2 - 14, y1 + 186, 12, fill=FIELD, outline=LINE, tags="ui")
        self.text.configure(insertbackground=self.accent, selectbackground=blend(FIELD, self.accent, 0.35))
        cv.create_window(cx, y1 + 47, window=self.text, anchor="nw", width=w, height=132, tags="ui")
        self.count_id = cv.create_text(cx, y1 + 204, anchor="w", fill=DIM, font=self.f_s, tags="ui")
        cv.create_text(x2 - 22, y1 + 204, text="⌘ + Enter", anchor="e", fill=DIM, font=self.f_s, tags="ui")
        self._pill("clear", (cx, y1 + 220, cx + 84, y1 + 258), "Temizle", lambda: self.text.delete("1.0", "end"),
                   CHIP, CHIP_HI, TEXT, self.f_s, outline=LINE)
        self.gen_geo = (cx + 92, y1 + 220, x2 - 22, y1 + 258)
        self.draw_gen()
        self._update_count()
        return y2

    def _player(self, x1, y1, x2):
        cv, y2 = self.cv, y1 + 60
        self._panel(x1, y1, x2, y2)
        row = (y1 + y2) / 2
        self.play_geo = (x1 + 34, row)
        self.draw_play()
        self.save_geo = (x2 - 25, row)
        self.draw_save()
        tw = tkfont.Font(font=self.f_mono).measure("0:00")
        self.time_id = cv.create_text(x2 - 46, row, text="0:00", anchor="e", fill=MUTED, font=self.f_mono,
                                      tags="ui")
        a, b = x1 + 64, x2 - 56 - tw
        self.wave_geo = (a, b, row, 32)
        self.draw_wave()
        self.hit("wave", (a, row - 16, b, row + 16), press=lambda x, y: self.seek((x - a) / (b - a)))
        return y2

    # ----- controls -----
    def _label(self, x, y, txt):
        cv, tag = self.cv, f"info{txt}"
        cv.create_text(x, y, text=txt, anchor="w", fill=TEXT, font=self.f_h, tags="ui")
        dx = x + tkfont.Font(font=self.f_h).measure(txt) + 16
        cv.create_oval(dx - 8, y - 8, dx + 8, y + 8, fill=CHIP, outline=LINE, tags=("ui", tag))
        cv.create_text(dx, y, text="?", fill=MUTED, font=self.f_xs, tags=("ui", tag))
        self.hit(tag, (dx - 9, y - 9, dx + 9, y + 9), tip=TIPS[txt], cursor="question_arrow")

    def _pill(self, tag, box, text, cmd, fill, hover, fg, font, outline="", enabled=True):
        cv = self.cv
        x1, y1, x2, y2 = box

        def draw(h):
            cv.delete(tag)
            rrect(cv, x1, y1, x2, y2, (y2 - y1) / 2, fill=hover if h and enabled else fill, outline=outline,
                  tags=("ui", tag))
            cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=fg, font=font, tags=("ui", tag))

        draw(False)
        self.hit(tag, box, click=cmd if enabled else None, enter=lambda: draw(True), leave=lambda: draw(False),
                 cursor="hand2" if enabled else "")

    def _icon_btn(self, tag, cx, cy, r, icon, cmd, square=False, enabled=True, color=TEXT, scale=1.0, tip=None):
        cv = self.cv

        def draw(hover):
            cv.delete(tag)
            fill = CHIP_HI if hover and enabled else CHIP
            if square:
                rrect(cv, cx - r, cy - r, cx + r, cy + r, 10, fill=fill, outline=LINE, tags=("ui", tag))
            else:
                cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=LINE, tags=("ui", tag))
            draw_icon(cv, icon, cx, cy, color if enabled else DIM, scale, ("ui", tag))

        draw(False)
        self.hit(tag, (cx - r, cy - r, cx + r, cy + r), click=cmd if enabled else None, enter=lambda: draw(True),
                 leave=lambda: draw(False), tip=tip if enabled else None, cursor="hand2" if enabled else "")

    def _slider(self, tag, geo, frac, ticks=(), mark=None):
        cv, (a, b, y), t = self.cv, geo, ("ui", tag)
        cv.delete(tag)
        x = a + frac * (b - a)
        rrect(cv, a, y - 3, b, y + 3, 3, fill=LINE, outline="", tags=t)
        if mark is not None:
            mx = a + mark * (b - a)
            cv.create_line(mx, y - 7, mx, y + 7, fill=DIM, tags=t)
        if x > a + 3:
            rrect(cv, a, y - 3, x, y + 3, 3, fill=self.accent, outline="", tags=t)
        for f in ticks:
            tx = a + f * (b - a)
            cv.create_oval(tx - 2, y - 2, tx + 2, y + 2, fill=BG if tx <= x else DIM, outline="", tags=t)
        cv.create_oval(x - 9, y - 9, x + 9, y + 9, fill=blend(self.accent, BG, 0.65), outline="", tags=t)
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
        self._icon_btn("lock", *self.lock_geo, 19, "lock" if self.seed_locked else "unlock", self._toggle_lock,
                       square=True, color=self.accent if self.seed_locked else TEXT, tip="Seed'i sabitle")

    def draw_gen(self):
        if self.busy:
            self._pill("gen", self.gen_geo, "Üretiliyor…", None, CHIP, CHIP, MUTED, self.f_h, enabled=False)
        else:
            self._pill("gen", self.gen_geo, "▶  Seslendir", self.play, self.accent, blend(self.accent, TEXT, 0.3),
                       BG, self.f_h)

    def draw_play(self):
        cv, (x, y), t = self.cv, self.play_geo, ("ui", "play")
        cv.delete("play")
        cv.create_oval(x - 20, y - 20, x + 20, y + 20, fill=CHIP_HI if self.busy else TEXT, outline="", tags=t)
        if self.playing:
            cv.create_rectangle(x - 5, y - 5, x + 5, y + 5, fill=BG, outline="", tags=t)
        else:
            cv.create_polygon(x - 4, y - 8, x - 4, y + 8, x + 8, y, fill=BG, outline="", tags=t)
        self.hit("play", (x - 20, y - 20, x + 20, y + 20), click=self.toggle)

    def draw_save(self):
        self._icon_btn("save", *self.save_geo, 11, "download", self.save, enabled=self.speech is not None,
                       scale=0.6, tip="WAV olarak kaydet")

    def draw_wave(self, phase=None):
        cv, (a, b, y, hgt), t = self.cv, self.wave_geo, ("ui", "wave")
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

    # ----- state -----
    def set_theme(self, name):
        if name != self.theme:
            self.theme = name
            self.build()

    def _settings_target(self):
        return 284 if self.settings_open else 48

    def toggle_settings(self):
        self.settings_open = not self.settings_open
        self.slide_from, self.slide_t0 = self.settings_h, time.perf_counter()
        if not self.animating:
            self.animating = True
            self._slide()

    def _slide(self):
        t = min((time.perf_counter() - self.slide_t0) / 0.35, 1)
        ease = 1 - (1 - t) ** 3  # ease-out cubic
        self.settings_h = self.slide_from + (self._settings_target() - self.slide_from) * ease
        self.animating = t < 1
        self.build()
        if self.animating:
            self.root.after(15, self._slide)

    def _speed_at(self, x, _y):
        a, b, _ = self.speed_geo
        t = min(max((x - a) / (b - a), 0), 1)
        v = SPEED_MIN * (SPEED_MAX / SPEED_MIN) ** t
        self.set_speed(1.0 if abs(v - 1.0) < 0.04 else round(v / 0.05) * 0.05)  # magnet at normal speed

    def set_speed(self, v):
        self.speed = round(min(max(v, SPEED_MIN), SPEED_MAX), 2)
        if self.settings_open:
            self.draw_speed()

    def _rate_at(self, x, _y):
        a, b, _ = self.rate_geo
        self.set_rate_index(round((x - a) / (b - a) * (len(RATES) - 1)))

    def set_rate_index(self, i):
        i = min(max(i, 0), len(RATES) - 1)
        if RATES[i] != self.rate:
            self.rate = RATES[i]
            self.draw_rate()

    def status(self, txt, col=MUTED):
        if len(txt) > 30:  # narrow title row: show a short version, keep the full text in the terminal
            print(txt, file=sys.stderr)
            txt = txt[:29] + "…"
        self.status_text, self.status_col = txt, col
        self.cv.itemconfigure(self.status_id, text=txt, fill=col)

    def _text_changed(self, _):
        self.text.edit_modified(False)
        self._update_count()

    def _update_count(self):
        n = len(self.text.get("1.0", "end-1c"))
        self.cv.itemconfigure(self.count_id, text=f"{n} karakter")

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

    def _last_seed_text(self):
        return f"Son kullanılan seed: {self.speech.seed}" if self.speech else ""

    def _space(self, e):
        if e.widget in (self.text, self.seed_entry):
            return
        self.toggle()
        return "break"

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
            t = time.perf_counter()
            sp = self.tts.say(text, speed=speed, seed=seed, sample_rate=rate)
            self.events.put(("done", (key, sp, time.perf_counter() - t)))
        except Exception as e:
            self.events.put(("error", str(e)))

    def _animate(self):
        if self.root.state() != "iconic":
            self.bg.frame(time.perf_counter() - self.t0)
        self.root.after(1000 // FPS, self._animate)

    def _poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(val)
        except queue.Empty:
            pass
        if self.busy:
            self.draw_wave(time.perf_counter() * 6)
        if self.playing:
            pos = self.play_off + time.perf_counter() - self.play_t0
            dur = self.speech.duration
            if pos >= dur:
                self.playing = False
                self.progress = 1.0
                self.draw_play()
                pos = dur
            else:
                self.progress = pos / dur
            self.draw_wave()
            self._set_time(pos)
        self.root.after(33, self._poll)

    def _on_status(self, v):
        self.status(*v)

    def _on_ready(self, dev):
        self.status("")

    def _on_error(self, msg):
        self.busy = False
        self.draw_gen()
        self.draw_play()
        self.status(f"{msg}", DANGER)
        self.draw_wave()

    def _on_done(self, val):
        key, sp, took = val
        self.busy = False
        self.speech, self.speech_key = sp, key
        a, b, _, _ = self.wave_geo
        peaks = np.array([c.max() if len(c) else 0 for c in np.array_split(np.abs(sp.audio), int((b - a) // 3))])
        self.bars, self.progress = peaks / (peaks.max() or 1), 0.0
        self.draw_gen()
        self.draw_save()
        if self.seed_locked:
            self._seed_set(str(sp.seed))
        if self.last_seed_id:
            self.cv.itemconfigure(self.last_seed_id, text=self._last_seed_text())
        self.status("")
        self._start(0.0)

    # ----- actions -----
    def play(self):
        if self.busy:
            return
        if self.tts is None:
            self.status("Model henüz yüklenmedi, bekle…", MUTED)
            return
        try:
            key = self._params()
        except ValueError as e:
            self.status(f"{e}", DANGER)
            return
        if not key[0]:
            self.status("Önce bir metin yaz", DANGER)
            return
        self.stop()
        if self.speech is not None and key == self.speech_key and key[2] is not None:
            self._start(0.0)  # same text + same fixed seed: replay without regenerating
            return
        self.busy = True
        self.draw_gen()
        self.draw_play()
        self.status("Seslendiriliyor…", self.accent2)
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
        self.draw_play()

    def stop(self):
        if self.playing:
            sd.stop()
            self.playing = False
            self.draw_play()

    def seek(self, frac):
        if self.speech is None or self.busy:
            return
        self._start(min(max(frac, 0), 1) * self.speech.duration)

    def _set_time(self, pos):
        self.cv.itemconfigure(self.time_id, text=f"{int(pos // 60)}:{int(pos % 60):02d}")

    def save(self):
        if self.speech is None:
            return
        from ema_lightning.audio import write_wav

        path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile="ema.wav",
                                            filetypes=[("WAV", "*.wav")])
        if path:
            write_wav(path, self.speech.audio, self.speech.sample_rate)
            self.status(f"Kaydedildi: {Path(path).name}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
