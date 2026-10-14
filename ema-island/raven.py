"""Raven: the voice assistant behind EMA Island.

    Ear    microphone -> voice activity -> "Raven" wake word -> records the request until 3 s of
           silence -> speech-to-text (local Whisper on MLX)
    Brain  the request -> Gemini (newest Flash) or Claude, streamed; the conversation lives in memory only
    Mouth  streamed reply -> sentences -> EMA Lightning -> speakers, one sentence while the next is made

Each part runs on its own thread and reports to the UI through post(kind, value).
"""
import datetime
import difflib
import os
import queue
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

SR = 16000
FRAME = 512  # silero-vad takes 32 ms frames at 16 kHz
FRAME_S = FRAME / SR
WAKE_MODEL = "mlx-community/whisper-base-mlx"  # fast enough to check every utterance for the wake word
STT_MODEL = "mlx-community/whisper-small-mlx"  # the request itself: ~0.5 s for a sentence on Apple Silicon
SILENCE_END = 3.0  # seconds of quiet that end a request
WAIT_FOR_SPEECH = 8.0  # after the wake word, give up if nothing is said
MAX_REQUEST = 60.0
WAKE_WORDS = ("raven", "reyvin", "reyven", "rayvin", "rayven", "reven", "revin", "reyvn")
HALLUCINATIONS = ("altyazı", "abone ol", "izlediğiniz için")  # Whisper's usual inventions on near-silence
CLAUDE_MODEL = "claude-haiku-5-5"
ENV_FILES = (Path(__file__).resolve().parent.parent / ".env", Path(__file__).resolve().parent / ".env")
GEMINI_COOLDOWN = 300  # seconds an overloaded model is skipped before it is tried again
GEMINI_QUOTA_WAIT = 60  # skip a model whose quota ran out this long, unless Google says how long
GEMINI_BUDGET = 25  # seconds spent going down the model list before a request gives up
GEMINI_TIMEOUT_MS = 10000  # longest wait before trying the next model; also sent to Google, whose minimum is 10 s
NO_KEY = "API anahtarı henüz eklenmedi. Proje klasöründeki ayar dosyasına Gemini anahtarını yazman gerekiyor."
MAX_HISTORY = 40  # messages; past this a new conversation starts (history is never edited, only dropped)

TR_FOLD = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iissgguuooccaaiiuu")


def fold(text):
    """Lowercase ASCII-ish Turkish, letters and spaces only, for fuzzy wake-word matching."""
    return re.sub(r"[^a-z ]+", " ", text.translate(TR_FOLD).lower()).split()


def find_wake(text):
    """Index of the word after the wake word in text.split(), or None if there is no wake word."""
    for i, w in enumerate(fold(text)):
        if w in WAKE_WORDS or (4 <= len(w) <= 7 and max(difflib.SequenceMatcher(None, w, k).ratio()
                                                          for k in WAKE_WORDS) >= 0.8):
            return i + 1
    return None


def transcribe(audio, repo, prompt="Raven"):
    import mlx_whisper

    r = mlx_whisper.transcribe(audio.astype(np.float32), path_or_hf_repo=repo, language="tr", temperature=0.0,
                               compression_ratio_threshold=None, logprob_threshold=None,
                               condition_on_previous_text=False, initial_prompt=prompt)
    text = r["text"].strip()
    return "" if any(h in text.lower() for h in HALLUCINATIONS) else text


class Ear:
    """Always-on microphone with a small state machine.

    mode "wake":   cut speech into utterances; post ("wake", rest) when one starts with "Raven"
    mode "listen": record until SILENCE_END of quiet, then post ("heard", text)
    mode "pause":  ignore the microphone (while Raven speaks, so it doesn't hear itself)
    """

    def __init__(self, post):
        self.post = post
        self.mode = "pause"
        self.enabled = True
        self.level = 0.0  # mic loudness 0..1 for the UI
        self.silence_left = None  # seconds until the request is taken, while listening
        self.frames = queue.Queue(maxsize=600)
        self.clock = 0.0  # audio time in seconds, counted in frames: frames queued during a transcription
        # are worked through later, so wall-clock time would mis-measure the silences
        self.stream = None
        self.prefix = ""
        threading.Thread(target=self._run, daemon=True).start()

    # called from the UI thread
    def wake(self):
        self.mode = "wake"

    def pause(self):
        self.mode = "pause"
        self.silence_left = None

    def listen(self, prefix=""):
        self.prefix = prefix
        self._listen_reset()
        self.mode = "listen"

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()

    # ear thread
    def _listen_reset(self):
        self.rec, self.heard, self.t_listen, self.t_speech = [], False, self.clock, None
        self.silence_left = None

    def _callback(self, data, frames, t, status):
        try:
            self.frames.put_nowait(data[:, 0].copy())
        except queue.Full:
            pass

    def _run(self):
        try:
            import torch
            from silero_vad import load_silero_vad

            vad = load_silero_vad()
            transcribe(np.zeros(SR, np.float32), WAKE_MODEL)  # load and warm both models
            transcribe(np.zeros(SR, np.float32), STT_MODEL)
            self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME,
                                         callback=self._callback)
            self.stream.start()
        except Exception as e:
            self.post("ear_error", f"Mikrofon açılamadı: {e}")
            return
        self.post("ear_ready", None)
        pre = deque(maxlen=10)  # ~0.3 s kept from before speech starts
        seg, quiet, silent_since = None, 0, 0.0
        while True:
            frame = self.frames.get()
            rms = float(np.sqrt(np.mean(frame ** 2)))
            self.level = max(min(rms * 12, 1.0), self.level * 0.8)
            self.clock += FRAME_S
            now = self.clock
            if frame.any():
                silent_since = now
            elif now - silent_since > 4 and silent_since >= 0:  # macOS feeds zeros without permission
                self.post("ear_error", "Mikrofon izni gerekli: Sistem Ayarları › Gizlilik › Mikrofon")
                silent_since = -1
            if self.mode == "pause" or not self.enabled:
                seg, quiet = None, 0
                pre.clear()
                continue
            with torch.no_grad():
                speech = vad(torch.from_numpy(frame), SR).item() > 0.5

            if self.mode == "wake":
                if speech:
                    seg = (seg or list(pre)) + [frame]
                    quiet = 0
                elif seg is not None:
                    seg.append(frame)
                    quiet += 1
                    if quiet * FRAME_S >= 0.5 or len(seg) * FRAME_S > 8:
                        self._check_wake(np.concatenate(seg))
                        seg, quiet = None, 0
                pre.append(frame)
            elif self.mode == "listen":
                self.rec.append(frame)
                if speech:
                    self.heard, self.t_speech = True, now
                if self.heard:
                    self.silence_left = max(SILENCE_END - (now - self.t_speech), 0)
                    if self.silence_left == 0 or now - self.t_listen > MAX_REQUEST:
                        self._finish()
                elif self.prefix and now - self.t_listen >= SILENCE_END:  # "Raven, ..." said in one breath
                    self._finish()
                elif now - self.t_listen > WAIT_FOR_SPEECH:
                    self.mode = "pause"
                    self.post("timeout", None)

    def _check_wake(self, audio):
        head = transcribe(audio[: int(2.5 * SR)], WAKE_MODEL)
        if find_wake(head) is None:
            return
        rest = ""
        if len(audio) > 1.3 * SR:  # more than the name itself: keep what came after it
            full = transcribe(audio, STT_MODEL)
            words, i = full.split(), find_wake(full)
            rest = " ".join(words[i:]) if i is not None else ""
        self.listen(rest)
        self.post("wake", rest)

    def _finish(self):
        self.mode = "pause"
        self.silence_left = None
        text = self.prefix
        if self.heard:
            end = len(self.rec) - int(max(SILENCE_END - 0.3, 0) / FRAME_S)  # drop the trailing quiet
            text = (text + " " + transcribe(np.concatenate(self.rec[:max(end, 1)]), STT_MODEL)).strip()
        self.post("heard", text)


MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
          "Aralık")
DAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")

SYSTEM = """Sen Raven'sın: MacBook'un çentiğinde yaşayan, Türkçe konuşan sesli bir asistan. Yanıtların EMA \
adlı bir ses modeliyle yüksek sesle okunuyor; kullanıcı seni dinliyor, okumuyor.

- Konuşur gibi, doğal ve kısa yanıt ver: çoğu zaman bir iki cümle. Kullanıcı ayrıntı isterse uzat.
- Markdown, madde işareti, başlık, tablo, kod bloğu, emoji ve bağlantı kullanma; bunlar sesli okunamıyor. \
Birkaç adım anlatman gerekirse "önce, sonra, son olarak" gibi cümlelerle anlat.
- Sayıları, tarihleri ve birimleri normal yaz ("15 dakika", "3,5 kilo"); ses modeli onları doğru okuyor.
- Kullanıcının söyledikleri konuşmadan yazıya çevrildi; küçük yazım hataları olabilir. Anlamı tahmin et, \
gerçekten anlaşılmıyorsa kısaca tekrar sor.
- İnternete, takvime ya da bilgisayardaki uygulamalara erişimin yok. Anlık hava durumu, haberler, borsa gibi \
bilgileri uydurma; bilemeyeceğini kısaca söyle.
- Kullanıcıya "sen" diye hitap et.

Altyapın sorulursa doğrusunu söyle: cevaplarını {model} üretiyor; sesin, Canberk Aslan'ın Türkçe ses modeli \
EMA Lightning; kullanıcının konuşması bilgisayarda Whisper ile yazıya çevriliyor. Başka bir şirketin ya da \
modelin adını uydurma."""


def keys():
    """Settings from the .env file(s) next to the project; real environment variables win.
    Read on every request, so a key added while the app runs is picked up right away."""
    vals = {}
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals.setdefault(k.strip(), v.strip().strip("\"'"))
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals


def gemini_label(name):
    """gemini-3.6-flash -> "Google'ın Gemini 3.6 Flash modeli", for the system prompt."""
    words = [w.capitalize() if not w[0].isdigit() else w for w in name.split("-")]
    return f"Google'ın {' '.join(words)} modeli"


def quota_wait(err):
    """Seconds to skip a model after a 429: Google's retryDelay / "retry in Ns", or an hour for a daily quota."""
    text = str(err)
    if "PerDay" in text:
        return 3600
    m = re.search(r"retryDelay'?:\s*'(\d+(?:\.\d+)?)s|retry in (\d+(?:\.\d+)?)s", text)
    return max(float(m.group(1) or m.group(2)), 5) if m else GEMINI_QUOTA_WAIT


def _version(v):
    return tuple(int(x) for x in v.split("."))


class Brain:
    """Streams a reply from Gemini (if GEMINI_API_KEY is set) or Claude (if ANTHROPIC_API_KEY is).
    The conversation lives only in memory and is gone when the app quits."""

    def __init__(self):
        self.gemini = self.gemini_key = self.gemini_ranked = self.gemini_used = None
        self.gemini_down = {}  # model -> time until which it is skipped (it was overloaded)
        self.claude = None
        self.reset()

    def reset(self):
        """Forget the conversation; each provider keeps its own, in its own message format."""
        self.histories = {"gemini": [], "claude": []}

    def _system(self, model):
        n = datetime.datetime.now()
        return SYSTEM.format(model=model) + (f"\n\nŞu an: {n.day} {MONTHS[n.month - 1]} {n.year} {DAYS[n.weekday()]}, "
                         f"saat {n:%H:%M}.")

    def ask(self, text, on_delta, cancel):
        """Stream the reply into on_delta(text) until done or `cancel` (an Event of this request alone) is set.
        Returns a spoken error message, or None. Gemini first; Claude if every Gemini model is out of quota
        or overloaded and an Anthropic key is set."""
        cfg = keys()
        gemini_key = cfg.get("GEMINI_API_KEY") or cfg.get("GOOGLE_API_KEY")
        claude_key = cfg.get("ANTHROPIC_API_KEY")
        if not gemini_key and not claude_key:
            return NO_KEY
        for name in self.histories:
            if len(self.histories[name]) >= MAX_HISTORY:
                self.histories[name] = []  # a new conversation (history is never edited, only dropped)
        if gemini_key:
            self.unavailable = False
            err = self._gemini(gemini_key, cfg.get("GEMINI_MODEL"), text, on_delta, cancel)
            if err is None or not (self.unavailable and claude_key):
                return err
            print("Raven: Gemini şu an kullanılamıyor, Claude'a geçiliyor", file=sys.stderr)
        return self._claude(claude_key, text, on_delta, cancel)

    # ----- Gemini -----
    def _rank_gemini(self):
        """Gemini models the key can use, in the order to try them: stable Flash newest first (Google's
        fast-and-strong tier, right for speech), then Flash-Lite. Each model has its own quota."""
        stable, preview, lite = [], [], []
        for m in self.gemini.models.list():
            name = m.name.split("/")[-1]
            if m.supported_actions and "generateContent" not in m.supported_actions:
                continue
            if mt := re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash", name):
                stable.append((_version(mt.group(1)), name))
            elif mt := re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash-preview(?:-[0-9-]+)?", name):
                preview.append((_version(mt.group(1)), name))
            elif mt := re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash-lite", name):
                lite.append((_version(mt.group(1)), name))
        ranked = [name for pool in (stable or preview, lite) for _, name in sorted(pool, reverse=True)]
        if not ranked:
            raise LookupError("Bu anahtarla kullanılabilen bir Gemini Flash modeli bulunamadı")
        return ranked

    def _gemini(self, key, model, text, on_delta, cancel):
        from google import genai
        from google.genai import errors, types

        contents = self.histories["gemini"] + [{"role": "user", "parts": [{"text": text}]}]
        spoken = []  # text already handed to the voice; once there is some, the model can't be switched

        def stream(name):
            """Returns True if the prompt was blocked, None if cancelled, False otherwise."""
            thinking = types.ThinkingConfig(thinking_level="LOW")  # speech wants the first words fast
            for attempt in (0, 1):
                config = types.GenerateContentConfig(system_instruction=self._system(gemini_label(name)),
                                                     max_output_tokens=2048,
                                                     thinking_config=thinking)
                try:
                    blocked = False
                    for chunk in self.gemini.models.generate_content_stream(model=name, contents=contents,
                                                                            config=config):
                        if cancel.is_set():
                            return None
                        if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                            blocked = True
                        for cand in chunk.candidates or []:
                            for part in (cand.content.parts if cand.content else None) or []:
                                if part.text and not part.thought:
                                    spoken.append(part.text)
                                    on_delta(part.text)
                    return blocked
                except errors.ClientError as e:  # a model without thinking levels: retry without them
                    if attempt or spoken or e.code != 400 or "think" not in str(e).lower():
                        raise
                    thinking = None

        try:
            if self.gemini is None or key != self.gemini_key:
                opts = types.HttpOptions(timeout=GEMINI_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1))
                self.gemini = genai.Client(api_key=key, http_options=opts)
                self.gemini_key, self.gemini_ranked = key, None
            if self.gemini_ranked is None:
                self.gemini_ranked = self._rank_gemini()
            ranked = ([model] if model else []) + [m for m in self.gemini_ranked if m != model]
            now = time.monotonic()
            chain = [m for m in ranked if self.gemini_down.get(m, 0) <= now] or ranked[:1]
            start, timeouts, last = now, 0, None
            for name in chain:  # the chosen model first; down the list when one is out of quota or overloaded
                if last is not None and (time.monotonic() - start > GEMINI_BUDGET or timeouts >= 2):
                    break
                if name != self.gemini_used:
                    print(f"Raven: Gemini modeli {name}", file=sys.stderr)
                    self.gemini_used = name
                try:
                    blocked = stream(name)
                    last = None
                    break
                except Exception as e:
                    quota = isinstance(e, errors.ClientError) and e.code == 429
                    gone = isinstance(e, errors.ClientError) and e.code == 404  # listed but retired
                    timeout = "timeout" in type(e).__name__.lower()
                    if spoken or not (quota or gone or timeout or isinstance(e, errors.ServerError)):
                        raise
                    wait = quota_wait(e) if quota else 86400 if gone else GEMINI_COOLDOWN
                    self.gemini_down[name] = time.monotonic() + wait
                    timeouts += timeout
                    last = e
                    why = "kotası doldu" if quota else "kullanımdan kalkmış" if gone else "yanıt vermedi"
                    print(f"Raven: {name} {why}; {round(wait)} sn atlanacak", file=sys.stderr)
            if last is not None:
                raise last
            if blocked is None:
                return None
        except errors.ClientError as e:
            print(e, file=sys.stderr)
            if e.code in (401, 403) or (e.code == 400 and "key" in str(e).lower()):
                return "Gemini API anahtarı geçersiz görünüyor."
            if e.code == 429:
                self.unavailable = not spoken
                return "Gemini kotası şu an dolu, biraz sonra tekrar dener misin?"
            if e.code == 404:
                return "Seçilen Gemini modeli bulunamadı."
            return "Bir hata oluştu, tekrar dener misin?"
        except errors.ServerError as e:
            print(e, file=sys.stderr)
            self.unavailable = not spoken
            return "Gemini şu an çok yoğun, birazdan tekrar dener misin?"
        except LookupError as e:
            print(e, file=sys.stderr)
            return "Bu anahtarla kullanabileceğim bir Gemini modeli bulamadım."
        except Exception as e:  # network errors come from the HTTP layer underneath the SDK
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            if "timeout" in type(e).__name__.lower():
                self.unavailable = not spoken
                return "Gemini çok geç yanıt veriyor, birazdan tekrar dener misin?"
            if "connect" in type(e).__name__.lower():
                return "İnternete bağlanamadım."
            return "Bir hata oluştu, tekrar dener misin?"
        reply = "".join(spoken)
        if not reply:
            return "Bu konuda yardımcı olamıyorum." if blocked else "Bir cevap gelmedi, tekrar dener misin?"
        self.histories["gemini"] = contents + [{"role": "model", "parts": [{"text": reply}]}]
        return None

    # ----- Claude -----
    def _claude(self, key, text, on_delta, cancel):
        import anthropic

        messages = self.histories["claude"] + [{"role": "user", "content": text}]
        try:
            if self.claude is None or self.claude.api_key != key:
                self.claude = anthropic.Anthropic(api_key=key)
            with self.claude.messages.stream(model=CLAUDE_MODEL, max_tokens=1024, system=self._system("Anthropic'in Claude Haiku 5.5 modeli"),
                                             output_config={"effort": "low"}, messages=messages) as stream:
                for delta in stream.text_stream:
                    if cancel.is_set():
                        return None
                    on_delta(delta)
                final = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            print(e, file=sys.stderr)
            return "API anahtarı geçersiz görünüyor."
        except anthropic.RateLimitError as e:
            print(e, file=sys.stderr)
            return "Şu an biraz yoğunluk var, birazdan tekrar dener misin?"
        except anthropic.APIConnectionError as e:
            print(e, file=sys.stderr)
            return "İnternete bağlanamadım."
        except anthropic.APIStatusError as e:
            print(e, file=sys.stderr)
            return "Bir hata oluştu, tekrar dener misin?"
        if final.stop_reason == "refusal":
            return "Bu konuda yardımcı olamıyorum."
        # append-only history: keep the full content (thinking blocks included) exactly as returned
        self.histories["claude"] = messages + [{"role": "assistant", "content": final.content}]
        return None


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


def speakable(s):
    """Strip what a reader can't say: markdown marks, list bullets, emoji."""
    s = EMOJI.sub("", s)
    s = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", s, flags=re.M)
    s = re.sub(r"[*_#`>|\[\]]", "", s)
    return re.sub(r"\s+", " ", s).strip()


class Mouth:
    """Speaks a streamed reply: splits it into sentences, makes each with EMA while the previous one plays."""

    def __init__(self, get_tts, get_voice, post):
        self.get_tts, self.get_voice, self.post = get_tts, get_voice, post
        self.sentences, self.audio = queue.Queue(), queue.Queue()
        self.buf, self.gen = "", 0  # gen: bumps on stop(), so stale work is dropped
        self.started = False
        self.level = 0.0
        self.stream, self.rate = None, None
        threading.Thread(target=self._synth, daemon=True).start()
        threading.Thread(target=self._play, daemon=True).start()

    def begin(self):
        self.stop()
        self.started = False

    def feed(self, text):
        self.buf += text
        while True:
            cut = self._boundary()
            if cut is None:
                return
            self._push(self.buf[:cut])
            self.buf = self.buf[cut:]

    def end(self):
        self._push(self.buf)
        self.buf = ""
        self.sentences.put((self.gen, None))

    def say(self, text):
        """Speak a whole text (used for errors and notices)."""
        self.begin()
        self.feed(text)
        self.end()

    def stop(self):
        self.gen += 1
        self.buf = ""

    def _boundary(self):
        for m in re.finditer(r"[.!?…:;]+[\"”’)]*\s|\n", self.buf):
            if m.end() >= 12:  # skip tiny pieces such as "Dr. " or "1. "
                return m.end()
        if len(self.buf) > 220:  # a very long sentence: break at the last comma or space
            i = max(self.buf.rfind(", ", 0, 220), self.buf.rfind(" ", 0, 220))
            return i + 1 if i > 0 else 220
        return None

    def _push(self, s):
        s = speakable(s)
        if s:
            self.sentences.put((self.gen, s))

    def _synth(self):
        while True:
            gen, s = self.sentences.get()
            if gen != self.gen:
                continue
            if s is None:
                self.audio.put((gen, None, None))
                continue
            while self.get_tts() is None:  # EMA still loading
                time.sleep(0.1)
            speed, seed, rate = self.get_voice()
            try:
                audio = self.get_tts().say(s, speed=speed, seed=seed, sample_rate=rate).audio
            except Exception as e:
                print(f"EMA: {e}", file=sys.stderr)
                continue
            self.audio.put((gen, audio, rate))

    def _play(self):
        while True:
            gen, audio, rate = self.audio.get()
            if gen != self.gen:
                continue
            if audio is None:
                self.level = 0.0
                self.post("speak_end", None)
                continue
            if rate != self.rate:
                if self.stream:
                    self.stream.close()
                self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
                self.stream.start()
                self.rate = rate
            if not self.started:
                self.started = True
                self.post("speak_start", None)
            step = rate // 20  # 50 ms: short enough to stop quickly and drive the level meter
            for i in range(0, len(audio), step):
                if gen != self.gen:
                    break
                chunk = audio[i:i + step].astype(np.float32)
                self.level = min(float(np.sqrt(np.mean(chunk ** 2))) * 6, 1.0)
                self.stream.write(chunk)
            self.level = 0.0
