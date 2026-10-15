// Gemini tokens spent through Raven in this browser, from the usageMetadata of each reply.
import type { TokenUsage } from './gemini'

export type UsageEntry = TokenUsage & { at: number; model: string }

const KEY = 'raven.usage'
const MAX_ENTRIES = 2000
const DAY_MS = 86_400_000

const isEntry = (v: unknown): v is UsageEntry =>
  typeof v === 'object' && v !== null && 'at' in v && typeof v.at === 'number' && 'model' in v &&
  typeof v.model === 'string' && 'input' in v && typeof v.input === 'number' && 'output' in v &&
  typeof v.output === 'number' && 'thinking' in v && typeof v.thinking === 'number'

export function loadUsage(): UsageEntry[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(raw) ? raw.filter(isEntry) : []
  } catch {
    return [] // storage blocked or a corrupt entry: start empty
  }
}

function save(entries: UsageEntry[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries))
  } catch {
    // storage blocked: usage is counted for this session only
  }
}

export function recordUsage(entries: UsageEntry[], entry: UsageEntry): UsageEntry[] {
  const next = [...entries, entry].slice(-MAX_ENTRIES)
  save(next)
  return next
}

export function clearUsage(): UsageEntry[] {
  save([])
  return []
}

export const tokens = (u: TokenUsage) => u.input + u.output + u.thinking

const startOfDay = (t: number) => {
  const d = new Date(t)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

export type DayUsage = TokenUsage & { day: number; requests: number }
export type ModelUsage = TokenUsage & { model: string; requests: number }

export function summarize(entries: UsageEntry[], days = 14, now = Date.now()) {
  const first = startOfDay(now) - (days - 1) * DAY_MS
  const byDay: DayUsage[] = Array.from({ length: days }, (_, i) => ({
    day: first + i * DAY_MS, requests: 0, input: 0, output: 0, thinking: 0,
  }))
  const models = new Map<string, ModelUsage>()
  for (const e of entries) {
    const slot = byDay[Math.round((startOfDay(e.at) - first) / DAY_MS)] // rounding absorbs DST hour shifts
    if (slot) {
      slot.requests++
      slot.input += e.input
      slot.output += e.output
      slot.thinking += e.thinking
    }
    const m = models.get(e.model) ?? { model: e.model, requests: 0, input: 0, output: 0, thinking: 0 }
    m.requests++
    m.input += e.input
    m.output += e.output
    m.thinking += e.thinking
    models.set(e.model, m)
  }
  const total = entries.reduce((s, e) => s + tokens(e), 0)
  const last = byDay[byDay.length - 1]
  return {
    total,
    today: last ? tokens(last) : 0,
    requests: entries.length,
    average: entries.length ? Math.round(total / entries.length) : 0,
    byDay,
    byModel: [...models.values()].sort((a, b) => tokens(b) - tokens(a)),
  }
}
