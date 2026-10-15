import { useState } from 'react'
import { Kirby } from '../../../kirby-avatar/Kirby'
import { checkKey } from '../lib/gemini'
import { Icon } from './Icon'

/** First screen: Raven needs the visitor's own Gemini API key before anything else. */
export function KeyGate({ onKey }: { onKey: (key: string) => void }) {
  const [value, setValue] = useState('')
  const [show, setShow] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    const key = value.trim()
    if (!key || checking) return
    setChecking(true)
    setError(null)
    try {
      await checkKey(key)
      onKey(key)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setChecking(false)
    }
  }

  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-avatar">
          <Kirby animation={error ? 'confused' : checking ? 'thinking' : 'happy'} size="100%" />
        </div>
        <h1 className="gate-title">Merhaba!</h1>
        <p className="gate-lead">
          Raven'ın seninle konuşabilmesi için bir Google Gemini API anahtarı gerekiyor. Anahtar ücretsiz, almak birkaç
          dakika sürer.
        </p>
        <ol className="gate-steps">
          <li>
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Google AI Studio</a>'yu aç ve
            Google hesabınla giriş yap.
          </li>
          <li>
            <strong>Create API key</strong> (API anahtarı oluştur) düğmesine bas. Bir proje seçmen istenirse var olanı seç
            ya da yeni bir proje oluştur.
          </li>
          <li>Oluşan anahtarı kopyala ve aşağıya yapıştır.</li>
        </ol>
        <form className="gate-form" onSubmit={e => {
          e.preventDefault()
          void submit()
        }}>
          <label htmlFor="gate-key">Gemini API anahtarı</label>
          <div className="gate-input">
            <input id="gate-key" type={show ? 'text' : 'password'} value={value} placeholder="AIza…" autoComplete="off"
              spellCheck={false} autoFocus onChange={e => setValue(e.target.value)} />
            <button type="button" className="icon-btn" onClick={() => setShow(s => !s)}
              aria-label={show ? 'Anahtarı gizle' : 'Anahtarı göster'}>
              <Icon name={show ? 'eyeOff' : 'eye'} size={20} />
            </button>
          </div>
          <button type="submit" className="gate-submit" disabled={checking || !value.trim()}>
            {checking ? 'Kontrol ediliyor…' : 'Başla'}
          </button>
          {error && <p className="gate-error" role="alert">{error}</p>}
        </form>
        <ul className="gate-notes">
          <li>Anahtar yalnızca bu tarayıcıda saklanır ve doğrudan Google'a gönderilir. Raven'ın sunucusuna gitmez.</li>
          <li>Ücretsiz katmanda Google, gönderilen içeriği ürünlerini geliştirmek için kullanabilir. Kişisel bilgilerini paylaşma.</li>
          <li>Anahtarı istediğin zaman Kullanım sekmesinden değiştirebilir ya da silebilirsin.</li>
        </ul>
      </div>
    </div>
  )
}
