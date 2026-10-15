"""Raven API: the speech side of Raven Web, as a Hugging Face ZeroGPU Space.

    /transcribe  base64 16 kHz mono WAV -> text (Whisper)
    /speak       text + voice settings -> {audio: base64 WAV, duration} (EMA Lightning)

The site talks to Gemini itself with each visitor's own key; nothing here sees that key or the conversation.
Run locally with `python app.py` (CPU, whisper-small); the site then connects to http://127.0.0.1:7860.
"""
import base64
import io
import os
import re
import wave

import gradio as gr
import numpy as np
import spaces
import torch
from ema_lightning import EMA
from transformers import pipeline

SOURCE = "https://github.com/kaanklcrsln/raven"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
STT_MODEL = os.environ.get("RAVEN_STT_MODEL") or ("openai/whisper-large-v3" if DEVICE == "cuda" else "openai/whisper-small")
STT_RATE = 16000
MAX_AUDIO_S = 60
MAX_TEXT = 2000
RATES = (8000, 16000, 24000, 48000)  # same choices as EMA Island
SPEED_MIN, SPEED_MAX = 0.25, 4.0
SEED_MAX = 2 ** 31 - 1
GAP = 0.15  # seconds of silence between sentences
MAX_SENTENCE = 220
HALLUCINATIONS = ("altyazı", "abone ol", "izlediğiniz için")  # Whisper's usual inventions on near-silence
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")

# Models go on the GPU at import time: on ZeroGPU that is the efficient place, a real GPU only exists inside @spaces.GPU.
tts = EMA(DEVICE)
stt = pipeline("automatic-speech-recognition", model=STT_MODEL, device=DEVICE,
               dtype=torch.float16 if DEVICE == "cuda" else torch.float32)


def speakable(s):
    """Strip what a reader can't say: markdown marks, list bullets, emoji."""
    s = EMOJI.sub("", s)
    s = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", s, flags=re.M)
    s = re.sub(r"[*_#`>|\[\]]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def sentences(text):
    """Split at sentence ends; keep tiny pieces ("Dr.", "1.") with the next one, break very long ones at a comma."""
    out, buf = [], ""
    for piece in re.split(r"(?<=[.!?…:;])\s+|\n+", text):
        buf = f"{buf} {piece}".strip()
        if len(buf) >= 12:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    short = []
    for s in out:
        while len(s) > MAX_SENTENCE:
            i = max(s.rfind(", ", 0, MAX_SENTENCE), s.rfind(" ", 0, MAX_SENTENCE))
            i = i + 1 if i > 0 else MAX_SENTENCE
            short.append(s[:i].strip())
            s = s[i:].strip()
        if s:
            short.append(s)
    return short


def wav_bytes(audio, rate):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def read_wav(data):
    with wave.open(io.BytesIO(data)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, STT_RATE):
            raise ValueError("ses 16 kHz, mono, 16 bit WAV olmalı")
        if w.getnframes() > MAX_AUDIO_S * STT_RATE:
            raise ValueError(f"kayıt {MAX_AUDIO_S} saniyeden uzun olamaz")
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


@spaces.GPU(duration=20)
def transcribe(audio_b64: str) -> str:
    """Turkish speech in a base64 16 kHz mono 16-bit WAV, as text ("" if nothing was said)."""
    try:
        samples = read_wav(base64.b64decode(audio_b64, validate=True))
    except (ValueError, wave.Error) as e:
        raise gr.Error(f"Ses kaydı okunamadı: {e}.")
    long_form = {"return_timestamps": True} if len(samples) > 30 * STT_RATE else {}
    out = stt({"raw": samples, "sampling_rate": STT_RATE},
              generate_kwargs={"language": "turkish", "task": "transcribe"}, **long_form)
    text = out["text"].strip()
    return "" if any(h in text.lower() for h in HALLUCINATIONS) else text


@spaces.GPU(duration=30)
def speak(text: str, speed: float, seed: int, sample_rate: int) -> dict:
    """Raven's reply read aloud by EMA Lightning: {"audio": base64 WAV, "duration": seconds}."""
    text = speakable(text)
    if not text:
        raise gr.Error("Okunacak metin boş.")
    if len(text) > MAX_TEXT:
        raise gr.Error(f"Metin {MAX_TEXT} karakterden uzun olamaz.")
    if not SPEED_MIN <= speed <= SPEED_MAX:
        raise gr.Error(f"Hız {SPEED_MIN} ile {SPEED_MAX} arasında olmalı.")
    if not 0 <= seed <= SEED_MAX:
        raise gr.Error(f"Seed 0 ile {SEED_MAX} arasında olmalı.")
    if sample_rate not in RATES:
        raise gr.Error(f"Örnekleme hızı şunlardan biri olmalı: {', '.join(map(str, RATES))}.")
    gap = np.zeros(int(sample_rate * GAP), np.float32)
    parts = []
    for s in sentences(text):
        parts += [np.asarray(tts.say(s, speed=speed, seed=seed, sample_rate=sample_rate).audio, np.float32), gap]
    audio = np.concatenate(parts[:-1])
    return {"audio": base64.b64encode(wav_bytes(audio, sample_rate)).decode("ascii"),
            "duration": len(audio) / sample_rate}


with gr.Blocks(title="Raven API") as demo:
    gr.Markdown(f"""# Raven API
[Raven Web]({SOURCE})'in ses sunucusu. Konuşmayı [Whisper](https://github.com/openai/whisper) ile yazıya döker, \
cevabı Canberk Aslan'ın Türkçe ses modeli [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) ile \
seslendirir. Bu sayfa yalnızca API sunar; kaynak kodu [GitHub'da]({SOURCE}) (AGPL-3.0).""")
    gr.api(transcribe, api_name="transcribe")
    gr.api(speak, api_name="speak")

if __name__ == "__main__":
    demo.launch()
