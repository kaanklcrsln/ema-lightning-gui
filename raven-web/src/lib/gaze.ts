export type Point = { x: number; y: number }

// Styles a hidden copy of the textarea needs so its text wraps exactly like the real one.
const MIRRORED = [
  'box-sizing', 'width', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'border-top-width',
  'border-right-width', 'border-bottom-width', 'border-left-width', 'border-style', 'font-family', 'font-size',
  'font-weight', 'font-style', 'letter-spacing', 'line-height', 'text-transform', 'word-spacing', 'tab-size',
]

/** Where the caret is on screen, measured with a hidden mirror of the textarea. */
export function caretPoint(el: HTMLTextAreaElement): Point {
  const style = getComputedStyle(el)
  const mirror = document.createElement('div')
  for (const p of MIRRORED) mirror.style.setProperty(p, style.getPropertyValue(p))
  Object.assign(mirror.style, {
    position: 'fixed', top: '0', left: '-9999px', visibility: 'hidden', whiteSpace: 'pre-wrap', overflowWrap: 'break-word',
  })
  mirror.textContent = el.value.slice(0, el.selectionEnd)
  const marker = document.createElement('span')
  marker.textContent = '​'
  mirror.append(marker)
  document.body.append(mirror)
  const box = el.getBoundingClientRect()
  const point = {
    x: box.left + marker.offsetLeft - el.scrollLeft,
    y: box.top + marker.offsetTop - el.scrollTop + marker.offsetHeight / 2,
  }
  mirror.remove()
  return point
}

const clamp = (v: number) => Math.max(-1, Math.min(1, v))

/** Direction from the middle of `from` to `to`, -1..1 on each axis, for Kirby's look(). */
export function directionTo(from: DOMRect, to: Point): Point {
  return {
    x: clamp((to.x - (from.left + from.width / 2)) / 320),
    y: clamp((to.y - (from.top + from.height / 2)) / 260),
  }
}
