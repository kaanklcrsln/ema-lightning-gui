# EMA Lightning GUI

Two desktop front-ends for [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning), a fast Turkish text-to-speech model. Both are built with Tkinter and run fully offline once the model is downloaded.

| Folder | What it is |
|---|---|
| [`ema-gui/`](ema-gui) | A compact window with a dark glass design and a softly drifting glow behind it |
| [`ema-island/`](ema-island) | macOS only. EMA lives in the MacBook notch: a black pill that springs open when you hover over it |

## Setup

Requires Python 3.10+ with Tk.

```bash
git clone https://github.com/kaanklcrsln/ema-lightning-gui.git
cd ema-lightning-gui
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
- Open, the notch row holds the theme dots, plus buttons for settings, GitHub and quit (or ⌘Q)
- The same text box, player and voice settings as EMA GUI, sized to fit under the notch
- No Dock icon; on Macs without a notch it floats as a pill at the top center of the screen

## Credits

The model is [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) by Canberk Aslan (Apache 2.0). Turkish text normalization comes from [normalizer-tr](https://github.com/erdemtuna/normalizer-tr). The GitHub mark comes from [Primer Octicons](https://github.com/primer/octicons) (MIT).
