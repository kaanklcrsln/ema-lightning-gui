import { useLayoutEffect, useRef, useState } from 'react'
import { caretPoint, type Point } from '../lib/gaze'
import { Icon } from './Icon'

const MAX_HEIGHT = 200

type Props = {
  busy: boolean
  onSend: (text: string) => void
  /** Where the caret is while typing (null when the box loses focus), so the avatar can follow it. */
  onCaret: (p: Point | null) => void
}

export function Composer({ busy, onSend, onCaret }: Props) {
  const [text, setText] = useState('')
  const area = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  const reportCaret = () => {
    const el = area.current
    if (el && document.activeElement === el) onCaret(caretPoint(el))
  }

  const send = () => {
    const t = text.trim()
    if (!t || busy) return
    onSend(t)
    setText('')
    onCaret(null)
  }

  return (
    <form className="composer" onSubmit={e => {
      e.preventDefault()
      send()
    }}>
      <textarea ref={area} rows={1} value={text} placeholder="Raven'a sor" aria-label="Mesaj"
        onChange={e => {
          setText(e.target.value)
          requestAnimationFrame(reportCaret)
        }}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            send()
          }
        }}
        onKeyUp={reportCaret} onClick={reportCaret} onSelect={reportCaret} onBlur={() => onCaret(null)} />
      <button type="submit" className="send-btn" disabled={busy || !text.trim()} aria-label="Gönder">
        <Icon name="arrowUp" />
      </button>
    </form>
  )
}
