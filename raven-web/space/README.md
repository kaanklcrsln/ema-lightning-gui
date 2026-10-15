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
short_description: Raven Web için Türkçe seslendirme (EMA Lightning)
models:
  - canberkkkkkk/ema-lightning
---

# Raven API

[Raven Web](https://github.com/kaanklcrsln/raven) sitesinin ses sunucusu. Tek bir uç sunar: `/speak`, metni Canberk Aslan'ın [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) modeliyle seslendirir.

Gemini'ye site doğrudan, ziyaretçinin kendi anahtarıyla bağlanır. Anahtar ve konuşma geçmişi bu sunucuya gelmez, buraya yalnızca seslendirilecek cevap metni gelir.

Kaynak kodu: [github.com/kaanklcrsln/raven](https://github.com/kaanklcrsln/raven), AGPL-3.0.
