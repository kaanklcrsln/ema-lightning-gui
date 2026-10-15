import { useEffect, useRef, useState } from 'react'
import { RATES, SPEED_MAX, SPEED_MIN, type VoiceSettings } from '../lib/voice'
import { randomSeed, SEED_MAX } from '../lib/settings'
import { Icon } from './Icon'

// The speed slider is logarithmic, like EMA Island's: 1× sits in the middle of 0.25×..4×.
const STEPS = 1000
const toSlider = (speed: number) => Math.round((Math.log(speed / SPEED_MIN) / Math.log(SPEED_MAX / SPEED_MIN)) * STEPS)
const fromSlider = (v: number) => Math.round(SPEED_MIN * (SPEED_MAX / SPEED_MIN) ** (v / STEPS) * 100) / 100

/** Bottom-right button with EMA's voice settings: speed, sample rate and seed. */
export function VoiceSettingsMenu({ value, onChange }: { value: VoiceSettings; onChange: (v: VoiceSettings) => void }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (e.target instanceof Node && !root.current?.contains(e.target)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const set = (patch: Partial<VoiceSettings>) => onChange({ ...value, ...patch })

  return (
    <div className="voice-settings" ref={root}>
      {open && (
        <div className="vs-panel" role="dialog" aria-label="Ses ayarları">
          <h2 className="vs-title">Ses</h2>

          <div className="vs-row">
            <label htmlFor="vs-speed">Hız</label>
            <output htmlFor="vs-speed">{value.speed.toFixed(2)}×</output>
          </div>
          <input id="vs-speed" type="range" min={0} max={STEPS} value={toSlider(value.speed)}
            onChange={e => set({ speed: fromSlider(Number(e.target.value)) })}
            onDoubleClick={() => set({ speed: 1 })} title="Çift tıklayınca 1×" />

          <div className="vs-row">
            <span id="vs-rate">Örnekleme</span>
            <output>{value.sampleRate / 1000} kHz</output>
          </div>
          <div className="vs-seg" role="radiogroup" aria-labelledby="vs-rate">
            {RATES.map(r => (
              <button key={r} type="button" role="radio" aria-checked={value.sampleRate === r}
                onClick={() => set({ sampleRate: r })}>
                {r / 1000}
              </button>
            ))}
          </div>

          <div className="vs-row">
            <label htmlFor="vs-seed">Seed</label>
          </div>
          <div className="vs-seed">
            <input id="vs-seed" type="number" min={0} max={SEED_MAX} value={value.seed}
              onChange={e => {
                const n = Math.trunc(Number(e.target.value))
                if (Number.isFinite(n)) set({ seed: Math.min(SEED_MAX, Math.max(0, n)), seedLocked: true })
              }} />
            <button type="button" className="icon-btn" onClick={() => set({ seed: randomSeed() })} aria-label="Rastgele seed">
              <Icon name="dice" size={20} />
            </button>
            <button type="button" className="icon-btn" data-on={value.seedLocked} aria-pressed={value.seedLocked}
              onClick={() => set({ seedLocked: !value.seedLocked })} aria-label="Seed kilidi">
              <Icon name={value.seedLocked ? 'lock' : 'unlock'} size={20} />
            </button>
          </div>
          <p className="vs-hint">
            {value.seedLocked ? 'Kilitli: her cevap bu seed ile okunur.' : 'Her cevap yeni bir seed ile okunur.'}
          </p>
        </div>
      )}
      <button type="button" className="vs-toggle" aria-expanded={open} aria-label="Ses ayarları"
        onClick={() => setOpen(o => !o)}>
        <Icon name="sliders" />
      </button>
    </div>
  )
}
