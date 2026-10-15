import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { caretPoint, type Point } from '../lib/gaze'
import { startRecording, type Recorded, type Recording } from '../lib/recorder'
import { Icon } from './Icon'
import { formatTime } from './VoiceMessage'

export type Sent = { kind: 'text'; text: string } | { kind: 'voice'; recorded: Recorded }

const LIVE_BARS = 28
const MIN_RECORDING_S = 0.4
const MAX_HEIGHT = 200

type Props = {
  busy: boolean
  onSend: (s: Sent) => void
  /** Where the caret is while typing (null when the box loses focus), so the avatar can follow it. */
  onCaret: (p: Point | null) => void
  onRecordingChange: (recording: boolean) => void
}

const micMessage = (e: unknown) =>
  e instanceof DOMException && e.name === 'NotAllowedError'
    ? 'Mikrofon izni verilmedi. Tarayıcının adres çubuğundan izin verebilirsin.'
    : e instanceof Error ? e.message : String(e)

export function Composer({ busy, onSend, onCaret, onRecordingChange }: Props) {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState<Recording | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array.from({ length: LIVE_BARS }, () => 0))
  const [micError, setMicError] = useState<string | null>(null)
  const area = useRef<HTMLTextAreaElement>(null)
  const live = useRef<Recording | null>(null)

  useEffect(() => () => live.current?.cancel(), []) // leaving the page mid-recording frees the microphone

  useLayoutEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  useEffect(() => {
    if (!recording) return
    const started = performance.now()
    let frame = 0
    let last = 0
    const meter = (t: number) => {
      if (t - last > 70) {
        last = t
        setLevels(l => [...l.slice(1), recording.level()])
        setElapsed((t - started) / 1000)
      }
      frame = requestAnimationFrame(meter)
    }
    frame = requestAnimationFrame(meter)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancel()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKey)
    }
  }, [recording])

  const setLive = (r: Recording | null) => {
    live.current = r
    setRecording(r)
    onRecordingChange(r !== null)
  }

  const reportCaret = () => {
    const el = area.current
    if (el && document.activeElement === el) onCaret(caretPoint(el))
  }

  const sendText = () => {
    const t = text.trim()
    if (!t || busy) return
    onSend({ kind: 'text', text: t })
    setText('')
    onCaret(null)
  }

  const start = async () => {
    setMicError(null)
    try {
      setElapsed(0)
      setLevels(l => l.map(() => 0))
      setLive(await startRecording())
    } catch (e) {
      setMicError(micMessage(e))
    }
  }

  const finish = async () => {
    const r = live.current
    if (!r || busy) return
    setLive(null)
    try {
      const recorded = await r.stop()
      if (recorded.duration < MIN_RECORDING_S) setMicError('Kayıt çok kısa oldu, biraz daha uzun konuş.')
      else onSend({ kind: 'voice', recorded })
    } catch (e) {
      setMicError(micMessage(e))
    }
  }

  const cancel = () => {
    live.current?.cancel()
    setLive(null)
  }

  return (
    <div className="composer-wrap">
      <form className="composer" data-recording={recording !== null}
        onSubmit={e => {
          e.preventDefault()
          if (recording) void finish()
          else sendText()
        }}>
        {recording ? (
          <>
            <button type="button" className="icon-btn" onClick={cancel} aria-label="Kaydı iptal et">
              <Icon name="close" />
            </button>
            <div className="rec-live" aria-live="polite">
              <span className="rec-dot" />
              <span className="rec-time">{formatTime(elapsed)}</span>
              <span className="rec-bars" aria-hidden="true">
                {levels.map((l, i) => <span key={i} style={{ height: `${14 + l * 86}%` }} />)}
              </span>
            </div>
            <button type="button" className="icon-btn" onClick={() => void finish()} disabled={busy}
              aria-label="Kaydı bitir ve gönder">
              <Icon name="stop" />
            </button>
          </>
        ) : (
          <>
            <textarea ref={area} rows={1} value={text} placeholder="Raven'a sor" aria-label="Mesaj"
              onChange={e => {
                setText(e.target.value)
                requestAnimationFrame(reportCaret)
              }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  sendText()
                }
              }}
              onKeyUp={reportCaret} onClick={reportCaret} onSelect={reportCaret} onBlur={() => onCaret(null)} />
            <button type="button" className="icon-btn" onClick={() => void start()} disabled={busy}
              aria-label="Sesli mesaj kaydet">
              <Icon name="mic" />
            </button>
          </>
        )}
        <button type="submit" className="send-btn" disabled={busy || (!recording && !text.trim())} aria-label="Gönder">
          <Icon name="arrowUp" />
        </button>
      </form>
      {micError && <p className="composer-error" role="alert">{micError}</p>}
    </div>
  )
}
