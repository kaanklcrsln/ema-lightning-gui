// Gemini, called straight from the browser with the visitor's own key: the key and the conversation never touch
// Raven's servers. Model choice and fallback follow EMA Island's Brain (ema-island/raven.py).

const BASE = 'https://generativelanguage.googleapis.com/v1beta'
const TIMEOUT_MS = 20000 // longest wait for one model before trying the next
const BUDGET_MS = 25000 // time spent going down the model list before giving up
const COOLDOWN_S = 300 // an overloaded model is skipped this long
const QUOTA_WAIT_S = 60 // a model out of quota is skipped this long, unless Google says how long
const MAX_OUTPUT_TOKENS = 2048
export const MAX_HISTORY = 40 // messages; past this a new conversation starts

export type Turn = { role: 'user' | 'model'; parts: [{ text: string }] }
export type TokenUsage = { input: number; output: number; thinking: number }
export type Answer = { text: string; model: string; usage: TokenUsage }

type Failure = { kind: 'http'; status: number; detail: string } | { kind: 'timeout' } | { kind: 'network' } | { kind: 'no-model' }

class GeminiFailure extends Error {
  constructor(readonly failure: Failure) {
    super(failure.kind === 'http' ? `Gemini ${failure.status}: ${failure.detail}` : `Gemini ${failure.kind}`)
  }
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

async function call(key: string, path: string, body?: unknown): Promise<Record<string, unknown>> {
  const abort = new AbortController()
  const timer = window.setTimeout(() => abort.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(`${BASE}/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: abort.signal,
    })
    const text = await res.text()
    if (!res.ok) throw new GeminiFailure({ kind: 'http', status: res.status, detail: text })
    const data: unknown = JSON.parse(text)
    if (!isRecord(data)) throw new GeminiFailure({ kind: 'http', status: res.status, detail: 'beklenmedik cevap' })
    return data
  } catch (e) {
    if (e instanceof GeminiFailure) throw e
    if (e instanceof DOMException && e.name === 'AbortError') throw new GeminiFailure({ kind: 'timeout' })
    if (e instanceof TypeError) throw new GeminiFailure({ kind: 'network' })
    throw e
  } finally {
    window.clearTimeout(timer)
  }
}

/** Turkish message for any failure, the same wording EMA Island speaks. */
function describe(e: unknown): string {
  if (!(e instanceof GeminiFailure)) return e instanceof Error ? e.message : 'Bir hata oluştu, tekrar dener misin?'
  const f = e.failure
  switch (f.kind) {
    case 'timeout':
      return 'Gemini çok geç yanıt veriyor, birazdan tekrar dener misin?'
    case 'network':
      return 'İnternete bağlanamadım.'
    case 'no-model':
      return 'Bu anahtarla kullanabileceğim bir Gemini modeli bulamadım.'
    case 'http':
      if (f.status === 401 || f.status === 403 || (f.status === 400 && /key/i.test(f.detail))) {
        return 'Gemini API anahtarı geçersiz görünüyor.'
      }
      if (f.status === 429) return 'Gemini kotası şu an dolu, biraz sonra tekrar dener misin?'
      if (f.status === 404) return 'Seçilen Gemini modeli bulunamadı.'
      if (f.status >= 500) return 'Gemini şu an çok yoğun, birazdan tekrar dener misin?'
      return 'Bir hata oluştu, tekrar dener misin?'
    default: {
      const _exhaustive: never = f
      return _exhaustive
    }
  }
}

// ----- choosing a model -----

const version = (v: string) => v.split('.').map(Number)
const newerFirst = (a: [number[], string], b: [number[], string]) => {
  for (let i = 0; i < Math.max(a[0].length, b[0].length); i++) {
    const d = (b[0][i] ?? 0) - (a[0][i] ?? 0)
    if (d) return d
  }
  return b[1].localeCompare(a[1])
}

/** Stable Flash newest first (fast and strong, right for speech), preview Flash if there is no stable one, then Flash-Lite. */
function rank(names: string[]): string[] {
  const stable: [number[], string][] = []
  const preview: [number[], string][] = []
  const lite: [number[], string][] = []
  for (const name of names) {
    let m: RegExpMatchArray | null
    if ((m = name.match(/^gemini-(\d+(?:\.\d+)*)-flash$/)) && m[1]) stable.push([version(m[1]), name])
    else if ((m = name.match(/^gemini-(\d+(?:\.\d+)*)-flash-preview(?:-[0-9-]+)?$/)) && m[1]) preview.push([version(m[1]), name])
    else if ((m = name.match(/^gemini-(\d+(?:\.\d+)*)-flash-lite$/)) && m[1]) lite.push([version(m[1]), name])
  }
  return [...(stable.length ? stable : preview).sort(newerFirst), ...lite.sort(newerFirst)].map(([, n]) => n)
}

async function listModels(key: string): Promise<string[]> {
  const names: string[] = []
  let page = ''
  do {
    const data = await call(key, `models?pageSize=1000${page ? `&pageToken=${encodeURIComponent(page)}` : ''}`)
    for (const m of Array.isArray(data.models) ? data.models : []) {
      if (!isRecord(m) || typeof m.name !== 'string') continue
      const actions = m.supportedGenerationMethods
      if (Array.isArray(actions) && !actions.includes('generateContent')) continue
      names.push(m.name.replace(/^models\//, ''))
    }
    page = typeof data.nextPageToken === 'string' ? data.nextPageToken : ''
  } while (page)
  return names
}

const rankings = new Map<string, Promise<string[]>>()
const down = new Map<string, number>() // model -> time (ms) until which it is skipped

function ranking(key: string): Promise<string[]> {
  let r = rankings.get(key)
  if (!r) {
    r = listModels(key).then(rank).then(ranked => {
      if (!ranked.length) throw new GeminiFailure({ kind: 'no-model' })
      return ranked
    })
    r.catch(() => rankings.delete(key)) // a failed lookup is retried next time
    rankings.set(key, r)
  }
  return r
}

/** Checks a key by listing the models it can use. Resolves to the model Raven would pick; rejects with a Turkish message. */
export async function checkKey(key: string): Promise<string> {
  try {
    const [first] = await ranking(key)
    if (!first) throw new GeminiFailure({ kind: 'no-model' })
    return first
  } catch (e) {
    throw new Error(describe(e))
  }
}

/** Seconds to skip a model after a 429: Google's retryDelay / "retry in Ns", or an hour for a daily quota. */
function quotaWait(detail: string): number {
  if (detail.includes('PerDay')) return 3600
  const m = detail.match(/"retryDelay":\s*"(\d+(?:\.\d+)?)s"|retry in (\d+(?:\.\d+)?)s/)
  const s = Number(m?.[1] ?? m?.[2])
  return Number.isFinite(s) && m ? Math.max(s, 5) : QUOTA_WAIT_S
}

// ----- the conversation -----

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
const DAYS = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi']

const SYSTEM = `Sen Raven'sın: bir web sitesinde yaşayan, Türkçe konuşan sesli bir asistan. Yanıtların EMA adlı bir ses modeliyle yüksek sesle okunuyor; kullanıcı seni dinliyor, okumuyor.

- Konuşur gibi, doğal ve kısa yanıt ver: çoğu zaman bir iki cümle. Kullanıcı ayrıntı isterse uzat.
- Markdown, madde işareti, başlık, tablo, kod bloğu, emoji ve bağlantı kullanma; bunlar sesli okunamıyor. Birkaç adım anlatman gerekirse "önce, sonra, son olarak" gibi cümlelerle anlat.
- Sayıları, tarihleri ve birimleri normal yaz ("15 dakika", "3,5 kilo"); ses modeli onları doğru okuyor.
- Kullanıcının söyledikleri bazen konuşmadan yazıya çevriliyor; küçük yazım hataları olabilir. Anlamı tahmin et, gerçekten anlaşılmıyorsa kısaca tekrar sor.
- İnternete, takvime ya da kullanıcının bilgisayarındaki uygulamalara erişimin yok. Anlık hava durumu, haberler, borsa gibi bilgileri uydurma; bilemeyeceğini kısaca söyle.
- Kullanıcıya "sen" diye hitap et.

Altyapın sorulursa doğrusunu söyle: cevaplarını {model} üretiyor; sesin, Canberk Aslan'ın Türkçe ses modeli EMA Lightning; kullanıcının konuşması Whisper ile yazıya çevriliyor. Başka bir şirketin ya da modelin adını uydurma.`

/** gemini-3.6-flash -> "Google'ın Gemini 3.6 Flash modeli" */
const label = (name: string) =>
  `Google'ın ${name.split('-').map(w => (/^\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1))).join(' ')} modeli`

function systemPrompt(model: string): string {
  const n = new Date()
  const time = `${String(n.getHours()).padStart(2, '0')}:${String(n.getMinutes()).padStart(2, '0')}`
  return `${SYSTEM.replace('{model}', label(model))}\n\nŞu an: ${n.getDate()} ${MONTHS[n.getMonth()]} ${n.getFullYear()} ${DAYS[n.getDay()]}, saat ${time}.`
}

async function generate(key: string, model: string, contents: Turn[]): Promise<Answer> {
  const request = (thinking: boolean) => ({
    contents,
    systemInstruction: { parts: [{ text: systemPrompt(model) }] },
    generationConfig: {
      maxOutputTokens: MAX_OUTPUT_TOKENS,
      ...(thinking ? { thinkingConfig: { thinkingLevel: 'LOW' } } : {}), // speech wants the first words fast
    },
  })
  let data: Record<string, unknown>
  try {
    data = await call(key, `models/${model}:generateContent`, request(true))
  } catch (e) {
    // a model without thinking levels: ask again without them
    const f = e instanceof GeminiFailure ? e.failure : null
    if (f?.kind !== 'http' || f.status !== 400 || !/think/i.test(f.detail)) throw e
    data = await call(key, `models/${model}:generateContent`, request(false))
  }
  const [candidate] = Array.isArray(data.candidates) ? data.candidates : []
  const content = isRecord(candidate) && isRecord(candidate.content) ? candidate.content : {}
  const text = (Array.isArray(content.parts) ? content.parts : [])
    .flatMap(p => (isRecord(p) && typeof p.text === 'string' && p.thought !== true ? [p.text] : []))
    .join('')
    .trim()
  const blocked = isRecord(data.promptFeedback) && typeof data.promptFeedback.blockReason === 'string'
  if (!text) throw new Error(blocked ? 'Bu konuda yardımcı olamıyorum.' : 'Bir cevap gelmedi, tekrar dener misin?')
  const u = isRecord(data.usageMetadata) ? data.usageMetadata : {}
  return {
    text,
    model,
    usage: { input: num(u.promptTokenCount), output: num(u.candidatesTokenCount), thinking: num(u.thoughtsTokenCount) },
  }
}

/** One reply from the newest Flash the key can use, going down the list when a model is out of quota or overloaded.
 *  Rejects with a Turkish message. */
export async function ask({ key, history, text }: { key: string; history: Turn[]; text: string }): Promise<Answer> {
  const contents: Turn[] = [...history, { role: 'user', parts: [{ text }] }]
  try {
    const ranked = await ranking(key)
    const now = Date.now()
    const chain = ranked.filter(m => (down.get(m) ?? 0) <= now)
    const started = Date.now()
    let timeouts = 0
    let last: GeminiFailure | null = null
    for (const model of chain.length ? chain : ranked.slice(0, 1)) {
      if (last && (Date.now() - started > BUDGET_MS || timeouts >= 2)) break
      try {
        return await generate(key, model, contents)
      } catch (e) {
        if (!(e instanceof GeminiFailure)) throw e
        const f = e.failure
        const quota = f.kind === 'http' && f.status === 429
        const gone = f.kind === 'http' && f.status === 404 // listed but retired
        const busy = f.kind === 'http' && f.status >= 500
        if (!(quota || gone || busy || f.kind === 'timeout')) throw e
        const wait = f.kind === 'http' && quota ? quotaWait(f.detail) : gone ? 86400 : COOLDOWN_S
        down.set(model, Date.now() + wait * 1000)
        if (f.kind === 'timeout') timeouts++
        last = e
      }
    }
    throw last ?? new GeminiFailure({ kind: 'no-model' })
  } catch (e) {
    throw new Error(describe(e))
  }
}
