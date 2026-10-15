import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { Icon } from './Icon'

const BARS = 40
const FLAT = Array.from({ length: BARS }, () => 0.25)

let playingNow: HTMLAudioElement | null = null // only one voice message plays at a time

/** Loudness of BARS slices of the clip, scaled to 0.15..1, for the waveform. */
async function waveform(blob: Blob): Promise<number[]> {
  const audio = await new OfflineAudioContext(1, 1, 8000).decodeAudioData(await blob.arrayBuffer())
  const data = audio.getChannelData(0)
  const step = Math.max(1, Math.floor(data.length / BARS))
  const rms = Array.from({ length: BARS }, (_, b) => {
    let sum = 0
    for (let i = b * step; i < Math.min(data.length, (b + 1) * step); i++) sum += (data[i] ?? 0) ** 2
    return Math.sqrt(sum / step)
  })
  const peak = Math.max(...rms, 1e-6)
  return rms.map(v => 0.15 + 0.85 * (v / peak))
}

export const formatTime = (s: number) => {
  const t = Math.max(0, Math.round(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

export function VoiceMessage({ audio, duration, autoPlay = false }: { audio: Blob; duration: number; autoPlay?: boolean }) {
  const url = useMemo(() => URL.createObjectURL(audio), [audio])
  useEffect(() => () => URL.revokeObjectURL(url), [url])
  const el = useRef<HTMLAudioElement>(null)
  const [bars, setBars] = useState<number[]>(FLAT)
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)

  useEffect(() => {
    let live = true
    waveform(audio).then(b => live && setBars(b), () => live && setBars(FLAT))
    return () => {
      live = false
    }
  }, [audio])

  useEffect(() => {
    if (!playing) return
    let frame = 0
    const follow = () => {
      if (el.current) setPosition(el.current.currentTime)
      frame = requestAnimationFrame(follow)
    }
    frame = requestAnimationFrame(follow)
    return () => cancelAnimationFrame(frame)
  }, [playing])

  const play = () => {
    const a = el.current
    if (!a) return
    if (playingNow && playingNow !== a) playingNow.pause()
    playingNow = a
    // the browser may refuse to start without a click (autoplay policy); the play button is still there
    a.play().catch(() => setPlaying(false))
  }

  useEffect(() => {
    if (autoPlay) play() // only when the message first appears
  }, [])

  const seekTo = (t: number) => {
    const a = el.current
    if (!a) return
    a.currentTime = Math.max(0, Math.min(duration, t))
    setPosition(a.currentTime)
  }
  const onWaveClick = (e: MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    seekTo(((e.clientX - box.left) / box.width) * duration)
  }
  const onWaveKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowRight') seekTo(position + 2)
    else if (e.key === 'ArrowLeft') seekTo(position - 2)
    else return
    e.preventDefault()
  }

  const progress = duration > 0 ? position / duration : 0
  return (
    <div className="voice">
      <button type="button" className="voice-play" onClick={() => (playing ? el.current?.pause() : play())}
        aria-label={playing ? 'Duraklat' : 'Oynat'}>
        <Icon name={playing ? 'pause' : 'play'} size={20} />
      </button>
      <div className="voice-wave" onClick={onWaveClick} onKeyDown={onWaveKey} role="slider" tabIndex={0}
        aria-label="Konum" aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(position)}
        aria-valuetext={formatTime(position)}>
        {bars.map((h, i) => <span key={i} data-on={(i + 0.5) / BARS <= progress} style={{ height: `${h * 100}%` }} />)}
      </div>
      <span className="voice-time">{formatTime(playing || position > 0 ? position : duration)}</span>
      <audio ref={el} src={url} preload="auto" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setPosition(0)
        }} />
    </div>
  )
}
