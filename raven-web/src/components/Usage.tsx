import { useLayoutEffect, useRef, useState } from 'react'
import { summarize, tokens, type DayUsage, type UsageEntry } from '../lib/usage'

const full = new Intl.NumberFormat('tr-TR')
const compact = new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 })
const dayLabel = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' })
const dayLong = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', weekday: 'long' })

const CHART_H = 220
const PAD = { top: 14, right: 8, bottom: 28, left: 46 }
const BAR_MAX = 24
const BAR_GAP = 2
const RADIUS = 4

/** A clean step (1, 2, 5 × 10ⁿ) so the axis reads 0 / 2 B / 4 B rather than 0 / 1.837 / 3.674. */
function niceStep(v: number) {
  const p = 10 ** Math.floor(Math.log10(Math.max(v, 1)))
  return [1, 2, 5, 10].map(m => m * p).find(s => s >= v) ?? 10 * p
}

/** Column with a 4px rounded data end and a square foot on the baseline. */
function column(x: number, y: number, w: number, h: number) {
  const r = Math.min(RADIUS, h, w / 2)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

function DailyChart({ days }: { days: DayUsage[] }) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)
  const [active, setActive] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    setWidth(el.clientWidth)
    const ro = new ResizeObserver(([e]) => e && setWidth(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const peak = Math.max(...days.map(tokens), 0)
  const step = niceStep(peak / 4 || 1)
  const top = Math.max(step, Math.ceil(peak / step) * step)
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  const plotW = Math.max(0, width - PAD.left - PAD.right)
  const plotH = CHART_H - PAD.top - PAD.bottom
  const slot = plotW / days.length
  const barW = Math.max(2, Math.min(BAR_MAX, slot - BAR_GAP * 4))
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH
  const labelEvery = slot < 34 ? 2 : 1
  const shown = active === null ? null : days[active]

  return (
    <div className="chart" ref={box}>
      <svg width={width} height={CHART_H} role="img" aria-label="Son 14 günün günlük token kullanımı">
        {ticks.map(t => (
          <g key={t}>
            <line className="chart-grid" x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="chart-axis" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">{compact.format(t)}</text>
          </g>
        ))}
        {days.map((d, i) => {
          const total = tokens(d)
          const x = PAD.left + i * slot + (slot - barW) / 2
          const h = (total / top) * plotH
          return (
            <g key={d.day}>
              {total > 0 && <path className="chart-bar" data-active={active === i} d={column(x, y(total), barW, h)} />}
              {i % labelEvery === (days.length - 1) % labelEvery && (
                <text className="chart-axis" x={x + barW / 2} y={CHART_H - 8} textAnchor="middle">
                  {dayLabel.format(d.day)}
                </text>
              )}
              {/* the whole column is the hover / focus target, bigger than the bar */}
              <rect className="chart-hit" x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} tabIndex={0}
                aria-label={`${dayLong.format(d.day)}: ${full.format(total)} token`}
                onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)} onBlur={() => setActive(null)} />
            </g>
          )
        })}
      </svg>
      {shown && active !== null && (
        <div className="chart-tip" role="status"
          style={{ left: Math.min(Math.max(PAD.left + (active + 0.5) * slot, 90), width - 90), top: Math.max(y(tokens(shown)) - 12, 0) }}>
          <strong>{full.format(tokens(shown))} token</strong>
          <span className="chart-tip-day">{dayLong.format(shown.day)}</span>
          <span>Girdi {full.format(shown.input)} · Çıktı {full.format(shown.output)}</span>
          <span>Düşünme {full.format(shown.thinking)} · {shown.requests} istek</span>
        </div>
      )}
    </div>
  )
}

function DailyTable({ days }: { days: DayUsage[] }) {
  return (
    <table className="usage-table">
      <thead>
        <tr><th>Gün</th><th>İstek</th><th>Girdi</th><th>Çıktı</th><th>Düşünme</th><th>Toplam</th></tr>
      </thead>
      <tbody>
        {[...days].reverse().map(d => (
          <tr key={d.day}>
            <td>{dayLabel.format(d.day)}</td><td>{d.requests}</td><td>{full.format(d.input)}</td>
            <td>{full.format(d.output)}</td><td>{full.format(d.thinking)}</td><td>{full.format(tokens(d))}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

type Props = { entries: UsageEntry[]; onChangeKey: () => void; onReset: () => void }

/** Tokens spent through Raven in this browser, in the spirit of AI Studio's usage page. */
export function Usage({ entries, onChangeKey, onReset }: Props) {
  const [asTable, setAsTable] = useState(false)
  const s = summarize(entries)
  const tiles = [
    ['Toplam token', compact.format(s.total), full.format(s.total)],
    ['Bugün', compact.format(s.today), full.format(s.today)],
    ['İstek', full.format(s.requests), full.format(s.requests)],
    ['İstek başına ortalama', compact.format(s.average), full.format(s.average)],
  ] as const

  return (
    <section className="usage" aria-labelledby="usage-title">
      <h1 className="usage-title" id="usage-title">Kullanım</h1>
      <p className="usage-sub">Raven'ın bu tarayıcıda senin anahtarınla harcadığı Gemini token'ları.</p>

      <div className="kpis">
        {tiles.map(([label, value, exact]) => (
          <div className="kpi" key={label} title={exact}>
            <span className="kpi-label">{label}</span>
            <span className="kpi-value">{value}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Günlük token, son 14 gün</h2>
          <button type="button" className="chip" aria-pressed={asTable} onClick={() => setAsTable(t => !t)}>
            {asTable ? 'Grafik' : 'Tablo'}
          </button>
        </div>
        {s.requests === 0 && <p className="usage-empty">Henüz istek yok. Raven'a bir şey sorduğunda burada görünecek.</p>}
        {asTable ? <DailyTable days={s.byDay} /> : <DailyChart days={s.byDay} />}
      </div>

      {s.byModel.length > 0 && (
        <div className="card">
          <div className="card-head"><h2>Modeller</h2></div>
          <table className="usage-table">
            <thead>
              <tr><th>Model</th><th>İstek</th><th>Girdi</th><th>Çıktı</th><th>Düşünme</th><th>Toplam</th></tr>
            </thead>
            <tbody>
              {s.byModel.map(m => (
                <tr key={m.model}>
                  <td>{m.model}</td><td>{m.requests}</td><td>{full.format(m.input)}</td><td>{full.format(m.output)}</td>
                  <td>{full.format(m.thinking)}</td><td>{full.format(tokens(m))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="usage-note">
        Bu sayılar yalnızca bu tarayıcıdan Raven ile yapılan istekleri kapsar. Anahtarının tüm kullanımını ve
        limitlerini <a href="https://aistudio.google.com/" target="_blank" rel="noreferrer">Google AI Studio</a>'da
        Dashboard → Usage bölümünde görebilirsin.
      </p>
      <div className="usage-actions">
        <button type="button" className="chip" onClick={onChangeKey}>Anahtarı değiştir</button>
        <button type="button" className="chip" onClick={onReset} disabled={s.requests === 0}>Kullanım verisini sıfırla</button>
      </div>
    </section>
  )
}
