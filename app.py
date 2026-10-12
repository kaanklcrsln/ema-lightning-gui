"""EMA Lightning Studio: dark glass Tkinter GUI for Turkish TTS.

Run:  .venv/bin/python app.py
"""
import math
import queue
import random
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog

import numpy as np
import sounddevice as sd

HERE = Path(__file__).resolve().parent

# ---------- palette ----------
BG_TOP = "#0b0d14"
BG_BOT = "#11131f"
CARD = "#161925"
CARD_HI = "#1d2130"
BORDER = "#2a2f42"
BORDER_HI = "#3a4160"
TEXT = "#e8eaf2"
MUTED = "#8a90a6"
DIM = "#5a6078"
ACCENT = "#8b7cff"
ACCENT_2 = "#5ad1ff"
ACCENT_HOVER = "#a294ff"
DANGER = "#ff6b8a"

RATES = (48000, 24000, 16000, 8000)
SPEED_MIN, SPEED_MAX = 0.25, 4.0

HELP = [
    ("Metin", "Seslendirmek istediğin Türkçe metni yaz. Sayılar, tarihler ve para birimleri otomatik okunur "
              "(ör. \"14:30\" → \"on dört otuz\"). Model tek ses ve sadece Türkçe destekler."),
    ("Seslendir / Oynat", "▶ butonu metni seslendirir ve hemen çalar. Metin veya ayarlar değişmediyse aynı sesi "
                          "yeniden üretmeden tekrar çalar. Kısayol: ⌘ + Enter. Çalarken ■ ile durdur."),
    ("Hız (speed)", "0.25× ile 4× arası. 1.0 normal hız. Çift tıklayınca 1.0'a döner."),
    ("Seed", "Aynı seed + aynı metin = birebir aynı ses. Boş bırakırsan her seferinde rastgele seçilir; "
             "kullanılan seed altta gösterilir. 🎲 yeni rastgele seed yazar, kilit ikonu sabitler."),
    ("Örnekleme hızı", "Çıkış kalitesi. 48 kHz en yüksek kalite; 8 kHz telefon hattı içindir. "
                       "Model her zaman 48 kHz üretir, diğerleri yeniden örneklenir."),
    ("Kaydet", "Son üretilen sesi .wav olarak kaydeder."),
    ("Not", "Mac'te model CPU'da çalışır. İlk üretim ısınma nedeniyle birkaç saniye sürebilir, "
            "sonrakiler çok daha hızlıdır."),
]


def pick_font(root, *names):
    fams = set(tkfont.families(root))
    for n in names:
        if n in fams:
            return n
    return "Helvetica"


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def rrect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


# ---------- widgets ----------
class Pill(tk.Canvas):
    """Rounded button drawn on a canvas (macOS ignores tk.Button colors)."""

    def __init__(self, master, text, command, w=120, h=40, bg=CARD, fill=CARD_HI, fg=TEXT,
                 hover=BORDER, border=BORDER, font=None, radius=None):
        super().__init__(master, width=w, height=h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h, self.r = w, h, radius if radius is not None else h // 2
        self.fill, self.hover_fill, self.fg, self.border = fill, hover, fg, border
        self.command, self.font, self.text, self.enabled = command, font, text, True
        self.bind("<Enter>", lambda e: self._draw(True))
        self.bind("<Leave>", lambda e: self._draw(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._draw(False)

    def _draw(self, hover):
        self.delete("all")
        fill = self.hover_fill if hover and self.enabled else self.fill
        rrect(self, 1, 1, self.w - 1, self.h - 1, self.r, fill=fill, outline=self.border)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=self.fg if self.enabled else DIM,
                         font=self.font)

    def set(self, text=None, enabled=None):
        if text is not None:
            self.text = text
        if enabled is not None:
            self.enabled = enabled
        self._draw(False)

    def _click(self, _):
        if self.enabled and self.command:
            self.command()


class Tooltip:
    def __init__(self, widget, text, font):
        self.widget, self.text, self.font, self.tip = widget, text, font, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() - 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.configure(bg=BORDER_HI)
        tk.Label(self.tip, text=self.text, bg=CARD_HI, fg=TEXT, font=self.font, justify="left",
                 wraplength=260, padx=10, pady=8).pack(padx=1, pady=1)
        self.tip.wm_geometry(f"+{x}+{y}")

    def hide(self, _):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class InfoDot(tk.Canvas):
    """Small round '?' with hover tooltip."""

    def __init__(self, master, text, font, small_font, bg=CARD):
        super().__init__(master, width=18, height=18, bg=bg, highlightthickness=0, cursor="question_arrow")
        self.create_oval(1, 1, 17, 17, outline=BORDER_HI, fill=CARD_HI)
        self.create_text(9, 9, text="?", fill=MUTED, font=small_font)
        Tooltip(self, text, font)


class SpeedSlider(tk.Canvas):
    """Log-scale slider so 1.0x sits in the middle of 0.25..4."""

    def __init__(self, master, var, w=280, h=28, on_change=None):
        super().__init__(master, width=w, height=h, bg=CARD, highlightthickness=0, cursor="hand2")
        self.var, self.w, self.h, self.on_change, self.pad = var, w, h, on_change, 10
        for ev in ("<Button-1>", "<B1-Motion>"):
            self.bind(ev, self._drag)
        self.bind("<Double-Button-1>", lambda e: self._set(1.0))
        self._draw()

    def _pos(self, v):
        t = math.log(v / SPEED_MIN) / math.log(SPEED_MAX / SPEED_MIN)
        return self.pad + t * (self.w - 2 * self.pad)

    def _drag(self, e):
        t = min(max((e.x - self.pad) / (self.w - 2 * self.pad), 0), 1)
        v = SPEED_MIN * (SPEED_MAX / SPEED_MIN) ** t
        if abs(v - 1.0) < 0.04:
            v = 1.0  # magnet at normal speed
        self._set(round(v / 0.05) * 0.05)

    def _set(self, v):
        self.var.set(round(min(max(v, SPEED_MIN), SPEED_MAX), 2))
        self._draw()
        if self.on_change:
            self.on_change()

    def _draw(self):
        self.delete("all")
        cy, x = self.h / 2, self._pos(self.var.get())
        rrect(self, self.pad, cy - 3, self.w - self.pad, cy + 3, 3, fill=BORDER, outline="")
        mid = self._pos(1.0)
        self.create_line(mid, cy - 7, mid, cy + 7, fill=DIM)
        if x > self.pad + 3:
            rrect(self, self.pad, cy - 3, x, cy + 3, 3, fill=ACCENT, outline="")
        self.create_oval(x - 9, cy - 9, x + 9, cy + 9, fill=blend(ACCENT, "#000000", 0.6), outline="")
        self.create_oval(x - 7, cy - 7, x + 7, cy + 7, fill=TEXT, outline=ACCENT, width=2)


class Segmented(tk.Canvas):
    def __init__(self, master, options, var, font, w=280, h=34, on_change=None):
        super().__init__(master, width=w, height=h, bg=CARD, highlightthickness=0, cursor="hand2")
        self.options, self.var, self.font, self.w, self.h, self.on_change = options, var, font, w, h, on_change
        self.bind("<Button-1>", self._click)
        self._draw()

    def _click(self, e):
        i = min(int(e.x / (self.w / len(self.options))), len(self.options) - 1)
        self.var.set(self.options[i])
        self._draw()
        if self.on_change:
            self.on_change()

    def _draw(self):
        self.delete("all")
        rrect(self, 1, 1, self.w - 1, self.h - 1, 10, fill=BG_BOT, outline=BORDER)
        seg = self.w / len(self.options)
        for i, o in enumerate(self.options):
            x1 = i * seg
            on = o == self.var.get()
            if on:
                rrect(self, x1 + 4, 4, x1 + seg - 4, self.h - 4, 8, fill=CARD_HI, outline=BORDER_HI)
            self.create_text(x1 + seg / 2, self.h / 2, text=f"{o // 1000} kHz",
                             fill=TEXT if on else MUTED, font=self.font)


class Waveform(tk.Canvas):
    def __init__(self, master, w, h, font):
        super().__init__(master, width=w, height=h, bg=CARD, highlightthickness=0, cursor="hand2")
        self.w, self.h, self.font, self.bars, self.progress = w, h, font, None, 0.0
        self.on_seek = None
        self.bind("<Button-1>", lambda e: self.on_seek and self.on_seek(min(max(e.x / self.w, 0), 1)))
        self.idle()

    def idle(self, msg="Henüz ses yok — metni yaz ve ▶'ye bas"):
        self.bars = None
        self.delete("all")
        n = 90
        for i in range(n):
            x = (i + 0.5) * self.w / n
            self.create_line(x, self.h / 2 - 1, x, self.h / 2 + 1, fill=BORDER, width=2, capstyle="round")
        self.create_text(self.w / 2, self.h / 2, text=msg, fill=DIM, font=self.font)

    def busy(self, phase):
        self.delete("all")
        n = 90
        for i in range(n):
            x = (i + 0.5) * self.w / n
            a = (math.sin(i * 0.25 - phase) * 0.5 + 0.5) * (math.sin(i * 0.07 + phase * 0.5) * 0.3 + 0.7)
            hh = 2 + a * (self.h * 0.32)
            self.create_line(x, self.h / 2 - hh, x, self.h / 2 + hh, fill=blend(BORDER_HI, ACCENT, a),
                             width=2, capstyle="round")

    def load(self, audio):
        n = 140
        chunks = np.array_split(np.abs(audio), n)
        peaks = np.array([c.max() if len(c) else 0 for c in chunks])
        self.bars = peaks / (peaks.max() or 1)
        self.progress = 0.0
        self.draw()

    def draw(self):
        if self.bars is None:
            return
        self.delete("all")
        n = len(self.bars)
        for i, a in enumerate(self.bars):
            x = (i + 0.5) * self.w / n
            hh = 1.5 + a * (self.h * 0.42)
            played = i / n < self.progress
            col = blend(ACCENT, ACCENT_2, i / n) if played else BORDER_HI
            self.create_line(x, self.h / 2 - hh, x, self.h / 2 + hh, fill=col, width=2, capstyle="round")
        if 0 < self.progress < 1:
            px = self.progress * self.w
            self.create_line(px, 4, px, self.h - 4, fill=TEXT, width=1)


# ---------- app ----------
class App:
    W, H = 980, 700

    def __init__(self, root):
        self.root = root
        root.title("EMA Lightning Studio")
        root.geometry(f"{self.W}x{self.H}")
        root.minsize(self.W, self.H)
        root.resizable(False, False)
        root.configure(bg=BG_TOP)

        fam = pick_font(root, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "Inter", "Helvetica")
        mono = pick_font(root, "SF Mono", "Menlo", "Monaco", "Courier")
        self.f_title = (fam, 18, "bold")
        self.f_h = (fam, 13, "bold")
        self.f = (fam, 13)
        self.f_s = (fam, 11)
        self.f_xs = (fam, 10, "bold")
        self.f_text = (fam, 16)
        self.f_mono = (mono, 12)

        self.tts = None
        self.speech = None
        self.speech_key = None
        self.playing = False
        self.play_t0 = 0.0
        self.play_off = 0.0
        self.busy = False
        self.events = queue.Queue()

        self.speed = tk.DoubleVar(value=1.0)
        self.rate = tk.IntVar(value=48000)
        self.seed = tk.StringVar(value="")
        self.seed_locked = False

        self.cv = tk.Canvas(root, width=self.W, height=self.H, bg=BG_TOP, highlightthickness=0)
        self.cv.place(x=0, y=0)
        self._background()
        self._header()
        self._editor()
        self._settings()
        self._player()

        root.bind("<Command-Return>", lambda e: self.play())
        root.bind("<Control-Return>", lambda e: self.play())
        root.bind("<space>", self._space)
        root.bind("<Escape>", lambda e: self.stop())
        self._poll()
        threading.Thread(target=self._load_model, daemon=True).start()

    # ----- layout -----
    def _background(self):
        cv = self.cv
        for y in range(0, self.H, 2):
            cv.create_line(0, y, self.W, y, fill=blend(BG_TOP, BG_BOT, y / self.H), width=2)
        # soft glow blobs: stacked ovals fading into the background
        for cx, cy, r, col in ((140, 80, 260, ACCENT), (self.W - 120, self.H - 60, 300, ACCENT_2)):
            for i in range(40, 0, -1):
                rr = r * i / 40
                cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="",
                               fill=blend(BG_TOP, col, 0.10 * (1 - i / 40) ** 1.6))

    def _card(self, x1, y1, x2, y2, title=None):
        cv = self.cv
        rrect(cv, x1 + 2, y1 + 6, x2 + 2, y2 + 8, 18, fill=blend(BG_TOP, "#000000", 0.5), outline="")  # shadow
        rrect(cv, x1, y1, x2, y2, 18, fill=CARD, outline=BORDER)
        cv.create_line(x1 + 18, y1 + 1, x2 - 18, y1 + 1, fill=BORDER_HI)  # glass rim highlight
        if title:
            cv.create_text(x1 + 22, y1 + 24, text=title, anchor="w", fill=MUTED, font=self.f_xs)

    def _header(self):
        cv = self.cv
        cv.create_oval(28, 24, 60, 56, fill=ACCENT, outline="")
        cv.create_text(44, 40, text="⚡", fill="white", font=self.f_h)
        cv.create_text(72, 32, text="EMA Lightning", anchor="w", fill=TEXT, font=self.f_title)
        cv.create_text(72, 52, text="Türkçe metin → ses  ·  8.6M parametre  ·  offline", anchor="w",
                       fill=MUTED, font=self.f_s)
        self.status_id = cv.create_text(self.W - 80, 40, text="● Model yükleniyor…", anchor="e",
                                        fill=MUTED, font=self.f_s)
        help_btn = Pill(cv, "?", self.show_help, w=36, h=36, bg=BG_TOP, fill=CARD_HI, hover=BORDER_HI,
                        border=BORDER_HI, font=self.f_h)
        cv.create_window(self.W - 50, 40, window=help_btn)

    def _editor(self):
        x1, y1, x2, y2 = 28, 80, 640, 500
        self._card(x1, y1, x2, y2, "METİN")
        self.text = tk.Text(self.cv, wrap="word", bg=CARD, fg=TEXT, insertbackground=ACCENT, relief="flat",
                            highlightthickness=0, bd=0, font=self.f_text, padx=4, pady=4, undo=True,
                            selectbackground=blend(CARD, ACCENT, 0.4), selectforeground=TEXT, spacing2=4)
        self.cv.create_window(x1 + 20, y1 + 44, window=self.text, anchor="nw",
                              width=x2 - x1 - 40, height=y2 - y1 - 110)
        self.text.insert("1.0", "Merhaba! Ben EMA. Yazdığın her şeyi saniyeler içinde Türkçe seslendirebilirim.")
        self.text.bind("<<Modified>>", self._text_changed)

        self.count_id = self.cv.create_text(x1 + 22, y2 - 32, anchor="w", fill=DIM, font=self.f_s)
        clear = Pill(self.cv, "Temizle", lambda: self.text.delete("1.0", "end"), w=84, h=34, font=self.f_s)
        self.cv.create_window(x2 - 270, y2 - 32, window=clear)
        self.gen_btn = Pill(self.cv, "▶  Seslendir", self.play, w=150, h=40, fill=ACCENT, hover=ACCENT_HOVER,
                            border=ACCENT, fg="white", font=self.f_h)
        self.cv.create_window(x2 - 100, y2 - 32, window=self.gen_btn)
        self.cv.create_text(x2 - 175, y2 - 62, text="⌘ + Enter", anchor="w", fill=DIM, font=self.f_s)
        self._update_count()

    def _settings(self):
        x1, y1, x2, y2 = 660, 80, self.W - 28, 500
        self._card(x1, y1, x2, y2, "SES AYARLARI")
        cv, cx, w = self.cv, x1 + 22, x2 - x1 - 44
        tips = dict(HELP)

        def label(y, txt, tip):
            cv.create_text(cx, y, text=txt, anchor="w", fill=TEXT, font=self.f_h)
            dot = InfoDot(cv, tip, self.f_s, self.f_xs)
            cv.create_window(cx + tkfont.Font(font=self.f_h).measure(txt) + 16, y, window=dot)

        # speed
        label(y1 + 66, "Hız", tips["Hız (speed)"])
        self.speed_lbl = cv.create_text(x2 - 22, y1 + 66, anchor="e", fill=ACCENT_2, font=self.f_mono)
        self.slider = SpeedSlider(cv, self.speed, w=w, on_change=self._settings_changed)
        cv.create_window(cx, y1 + 98, window=self.slider, anchor="w")
        cv.create_text(cx + 8, y1 + 120, text="Yavaş", anchor="w", fill=DIM, font=self.f_s)
        cv.create_text(x2 - 30, y1 + 120, text="Hızlı", anchor="e", fill=DIM, font=self.f_s)

        # sample rate
        label(y1 + 160, "Örnekleme hızı", tips["Örnekleme hızı"])
        seg = Segmented(cv, RATES, self.rate, self.f_s, w=w, on_change=self._settings_changed)
        cv.create_window(cx, y1 + 194, window=seg, anchor="w")

        # seed
        label(y1 + 240, "Seed", tips["Seed"])
        frame = tk.Canvas(cv, width=w, height=40, bg=CARD, highlightthickness=0)
        rrect(frame, 1, 1, w - 92, 39, 10, fill=BG_BOT, outline=BORDER)
        self.seed_entry = tk.Entry(frame, textvariable=self.seed, bg=BG_BOT, fg=TEXT, insertbackground=ACCENT,
                                   relief="flat", highlightthickness=0, bd=0, font=self.f_mono)
        frame.create_window(12, 20, window=self.seed_entry, anchor="w", width=w - 116)
        self.seed_ph = frame.create_text(14, 20, text="rastgele", anchor="w", fill=DIM, font=self.f_mono)
        self.seed.trace_add("write", lambda *_: (frame.itemconfigure(
            self.seed_ph, state="hidden" if self.seed.get() else "normal"), self._settings_changed()))
        dice = Pill(frame, "🎲", self._random_seed, w=40, h=38, font=self.f, radius=10)
        frame.create_window(w - 66, 20, window=dice)
        self.lock = Pill(frame, "🔓", self._toggle_lock, w=40, h=38, font=self.f, radius=10)
        frame.create_window(w - 20, 20, window=self.lock)
        Tooltip(dice, "Yeni rastgele seed yaz", self.f_s)
        Tooltip(self.lock, "Kilitliyken seed her üretimde sabit kalır.\nAçıkken ve kutu boşsa her seferinde rastgele.",
                self.f_s)
        cv.create_window(cx, y1 + 274, window=frame, anchor="w")
        self.last_seed_id = cv.create_text(cx, y1 + 306, text="", anchor="w", fill=DIM, font=self.f_s)

        # info
        cv.create_line(cx, y1 + 336, x2 - 22, y1 + 336, fill=BORDER)
        self.info_id = cv.create_text(cx, y1 + 350, anchor="nw", fill=MUTED, font=self.f_s, width=w,
                                      text="Tek ses · Türkçe · 48 kHz\nCPU modunda çalışıyor")
        self._settings_changed()

    def _player(self):
        x1, y1, x2, y2 = 28, 520, self.W - 28, self.H - 24
        self._card(x1, y1, x2, y2)
        cv = self.cv
        self.play_btn = tk.Canvas(cv, width=56, height=56, bg=CARD, highlightthickness=0, cursor="hand2")
        self.play_btn.bind("<ButtonRelease-1>", lambda e: self.toggle())
        self._draw_play_btn()
        cv.create_window(x1 + 50, (y1 + y2) / 2, window=self.play_btn)

        self.wave = Waveform(cv, x2 - x1 - 280, 90, self.f_s)
        self.wave.on_seek = self.seek
        cv.create_window(x1 + 92, (y1 + y2) / 2 - 8, window=self.wave, anchor="w")
        self.time_id = cv.create_text(x1 + 92, y2 - 20, text="0:00 / 0:00", anchor="w", fill=MUTED,
                                      font=self.f_mono)
        self.meta_id = cv.create_text(x2 - 196, y2 - 20, text="", anchor="e", fill=DIM, font=self.f_s)
        self.save_btn = Pill(cv, "⤓  Kaydet", self.save, w=130, h=40, font=self.f)
        self.save_btn.set(enabled=False)
        cv.create_window(x2 - 90, (y1 + y2) / 2, window=self.save_btn)

    def _draw_play_btn(self):
        c = self.play_btn
        c.delete("all")
        c.create_oval(2, 2, 54, 54, fill=TEXT if not self.busy else BORDER_HI, outline="")
        if self.playing:
            c.create_rectangle(21, 21, 35, 35, fill=BG_TOP, outline="")
        else:
            c.create_polygon(23, 18, 23, 38, 39, 28, fill=BG_TOP, outline="")

    # ----- state -----
    def status(self, txt, col=MUTED):
        self.cv.itemconfigure(self.status_id, text=txt, fill=col)

    def _text_changed(self, _):
        self.text.edit_modified(False)
        self._update_count()

    def _update_count(self):
        n = len(self.text.get("1.0", "end-1c"))
        self.cv.itemconfigure(self.count_id, text=f"{n} karakter")

    def _settings_changed(self):
        self.cv.itemconfigure(self.speed_lbl, text=f"{self.speed.get():.2f}×")

    def _random_seed(self):
        self.seed.set(str(random.randrange(0, 2 ** 31)))

    def _toggle_lock(self):
        self.seed_locked = not self.seed_locked
        self.lock.set(text="🔒" if self.seed_locked else "🔓")
        if self.seed_locked and not self.seed.get() and self.speech:
            self.seed.set(str(self.speech.seed))

    def _space(self, e):
        if e.widget in (self.text, self.seed_entry):
            return
        self.toggle()
        return "break"

    def _params(self):
        text = self.text.get("1.0", "end-1c").strip()
        s = self.seed.get().strip()
        if s and not s.isdigit():
            raise ValueError("Seed pozitif bir tam sayı olmalı")
        return text, round(self.speed.get(), 2), int(s) if s else None, self.rate.get()

    # ----- model -----
    def _load_model(self):
        try:
            import torch
            from ema_lightning import EMA
            from ema_lightning.decoder import load_decoder
            from ema_lightning.frontend import Frontend
            from ema_lightning.model import load_acoustic

            dev = "cuda" if torch.cuda.is_available() else "cpu"
            ema, dec = HERE / "ema.pt", HERE / "decoder.pt"
            if ema.exists() and dec.exists():  # use the weights cloned next to this file
                m = load_acoustic(str(ema), dev)
                tts = EMA._from_parts(m, load_decoder(str(dec), dev), Frontend(m.vocab), dev)
            else:
                tts = EMA(dev)
            self.events.put(("status", ("● Isınıyor…", MUTED)))
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

    def _poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(val)
        except queue.Empty:
            pass
        if self.busy:
            self.wave.busy(time.perf_counter() * 6)
        if self.playing:
            pos = self.play_off + time.perf_counter() - self.play_t0
            dur = self.speech.duration
            if pos >= dur:
                self.playing = False
                self.wave.progress = 1.0
                self._draw_play_btn()
                pos = dur
            else:
                self.wave.progress = pos / dur
            self.wave.draw()
            self._set_time(pos)
        self.root.after(33, self._poll)

    def _on_status(self, v):
        self.status(*v)

    def _on_ready(self, dev):
        self.status(f"● Hazır  ·  {dev.upper()}", "#5be3a0")
        self.cv.itemconfigure(self.info_id, text=f"Tek ses · Türkçe · 48 kHz\n{dev.upper()} modunda çalışıyor")

    def _on_error(self, msg):
        self.busy = False
        self.gen_btn.set("▶  Seslendir", enabled=True)
        self._draw_play_btn()
        self.status(f"● {msg}", DANGER)
        if self.speech is None:
            self.wave.idle("Hata — ayrıntı sağ üstte")
        else:
            self.wave.draw()

    def _on_done(self, val):
        key, sp, took = val
        self.busy = False
        self.speech, self.speech_key = sp, key
        self.gen_btn.set("▶  Seslendir", enabled=True)
        self.save_btn.set(enabled=True)
        self.wave.load(sp.audio)
        if self.seed_locked:
            self.seed.set(str(sp.seed))
        self.cv.itemconfigure(self.last_seed_id, text=f"Son kullanılan seed: {sp.seed}")
        self.cv.itemconfigure(self.meta_id, text=f"{sp.sample_rate // 1000} kHz · {took:.2f} sn'de üretildi")
        self.status(f"● Hazır  ·  {sp.duration / took:.0f}× gerçek zaman", "#5be3a0")
        self._start(0.0)

    # ----- actions -----
    def play(self):
        if self.busy:
            return
        if self.tts is None:
            self.status("● Model henüz yüklenmedi, bekle…", MUTED)
            return
        try:
            key = self._params()
        except ValueError as e:
            self.status(f"● {e}", DANGER)
            return
        if not key[0]:
            self.status("● Önce bir metin yaz", DANGER)
            return
        self.stop()
        if self.speech is not None and key == self.speech_key and key[2] is not None:
            self._start(0.0)  # same text + same fixed seed: replay without regenerating
            return
        self.busy = True
        self.gen_btn.set("Üretiliyor…", enabled=False)
        self._draw_play_btn()
        self.status("● Seslendiriliyor…", ACCENT_2)
        threading.Thread(target=self._generate, args=(key,), daemon=True).start()

    def toggle(self):
        if self.busy:
            return
        if self.playing:
            self.stop()
        elif self.speech is not None and self.speech_key == self._safe_params():
            start = 0.0 if self.wave.progress >= 1 else self.wave.progress * self.speech.duration
            self._start(start)
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
        self._draw_play_btn()

    def stop(self):
        if self.playing:
            sd.stop()
            self.playing = False
            self._draw_play_btn()

    def seek(self, frac):
        if self.speech is None or self.busy:
            return
        self._start(frac * self.speech.duration)

    def _set_time(self, pos):
        f = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"
        self.cv.itemconfigure(self.time_id, text=f"{f(pos)} / {f(self.speech.duration)}")

    def save(self):
        if self.speech is None:
            return
        from ema_lightning.audio import write_wav

        path = filedialog.asksaveasfilename(defaultextension=".wav", initialfile="ema.wav",
                                            filetypes=[("WAV", "*.wav")])
        if path:
            write_wav(path, self.speech.audio, self.speech.sample_rate)
            self.status(f"● Kaydedildi: {Path(path).name}", "#5be3a0")

    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title("Nasıl kullanılır?")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self.root)
        tk.Label(win, text="Nasıl kullanılır?", bg=CARD, fg=TEXT, font=self.f_title, anchor="w").pack(
            fill="x", padx=28, pady=(24, 4))
        tk.Label(win, text="EMA Lightning · Türkçe metin → ses", bg=CARD, fg=MUTED, font=self.f_s,
                 anchor="w").pack(fill="x", padx=28, pady=(0, 14))
        for title, body in HELP:
            row = tk.Frame(win, bg=CARD)
            row.pack(fill="x", padx=28, pady=6)
            tk.Label(row, text=title, bg=CARD, fg=ACCENT_2, font=self.f_h, anchor="w", width=16).pack(
                side="left", anchor="n")
            tk.Label(row, text=body, bg=CARD, fg=TEXT, font=self.f, anchor="w", justify="left",
                     wraplength=400).pack(side="left", fill="x")
        tk.Label(win, text="Kısayollar:  ⌘+Enter seslendir  ·  Boşluk oynat/durdur  ·  Esc durdur",
                 bg=CARD, fg=DIM, font=self.f_s).pack(padx=28, pady=(14, 8))
        Pill(win, "Anladım", win.destroy, w=120, h=38, bg=CARD, fill=ACCENT, hover=ACCENT_HOVER,
             border=ACCENT, fg="white", font=self.f_h).pack(pady=(4, 24))
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.W - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + 60
        win.geometry(f"+{x}+{y}")
        win.focus_set()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
