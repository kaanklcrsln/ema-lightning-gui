import { useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'
import { VoiceMessage } from './VoiceMessage'

export type Message =
  | { id: string; kind: 'user-text'; text: string }
  /** transcript: null while the server is still turning it into text, '' if that failed */
  | { id: string; kind: 'user-voice'; audio: Blob; duration: number; transcript: string | null }
  | { id: string; kind: 'raven'; audio: Blob; duration: number; text: string }
  | { id: string; kind: 'error'; text: string }

export function Dots({ big = false }: { big?: boolean }) {
  return (
    <span className={big ? 'dots big' : 'dots'} role="status" aria-label="Raven düşünüyor">
      <span />
      <span />
      <span />
    </span>
  )
}

function RavenReply({ m, autoPlay }: { m: Extract<Message, { kind: 'raven' }>; autoPlay: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="row raven">
      <div className="bubble">
        <VoiceMessage audio={m.audio} duration={m.duration} autoPlay={autoPlay} />
      </div>
      <button type="button" className="transcript-toggle" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {open ? 'Metni gizle' : 'Metni göster'}
        <span className="chevron" data-open={open}><Icon name="chevron" size={16} /></span>
      </button>
      {open && <p className="transcript">{m.text}</p>}
    </div>
  )
}

function Row({ m, autoPlay }: { m: Message; autoPlay: boolean }) {
  switch (m.kind) {
    case 'user-text':
      return <div className="row user"><div className="bubble">{m.text}</div></div>
    case 'user-voice':
      return (
        <div className="row user">
          <div className="bubble"><VoiceMessage audio={m.audio} duration={m.duration} /></div>
          {m.transcript === null
            ? <p className="caption">Yazıya dökülüyor…</p>
            : m.transcript && <p className="caption">{m.transcript}</p>}
        </div>
      )
    case 'raven':
      return <RavenReply m={m} autoPlay={autoPlay} />
    case 'error':
      return <div className="row raven error"><div className="bubble" role="alert">{m.text}</div></div>
    default: {
      const _exhaustive: never = m
      return _exhaustive
    }
  }
}

export function Chat({ messages, pending, autoPlayId }: { messages: Message[]; pending: boolean; autoPlayId: string | null }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])
  // Until Raven has answered once, the loader sits in the middle of the screen where the avatar was.
  const firstAnswer = pending && !messages.some(m => m.kind === 'raven' || m.kind === 'error')
  return (
    <div className="chat">
      <div className="chat-list">
        {messages.map(m => <Row key={m.id} m={m} autoPlay={m.id === autoPlayId} />)}
        {pending && !firstAnswer && <div className="row raven"><div className="bubble"><Dots /></div></div>}
        <div ref={end} />
      </div>
      {firstAnswer && (
        <div className="center-loader">
          <Dots big />
          <p>Raven düşünüyor</p>
        </div>
      )}
    </div>
  )
}
