# EMA Lightning GUI

<img width="1920" height="1080" alt="kirbybanner_00000" src="https://github.com/user-attachments/assets/751137ad-a7df-48db-932b-d6acefc9ec7c" />

Two desktop front-ends for [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning), a fast Turkish text-to-speech model. Both are built with Tkinter and run fully offline once the model is downloaded.

| Folder | What it is |
|---|---|
| [`ema-gui/`](ema-gui) | A compact window with a dark glass design and a softly drifting glow behind it |
| [`ema-island/`](ema-island) | macOS only. EMA lives in the MacBook notch: a black pill that springs open when you hover over it |

## Setup

Requires Python 3.10+ with Tk.

```bash
git clone https://github.com/kaanklcrsln/raven.git
cd raven
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

On first launch the model (~34 MB) downloads from Hugging Face. To keep it local, put `ema.pt` and `decoder.pt` in the repo root (or next to an `app.py`), and both apps will load them from there:

```bash
hf download canberkkkkkk/ema-lightning ema.pt decoder.pt --local-dir .
```

On Macs and other machines without an NVIDIA GPU, the model runs on the CPU. The first generation is slow while the model warms up; later ones run many times faster than real time.

## EMA GUI

```bash
.venv/bin/python ema-gui/app.py
```

- Type Turkish text and press **▶ Seslendir** (or ⌘+Enter) to generate speech and play it right away
- Waveform player: click anywhere on it to jump; Space plays/pauses; Esc stops
- Collapsible voice settings: **speed** (0.25×–4×; double-click to reset), **sample rate** (8–48 kHz), **seed** (random, rolled with the dice, or locked)
- Four color themes, picked from the navbar
- Save the result as `.wav`

## EMA Island

```bash
.venv/bin/python ema-island/app.py
```

- Sits on top of the menu bar and hugs the notch. Hover over it to open, move away to close
- Collapsed, it shows small bars while audio plays, a spinner while generating, and the playback time
- Open, the notch row holds the microphone toggle and buttons for ask/read mode, settings, GitHub and quit (or ⌘Q). The island has one fixed lavender accent
- The same text box, player and voice settings as EMA GUI, sized to fit under the notch
- No Dock icon; on Macs without a notch it floats as a pill at the top center of the screen

### Raven, the voice assistant

Say **"Raven"** (pronounced *rey-vın*). The island opens and listens; ask your question, and after 3 seconds of silence it is sent to Gemini (the newest Flash model your key can use). The reply streams back and EMA speaks it sentence by sentence. You can also say it in one breath: "Raven, yarın hava nasıl?"

- Wake word and speech-to-text run locally with Whisper on Apple Silicon (`mlx-whisper`); only the transcribed text leaves the computer
- The conversation is kept in memory only and is gone when the app quits
- Typed prompts go to Raven too; the ✦ / 🔈 icon switches the text box between asking Raven and reading the text aloud
- The microphone icon turns wake-word listening on and off; Esc stops Raven mid-sentence
- Needs microphone permission for the app you launch it from (Terminal, VS Code, …)
- Needs a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), in a `.env` file in the repo root (git-ignored, never committed):

  ```
  GEMINI_API_KEY=your-key
  GEMINI_MODEL=
  ```

  Leave `GEMINI_MODEL` empty to use the newest Flash model; when one runs out of quota or is overloaded, the next one takes over. `ANTHROPIC_API_KEY` adds Claude Haiku 5.5 as a fallback

## Credits

The model is [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) by Canberk Aslan (Apache 2.0). Turkish text normalization comes from [normalizer-tr](https://github.com/erdemtuna/normalizer-tr). Raven's mascot was designed with [Avatar Lab](https://github.com/smontlouis/bible-strong-avatar-lab) by Stéphane Montlouis (AGPL-3.0); its export lives in [`kirby-avatar/`](kirby-avatar), and `ema-island/mascot.py` renders it in Tk following that export's engine. The GitHub mark comes from [Primer Octicons](https://github.com/primer/octicons) (MIT).
