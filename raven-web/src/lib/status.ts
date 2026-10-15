import { useEffect, useState } from 'react'
import { connect, onSpaceStatus } from './voice'

export type SpaceState =
  | { kind: 'connecting' }
  | { kind: 'waking' }
  | { kind: 'ready' }
  | { kind: 'error'; message: string }

const RETRY_MS = 15000

/** Connects to the voice Space on load. A free Space sleeps when idle; waking it takes a minute or two. */
export function useSpaceStatus(): SpaceState {
  const [state, setState] = useState<SpaceState>({ kind: 'connecting' })
  useEffect(() => {
    let live = true
    let timer = 0
    const off = onSpaceStatus(s => {
      if (!live) return
      if (s.status === 'sleeping' || s.status === 'building' || s.status === 'starting') setState({ kind: 'waking' })
      else if (s.status === 'space_error' || s.status === 'paused' || s.status === 'error' || s.status === 'stopped') {
        setState({ kind: 'error', message: s.message || 'Ses sunucusu şu an çalışmıyor.' })
      }
    })
    const attempt = () => {
      connect().then(
        () => live && setState({ kind: 'ready' }),
        (e: unknown) => {
          if (!live) return
          const why = e instanceof Error ? e.message : String(e)
          setState({ kind: 'error', message: `Ses sunucusuna bağlanılamadı (${why}).` })
          timer = window.setTimeout(attempt, RETRY_MS)
        },
      )
    }
    attempt()
    return () => {
      live = false
      off()
      window.clearTimeout(timer)
    }
  }, [])
  return state
}
