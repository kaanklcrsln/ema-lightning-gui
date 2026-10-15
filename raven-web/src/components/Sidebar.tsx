import { useEffect, useRef, useState } from 'react'
import { Kirby, type AnimationName } from '../../../kirby-avatar/Kirby'
import { Icon } from './Icon'

const SETTLE_MS = 700

type Props = { open: boolean; onToggle: () => void; usageOpen: boolean; onUsage: () => void }

/** The rail on the left. Raven sits on top: clicking it opens or closes the sidebar, and its face reacts.
 *  The usage tab sits at the bottom. */
export function Sidebar({ open, onToggle, usageOpen, onUsage }: Props) {
  const [mood, setMood] = useState<AnimationName>('idle')
  const shown = useRef(open)

  useEffect(() => {
    if (shown.current === open) return
    shown.current = open
    setMood(open ? 'surprised' : 'drowsy')
    const settle = window.setTimeout(() => setMood(open ? 'happy' : 'idle'), SETTLE_MS)
    return () => window.clearTimeout(settle)
  }, [open])

  return (
    <aside className="sidebar" data-open={open}>
      <button type="button" className="sidebar-avatar" onClick={onToggle} aria-expanded={open}
        aria-label={open ? 'Kenar çubuğunu kapat' : 'Kenar çubuğunu aç'}>
        <Kirby animation={mood} size={40} />
      </button>
      <button type="button" className="sidebar-tab" onClick={onUsage} aria-pressed={usageOpen} aria-label="Kullanım"
        title="Kullanım">
        <Icon name="chart" />
        <span className="sidebar-label">Kullanım</span>
      </button>
    </aside>
  )
}
