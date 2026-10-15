"""Raven API: Raven Web's voice, as a Hugging Face ZeroGPU Space.

    /speak  text + voice settings -> {audio: base64 WAV, duration} (EMA Lightning)

The site talks to Gemini itself with each visitor's own key; nothing here sees that key or the conversation.
Run locally with `python app.py` (CPU); the site then connects to http://127.0.0.1:7860.
"""
import base64
import io
import re
import wave

import gradio as gr
import numpy as np
import spaces
import torch
from ema_lightning import EMA

SOURCE = "https://github.com/kaanklcrsln/raven"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_TEXT = 2000
RATES = (8000, 16000, 24000, 48000)  # same choices as EMA Island
SPEED_MIN, SPEED_MAX = 0.25, 4.0
SEED_MAX = 2 ** 31 - 1
GAP = 0.15  # seconds of silence between sentences
MAX_SENTENCE = 220
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")

# The model goes on the GPU at import time: on ZeroGPU that is the efficient place, a real GPU only exists inside @spaces.GPU.
tts = EMA(DEVICE)
# Left unset, EMA times batches of up to 128 on its first request to pick a batch size. On ZeroGPU's shared GPU the
# big batches run out of memory, which surfaces as an NVML assert instead of the OutOfMemoryError EMA catches.
# Requests here are one reply at a time, so a small fixed batch is enough.
tts._batch_size = 4


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
    # ZeroGPU restores the weights in its GPU worker as trainable tensors, so EMA's playback thread would build a
    # gradient graph and .numpy() on the audio fails. Speech never needs gradients.
    tts._engine.model.requires_grad_(False)
    tts._engine.decoder.requires_grad_(False)
    gap = np.zeros(int(sample_rate * GAP), np.float32)
    parts = []
    for s in sentences(text):
        parts += [np.asarray(tts.say(s, speed=speed, seed=seed, sample_rate=sample_rate).audio, np.float32), gap]
    audio = np.concatenate(parts[:-1])
    return {"audio": base64.b64encode(wav_bytes(audio, sample_rate)).decode("ascii"),
            "duration": len(audio) / sample_rate}


with gr.Blocks(title="Raven API") as demo:
    gr.Markdown(f"""# Raven API
[Raven Web]({SOURCE})'in ses sunucusu. Cevapları Canberk Aslan'ın Türkçe ses modeli \
[EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) ile seslendirir. Bu sayfa yalnızca API sunar; \
kaynak kodu [GitHub'da]({SOURCE}) (AGPL-3.0).""")
    gr.api(speak, api_name="speak")

if __name__ == "__main__":
    # No server-side rendering: the site calls the API from another origin, the Node SSR proxy adds nothing here.
    demo.launch(ssr_mode=False)
