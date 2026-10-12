# EMA Lightning Studio

A dark, glass-style desktop GUI for [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning), a fast Turkish text-to-speech model. Built with Tkinter. It runs fully offline once the model is downloaded.

## Features

- Type Turkish text and press **▶ Seslendir** (or ⌘+Enter) to generate speech and hear it right away
- Waveform player: click anywhere on it to jump, Space plays/pauses, Esc stops
- **Speed** from 0.25× to 4× (double-click the slider to reset to 1.0×)
- **Sample rate**: 48 / 24 / 16 / 8 kHz
- **Seed**: leave empty for a random seed, roll a new one with 🎲, or lock it with 🔒 to get the same audio every time
- Save the result as `.wav`
- A **?** button with a usage guide, plus a tooltip on each setting

## Setup

Requires Python 3.10+ with Tk.

```bash
git clone https://github.com/kaanklcrsln/ema-lightning-gui.git
cd ema-lightning-gui
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

On first launch the model (~34 MB) downloads from Hugging Face. If `ema.pt` and `decoder.pt` are next to `app.py`, those files are used instead:

```bash
hf download canberkkkkkk/ema-lightning ema.pt decoder.pt --local-dir .
```

On Macs and other machines without an NVIDIA GPU, the model runs on the CPU. The first generation is slow while the model warms up; later ones run many times faster than real time.

## Credits

The model is [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) by Canberk Aslan (Apache 2.0). Turkish text normalization comes from [normalizer-tr](https://github.com/erdemtuna/normalizer-tr).
