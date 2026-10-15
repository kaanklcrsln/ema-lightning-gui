// Raven's voice lives on a Hugging Face ZeroGPU Space (raven-web/space): EMA Lightning.
import { Client, type SpaceStatus } from '@gradio/client'

export const RATES = [8000, 16000, 24000, 48000] as const
export type SampleRate = (typeof RATES)[number]
export const SPEED_MIN = 0.25
export const SPEED_MAX = 4

export type VoiceSettings = { speed: number; sampleRate: SampleRate; seed: number; seedLocked: boolean }

export const isSampleRate = (v: unknown): v is SampleRate => RATES.some(r => r === v)

/** "user/space" on Hugging Face, or a full URL such as the local `python app.py`. */
export const SPACE: string = import.meta.env.VITE_RAVEN_SPACE || 'http://127.0.0.1:7860/'

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

const listeners = new Set<(s: SpaceStatus) => void>()
let connecting: Promise<Client> | null = null

/** Space status changes while connecting (sleeping, building, running...). */
export function onSpaceStatus(listener: (s: SpaceStatus) => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function connect(): Promise<Client> {
  connecting ??= Client.connect(SPACE, { status_callback: s => listeners.forEach(l => l(s)) }).catch((e: unknown) => {
    connecting = null // try again on the next call
    throw e
  })
  return connecting
}

/** Gradio rejects with an Error or with a status object carrying `message`; this turns either into Turkish text. */
function spaceError(e: unknown): Error {
  const message = e instanceof Error ? e.message : isRecord(e) && typeof e.message === 'string' ? e.message : String(e)
  if (/quota/i.test(message)) {
    return new Error('Ses sunucusunun bugünkü ücretsiz GPU kotan doldu. Kota 24 saat içinde yenilenir.')
  }
  if (/app config|fetch|network/i.test(message)) {
    return new Error('Ses sunucusuna (Hugging Face) ulaşılamadı. Bağlı olduğun ağ hf.space adreslerini engelliyor olabilir.')
  }
  return new Error(message || 'Ses sunucusunda bir hata oluştu.')
}

async function predict(endpoint: string, data: Record<string, unknown>): Promise<unknown> {
  try {
    const result = await (await connect()).predict(endpoint, data)
    return Array.isArray(result.data) ? result.data[0] : undefined
  } catch (e) {
    throw spaceError(e)
  }
}

const base64ToBlob = (b64: string, type: string) => {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type })
}

export async function speak(text: string, voice: VoiceSettings): Promise<{ audio: Blob; duration: number }> {
  const out = await predict('/speak', { text, speed: voice.speed, seed: voice.seed, sample_rate: voice.sampleRate })
  if (!isRecord(out) || typeof out.audio !== 'string' || typeof out.duration !== 'number') {
    throw new Error('Ses sunucusundan beklenmedik bir cevap geldi.')
  }
  return { audio: base64ToBlob(out.audio, 'audio/wav'), duration: out.duration }
}
