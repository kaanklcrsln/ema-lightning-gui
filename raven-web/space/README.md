---
title: Raven API
emoji: 🐦
colorFrom: purple
colorTo: indigo
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
license: agpl-3.0
short_description: Raven Web için Türkçe ses tanıma ve seslendirme
models:
  - canberkkkkkk/ema-lightning
  - openai/whisper-large-v3
---

# Raven API

[Raven Web](https://github.com/kaanklcrsln/raven) sitesinin ses sunucusu. İki uç sunar:

- `/transcribe` 16 kHz mono WAV kaydını [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3) ile Türkçe metne çevirir
- `/speak` metni Canberk Aslan'ın [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) modeliyle seslendirir

Gemini'ye site doğrudan, ziyaretçinin kendi anahtarıyla bağlanır. Anahtar ve konuşma bu sunucuya gelmez.

Kaynak kodu: [github.com/kaanklcrsln/raven](https://github.com/kaanklcrsln/raven), AGPL-3.0.
