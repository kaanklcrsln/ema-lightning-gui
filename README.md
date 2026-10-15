# EMA Lightning GUI

<img width="1920" height="1080" alt="kirbybanner_00000" src="https://github.com/user-attachments/assets/751137ad-a7df-48db-932b-d6acefc9ec7c" />

Hızlı bir Türkçe metinden konuşmaya (TTS) modeli olan [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) için iki masaüstü arayüzü. İkisi de Tkinter ile yazıldı. Model bir kez indirildikten sonra seslendirme tamamen çevrimdışı çalışır.

| Klasör | Ne işe yarar |
|---|---|
| [`ema-gui/`](ema-gui) | Koyu, cam görünümlü küçük bir pencere. Arkasında yavaşça kayan bir ışıltı var |
| [`ema-island/`](ema-island) | Yalnızca macOS. EMA, MacBook'un çentiğine yerleşir. Üzerine gelince açılan siyah bir hap |

## Kurulum

Tk destekli Python 3.10 veya üstü gerekir.

```bash
git clone https://github.com/kaanklcrsln/raven.git
cd raven
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

İlk açılışta model Hugging Face'ten iner, boyutu yaklaşık 34 MB. Modeli yerelde tutmak isterseniz `ema.pt` ve `decoder.pt` dosyalarını repo kök dizinine ya da bir `app.py` dosyasının yanına koyun. İki uygulama da modeli oradan yükler:

```bash
hf download canberkkkkkk/ema-lightning ema.pt decoder.pt --local-dir .
```

NVIDIA GPU'su olmayan Mac'lerde ve diğer bilgisayarlarda model CPU'da çalışır. İlk seslendirme yavaştır çünkü model ısınır. Sonrakiler gerçek zamandan kat kat hızlıdır.

## EMA GUI

```bash
.venv/bin/python ema-gui/app.py
```

- Türkçe metni yazıp **▶ Seslendir** düğmesine ya da ⌘+Enter'a basın. Ses üretilir ve hemen çalar
- Dalga formu oynatıcısında herhangi bir yere tıklayınca o noktaya atlar. Boşluk tuşu oynatır ya da duraklatır, Esc durdurur
- Açılıp kapanan ses ayarları:
  - **Hız**, 0.25× ile 4× arası. Çift tıklayınca sıfırlanır
  - **Örnekleme hızı**, 8 ile 48 kHz arası
  - **Seed**, rastgele olabilir, zarla yeniden atılabilir ya da sabitlenebilir
- Üst çubuktan seçilen dört renk teması
- Sonucu `.wav` olarak kaydetme

## EMA Island

```bash
.venv/bin/python ema-island/app.py
```

- Menü çubuğunun üstünde durur ve çentiği sarar. Üzerine gelince açılır, fare uzaklaşınca kapanır
- Kapalıyken ses çalarken küçük çubuklar, ses üretilirken dönen bir gösterge ve çalma süresini gösterir
- Açıkken çentik satırında mikrofon anahtarı, sorma ve okuma modu, ayarlar, GitHub ve çıkış düğmeleri bulunur. ⌘Q da uygulamayı kapatır. Adanın tek ve sabit bir lavanta vurgu rengi var
- Metin kutusu, oynatıcı ve ses ayarları EMA GUI'dekiyle aynı, yalnızca çentiğin altına sığacak boyutta
- Dock simgesi yok. Çentiği olmayan Mac'lerde ekranın üst ortasında yüzen bir hap olarak görünür

### Raven, sesli asistan

**"Raven"** deyin, *rey-vın* diye okunur. Ada açılır ve dinlemeye başlar. Sorunuzu sorun. 3 saniye sessizlikten sonra soru Gemini'ye gider ve anahtarınızın erişebildiği en yeni Flash modeli cevaplar. Cevap parça parça gelir, EMA da onu cümle cümle seslendirir. Tek nefeste de söyleyebilirsiniz: "Raven, yarın hava nasıl?"

- Uyandırma kelimesi ve konuşmanın yazıya dökülmesi Apple Silicon üzerinde yerel olarak Whisper ile çalışır (`mlx-whisper`). Uyandırma kelimesini `whisper-base`, isteğin kendisini `whisper-small` çözer. Konuşmanın başladığını ve bittiğini Silero VAD algılar. Bilgisayardan yalnızca yazıya dökülmüş metin çıkar
- Konuşma yalnızca bellekte tutulur ve uygulama kapanınca silinir
- Yazılan istekler de Raven'a gider. ✦ / 🔈 simgesi metin kutusunu Raven'a sorma ile metni sesli okuma arasında değiştirir
- Mikrofon simgesi uyandırma kelimesini dinlemeyi açar ve kapatır. Esc, Raven'ı cümlenin ortasında susturur
- Uygulamayı başlattığınız program için mikrofon izni gerekir. Bu program Terminal, VS Code ya da başka bir uygulama olabilir
- [Google AI Studio](https://aistudio.google.com/apikey)'dan alınmış bir Gemini API anahtarı gerekir. Anahtarı repo kök dizinindeki `.env` dosyasına yazın. Git bu dosyayı yok sayar, dosya hiçbir zaman commit'lenmez:

  ```
  GEMINI_API_KEY=anahtariniz
  GEMINI_MODEL=
  ```

  `GEMINI_MODEL` boş kalırsa en yeni Flash modeli kullanılır. Bir modelin kotası dolar ya da model aşırı yüklenirse sıradaki model devreye girer. `ANTHROPIC_API_KEY` eklerseniz Claude Haiku 5.5 yedek olarak çalışır

## Atıflar

Bu proje aşağıdaki çalışmaların üzerine kurulu. Hepsinin geliştiricilerine teşekkürler.

| Bileşen | Geliştiren | Lisans | Projedeki görevi |
|---|---|---|---|
| [EMA Lightning](https://huggingface.co/canberkkkkkk/ema-lightning) | Canberk Aslan | Apache-2.0 | Türkçe metinden konuşma modeli ve `ema-lightning` paketi |
| [normalizer-tr](https://github.com/erdemtuna/normalizer-tr) | Erdem Tuna | Apache-2.0 | Sayıları, tarihleri ve sembolleri okunuşa çeviren Türkçe metin normalleştirici. EMA Lightning içinden çalışır |
| [Whisper](https://github.com/openai/whisper) | OpenAI | MIT | Konuşma tanıma modeli |
| [MLX](https://github.com/ml-explore/mlx) ve [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) | Apple ve MLX katkıcıları | MIT | Whisper'ı Apple Silicon üzerinde çalıştırır |
| [whisper-base-mlx](https://huggingface.co/mlx-community/whisper-base-mlx) ve [whisper-small-mlx](https://huggingface.co/mlx-community/whisper-small-mlx) | mlx-community | MIT (OpenAI Whisper) | Whisper ağırlıklarının MLX biçimine dönüştürülmüş halleri |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Silero Team | MIT | Konuşmanın başını ve sonunu algılar |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | Matthias Geier | MIT | Mikrofondan kayıt alır ve ses çalar |
| [PortAudio](https://www.portaudio.com) | PortAudio katkıcıları | MIT tarzı | sounddevice'ın kullandığı ses kütüphanesi |
| [PyTorch](https://pytorch.org) | PyTorch ekibi | BSD-3-Clause | EMA Lightning ve Silero VAD bunun üzerinde çalışır |
| [NumPy](https://numpy.org) | NumPy geliştiricileri | BSD-3-Clause | Ses verisini işler |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Hugging Face | Apache-2.0 | Modelleri indirir |
| [Google Gen AI SDK](https://github.com/googleapis/python-genai) | Google | Apache-2.0 | Gemini API'ye bağlanır |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | Anthropic | MIT | Yedek olarak Claude API'ye bağlanır |
| [Avatar Lab](https://github.com/smontlouis/bible-strong-avatar-lab) | Stéphane Montlouis | AGPL-3.0 | Raven'ın maskotu bu araçla tasarlandı. Dışa aktarılan dosyalar [`kirby-avatar/`](kirby-avatar) klasöründe. `ema-island/mascot.py` bu dosyalardaki motoru izleyerek maskotu Tk'de çizer |
| [Primer Octicons](https://github.com/primer/octicons) | GitHub | MIT | GitHub simgesi |
| [Python](https://www.python.org) ve [Tcl/Tk](https://www.tcl-lang.org) | Python Software Foundation ve Tcl/Tk katkıcıları | PSF ve Tcl/Tk lisansı | Programlama dili ve Tkinter arayüz kütüphanesi |

**Hizmetler.** Raven'ın cevapları [Google Gemini API](https://ai.google.dev) üzerinden, yedek olarak da [Anthropic Claude API](https://www.anthropic.com/api) üzerinden gelir. Yazıya dökülen metin bu sağlayıcılara gönderilir. İki hizmet de kendi kullanım koşullarına tabidir.

**Yazı tipleri.** Arayüz, sistemde kuruluysa Apple'ın SF Pro ve SF Mono yazı tiplerini kullanır. Bu yazı tipleri repoda yer almaz.

**Kirby.** Maskot dosyalarındaki "Kirby" adı Nintendo ve HAL Laboratory'nin ticari markasıdır. Bu projenin Nintendo ya da HAL Laboratory ile bir bağı yoktur ve proje onlar tarafından desteklenmez.

## Lisans

Copyright (C) 2026 kaanklcrsln

Bu proje [GNU Affero Genel Kamu Lisansı, sürüm 3](LICENSE) (AGPL-3.0) ile lisanslıdır. Avatar Lab AGPL-3.0 ile lisanslı. `kirby-avatar/` ve `ema-island/mascot.py` onun motorundan türediği için repo da aynı lisansı kullanır. Kodu değiştirip dağıtırsanız ya da ağ üzerinden kullanıcılara sunarsanız kaynak kodunu da AGPL-3.0 ile paylaşmanız gerekir.

EMA Lightning model dosyaları (`ema.pt`, `decoder.pt`) bu repoda yer almaz. İlk çalıştırmada Hugging Face'ten inerler ve kendi lisansları olan Apache-2.0'a tabidirler. Diğer bağımlılıklar da yukarıdaki tabloda yazan kendi lisanslarıyla gelir.
