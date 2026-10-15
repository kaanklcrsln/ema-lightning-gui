import { useEffect, useRef, useState } from 'react'
import { Kirby, type AnimationName, type AvatarHandle } from '../../kirby-avatar/Kirby'
import { Chat, type Message } from './components/Chat'
import { Composer } from './components/Composer'
import { KeyGate } from './components/KeyGate'
import { Sidebar } from './components/Sidebar'
import { Usage } from './components/Usage'
import { VoiceSettingsMenu } from './components/VoiceSettings'
import { ask, MAX_HISTORY, type Turn } from './lib/gemini'
import { directionTo, type Point } from './lib/gaze'
import { clearKey, loadKey, saveKey } from './lib/key'
import { loadVoice, randomSeed, saveVoice } from './lib/settings'
import { useSpaceStatus, type SpaceState } from './lib/status'
import { clearUsage, loadUsage, recordUsage, type UsageEntry } from './lib/usage'
import { speak, type VoiceSettings } from './lib/voice'

/** hero: Raven in the middle, nothing sent yet. leaving: the avatar's exit animation. chat: the conversation. */
type Stage = 'hero' | 'leaving' | 'chat'
type View = 'chat' | 'usage'

const SOURCE = 'https://github.com/kaanklcrsln/raven'
const LEAVE_MS = 450
const IDLE_MS = 1500

const statusNote = (s: SpaceState) => {
  switch (s.kind) {
    case 'connecting':
    case 'ready':
      return null
    case 'waking':
      return 'Ses sunucusu uyanıyor, bu bir iki dakika sürebilir…'
    case 'error':
      return s.message
    default: {
      const _exhaustive: never = s
      return _exhaustive
    }
  }
}

export function App() {
  const [key, setKey] = useState<string | null>(loadKey)
  if (!key) {
    return <KeyGate onKey={k => {
      saveKey(k)
      setKey(k)
    }} />
  }
  return <Raven apiKey={key} onForgetKey={() => {
    clearKey()
    setKey(null)
  }} />
}

function Raven({ apiKey, onForgetKey }: { apiKey: string; onForgetKey: () => void }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [view, setView] = useState<View>('chat')
  const [stage, setStage] = useState<Stage>('hero')
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [autoPlayId, setAutoPlayId] = useState<string | null>(null)
  const [voice, setVoice] = useState<VoiceSettings>(loadVoice)
  const [usage, setUsage] = useState<UsageEntry[]>(loadUsage)
  const [mood, setMood] = useState<AnimationName>('idle')
  const status = useSpaceStatus()
  const history = useRef<Turn[]>([]) // the conversation as Gemini sees it; gone when the page closes
  const hero = useRef<AvatarHandle>(null)
  const heroBox = useRef<HTMLDivElement>(null)
  const idleTimer = useRef(0)

  useEffect(() => saveVoice(voice), [voice])

  const settle = () => {
    window.clearTimeout(idleTimer.current)
    hero.current?.look(null)
    setMood('idle')
  }

  const onCaret = (p: Point | null) => {
    const box = heroBox.current?.getBoundingClientRect()
    if (stage !== 'hero' || !p || !box) return settle()
    window.clearTimeout(idleTimer.current)
    hero.current?.look(directionTo(box, p))
    setMood('listening')
    idleTimer.current = window.setTimeout(settle, IDLE_MS)
  }

  const send = async (text: string) => {
    if (pending) return
    setMessages(ms => [...ms, { id: crypto.randomUUID(), kind: 'user-text', text }])
    if (stage === 'hero') {
      settle()
      setStage('leaving')
      window.setTimeout(() => setStage('chat'), LEAVE_MS)
    }
    const seed = voice.seedLocked ? voice.seed : randomSeed()
    if (!voice.seedLocked) setVoice(v => ({ ...v, seed }))
    const fail = (message: string) => setMessages(ms => [...ms, { id: crypto.randomUUID(), kind: 'error', text: message }])
    const reason = (e: unknown) => (e instanceof Error ? e.message : String(e))
    setPending(true)
    try {
      if (history.current.length >= MAX_HISTORY) history.current = [] // a new conversation; history is never edited
      const answer = await ask({ key: apiKey, history: history.current, text })
      history.current = [...history.current, { role: 'user', parts: [{ text }] }, { role: 'model', parts: [{ text: answer.text }] }]
      const entry = { at: Date.now(), model: answer.model, ...answer.usage }
      setUsage(u => recordUsage(u, entry))
      try {
        const spoken = await speak(answer.text, { ...voice, seed })
        const ravenId = crypto.randomUUID()
        setMessages(ms => [...ms, { id: ravenId, kind: 'raven', audio: spoken.audio, duration: spoken.duration, text: answer.text }])
        setAutoPlayId(ravenId)
      } catch (e) {
        fail(`${answer.text}\n\nBu cevap seslendirilemedi: ${reason(e)}`)
      }
    } catch (e) {
      fail(reason(e))
    } finally {
      setPending(false)
    }
  }

  const note = statusNote(status)
  return (
    <div className="app">
      <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen(o => !o)} usageOpen={view === 'usage'}
        onUsage={() => setView(v => (v === 'usage' ? 'chat' : 'usage'))} />
      <main className="main" data-stage={stage} data-view={view}>
        <header className="topbar">
          <button type="button" className="brand" onClick={() => setView('chat')}>Raven</button>
        </header>
        {view === 'usage' ? (
          <div className="usage-scroll">
            <Usage entries={usage} onChangeKey={onForgetKey} onReset={() => setUsage(clearUsage())} />
          </div>
        ) : (
          <>
            <div className="center">
              {stage === 'chat' ? (
                <Chat messages={messages} pending={pending} autoPlayId={autoPlayId} />
              ) : (
                <section className="hero" data-leaving={stage === 'leaving'}>
                  <div className="hero-avatar" ref={heroBox}>
                    <Kirby ref={hero} animation={mood} size="100%" />
                  </div>
                  <h1 className="hero-title">Bugün ne soralım?</h1>
                </section>
              )}
              <div className="dock">
                <Composer busy={pending} onSend={t => void send(t)} onCaret={onCaret} />
              </div>
            </div>
            <VoiceSettingsMenu value={voice} onChange={setVoice} />
          </>
        )}
        <p className="footnote" role={note ? 'status' : undefined}>
          {note ?? 'Raven bir yapay zekâ, yanılabilir. Ses: EMA Lightning.'}{' '}
          <a href={SOURCE} target="_blank" rel="noreferrer">Kaynak kodu</a>
        </p>
      </main>
    </div>
  )
}
