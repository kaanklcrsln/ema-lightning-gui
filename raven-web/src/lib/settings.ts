import { isSampleRate, SPEED_MAX, SPEED_MIN, type VoiceSettings } from './voice'

const KEY = 'raven.voice'
export const SEED_MAX = 2 ** 31 - 1

export const randomSeed = () => Math.floor(Math.random() * SEED_MAX)

const defaults = (): VoiceSettings => ({ speed: 1, sampleRate: 48000, seed: randomSeed(), seedLocked: false })

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

/** Voice settings remembered in this browser; anything missing or out of range falls back to the default. */
export function loadVoice(): VoiceSettings {
  const d = defaults()
  let saved: unknown = null
  try {
    saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
  } catch {
    return d // storage blocked (private window) or a corrupt entry: start from the defaults
  }
  if (!isRecord(saved)) return d
  const { speed, sampleRate, seed, seedLocked } = saved
  return {
    speed: typeof speed === 'number' && speed >= SPEED_MIN && speed <= SPEED_MAX ? speed : d.speed,
    sampleRate: isSampleRate(sampleRate) ? sampleRate : d.sampleRate,
    seed: Number.isInteger(seed) && typeof seed === 'number' && seed >= 0 && seed <= SEED_MAX ? seed : d.seed,
    seedLocked: typeof seedLocked === 'boolean' ? seedLocked : d.seedLocked,
  }
}

export function saveVoice(v: VoiceSettings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(v))
  } catch {
    // storage blocked: the settings still apply, they just aren't remembered
  }
}
