/**
 * Pan and zoom for an inline <svg> by rewriting its `viewBox`.
 *
 * Anything drawn inside the same <svg> (device click boxes, later layers)
 * follows the view with no alignment code, and redrawing those layers never
 * touches the viewBox, so the view stays where the user left it.
 *
 * - Ctrl/⌘ + wheel zooms around the cursor, like the desktop canvas; a
 *   trackpad pinch arrives as Ctrl + wheel. A plain wheel still scrolls the page.
 * - Dragging pans once the pointer has moved a few pixels, so a plain click
 *   still reaches what was clicked. The click that ends a drag is swallowed.
 * - Two pointers pinch-zoom and pan together (touch screens).
 */

/** A rectangle in the drawing's own units, i.e. those of its original viewBox. */
export interface SvgBox {
  x: number
  y: number
  width: number
  height: number
}

export interface SvgPanZoom {
  zoomIn(): void
  zoomOut(): void
  /** Show the whole drawing (the desktop canvas's Home). */
  fit(): void
  /** Zoom to a box in drawing units, e.g. a device from platform-devices.json. */
  focus(box: SvgBox): void
  /** Detach every listener; the <svg> keeps its current view. */
  destroy(): void
}

interface Point {
  x: number
  y: number
}

/** Centre of the view in drawing units, and screen pixels per drawing unit. */
interface View {
  cx: number
  cy: number
  scale: number
}

const WHEEL_ZOOM_STEP = 1.15 // per wheel notch, as on the desktop canvas
const BUTTON_ZOOM_STEP = 1.5
const MIN_ZOOM = 0.5 // zoom limits, relative to the fitted view
const MAX_ZOOM = 20
const FOCUS_PADDING = 0.6 // around a focused box, as a fraction of its longer side
const DRAG_THRESHOLD_MOUSE = 4 // px
const DRAG_THRESHOLD_TOUCH = 10 // px
const ANIMATION_MS = 220

// Chromium sends a trackpad pinch as Ctrl + wheel with deltaY = -100·ln(scale),
// so exp(-deltaY / 100) follows the fingers. Capping each event at one desktop
// step keeps a mouse notch (deltaY ≈ 100) from jumping further than that.
const MAX_WHEEL_DELTA = 100 * Math.log(WHEEL_ZOOM_STEP)

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function wheelZoomFactor(event: WheelEvent): number {
  // Line and page deltas come from discrete notches: each one is a full step.
  const delta = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL
    ? event.deltaY
    : event.deltaY * 100
  return Math.exp(-clamp(delta, -MAX_WHEEL_DELTA, MAX_WHEEL_DELTA) / 100)
}

function contentBox(svg: SVGSVGElement): SvgBox {
  // A missing viewBox reads as null in Firefox and as an empty rect in Chromium.
  const viewBox = svg.viewBox.baseVal as DOMRect | null
  const box = viewBox && viewBox.width > 0 && viewBox.height > 0 ? viewBox : svg.getBBox()
  return { x: box.x, y: box.y, width: Math.max(box.width, 1), height: Math.max(box.height, 1) }
}

export function createSvgPanZoom(svg: SVGSVGElement): SvgPanZoom {
  // Read once: from here on the viewBox holds the view, not the drawing's extent.
  const content = contentBox(svg)
  let view: View = {
    cx: content.x + content.width / 2,
    cy: content.y + content.height / 2,
    scale: 1,
  }
  // While fitted, the view re-fits whenever the panel changes size.
  let fitted = true
  let renderFrame = 0
  let animationFrame = 0
  let animationTarget: View | null = null

  const pointers = new Map<number, Point>()
  let dragOrigin: Point = { x: 0, y: 0 }
  let panning = false
  let suppressClick = false

  function hasSize(rect: DOMRect): boolean {
    return rect.width > 0 && rect.height > 0
  }

  function fitScale(rect: DOMRect): number {
    return Math.min(rect.width / content.width, rect.height / content.height)
  }

  function fittedView(rect: DOMRect): View {
    return {
      cx: content.x + content.width / 2,
      cy: content.y + content.height / 2,
      scale: fitScale(rect),
    }
  }

  function clampScale(scale: number, rect: DOMRect): number {
    const fit = fitScale(rect)
    return clamp(scale, fit * MIN_ZOOM, fit * MAX_ZOOM)
  }

  function limited(next: View, rect: DOMRect): View {
    return {
      // Keeping the centre on the drawing means it can't be dragged out of sight.
      cx: clamp(next.cx, content.x, content.x + content.width),
      cy: clamp(next.cy, content.y, content.y + content.height),
      scale: clampScale(next.scale, rect),
    }
  }

  function writeViewBox() {
    const rect = svg.getBoundingClientRect()
    if (!hasSize(rect)) return
    const width = rect.width / view.scale
    const height = rect.height / view.scale
    svg.setAttribute(
      'viewBox',
      `${view.cx - width / 2} ${view.cy - height / 2} ${width} ${height}`,
    )
  }

  // At most one write per frame: reading layout after each write would force a
  // relayout of the whole drawing on every pointer event.
  function scheduleRender() {
    if (renderFrame) return
    renderFrame = requestAnimationFrame(() => {
      renderFrame = 0
      writeViewBox()
    })
  }

  function stopAnimation() {
    cancelAnimationFrame(animationFrame)
    animationFrame = 0
    animationTarget = null
  }

  function animateTo(next: View) {
    const rect = svg.getBoundingClientRect()
    if (!hasSize(rect)) return
    stopAnimation()
    const from = view
    const to = limited(next, rect)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      view = to
      scheduleRender()
      return
    }
    animationTarget = to
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min((now - start) / ANIMATION_MS, 1)
      const eased = 1 - (1 - t) ** 3
      view = {
        cx: from.cx + (to.cx - from.cx) * eased,
        cy: from.cy + (to.cy - from.cy) * eased,
        // Geometric, so the zoom speed looks constant.
        scale: from.scale * (to.scale / from.scale) ** eased,
      }
      writeViewBox()
      if (t < 1) animationFrame = requestAnimationFrame(step)
      else stopAnimation()
    }
    animationFrame = requestAnimationFrame(step)
  }

  /** Scale by `factor` and carry the drawing point under `from` to `to` (client px). */
  function moveView(from: Point, to: Point, factor: number) {
    const rect = svg.getBoundingClientRect()
    if (!hasSize(rect)) return
    stopAnimation()
    fitted = false
    const midX = rect.left + rect.width / 2
    const midY = rect.top + rect.height / 2
    const scale = clampScale(view.scale * factor, rect)
    view = limited({
      cx: view.cx + (from.x - midX) / view.scale - (to.x - midX) / scale,
      cy: view.cy + (from.y - midY) / view.scale - (to.y - midY) / scale,
      scale,
    }, rect)
    scheduleRender()
  }

  function zoomBy(factor: number) {
    // Repeated clicks compound from where the running animation is heading.
    const base = animationTarget ?? view
    fitted = false
    animateTo({ ...base, scale: base.scale * factor })
  }

  function pinch(): { centre: Point, distance: number } | null {
    const [a, b] = [...pointers.values()]
    if (!a || !b) return null
    return {
      centre: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      distance: Math.max(Math.hypot(a.x - b.x, a.y - b.y), 1),
    }
  }

  function beginPan(pointerId: number) {
    panning = true
    suppressClick = true
    svg.classList.add('is-panning')
    // Keep receiving moves after the pointer leaves the panel.
    svg.setPointerCapture(pointerId)
  }

  function onWheel(event: WheelEvent) {
    if (!event.ctrlKey && !event.metaKey) return
    event.preventDefault() // otherwise the browser zooms the whole page
    const at = { x: event.clientX, y: event.clientY }
    moveView(at, at, wheelZoomFactor(event))
  }

  function onPointerDown(event: PointerEvent) {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    if (event.isPrimary) {
      // A new gesture: forget pointers that were released outside the drawing.
      pointers.clear()
      panning = false
      suppressClick = false
      dragOrigin = { x: event.clientX, y: event.clientY }
    }
    stopAnimation()
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointers.size > 1) beginPan(event.pointerId)
  }

  function onPointerMove(event: PointerEvent) {
    const last = pointers.get(event.pointerId)
    if (!last) return
    if (event.buttons === 0) {
      // Released outside the drawing before a drag began, so never captured.
      pointers.delete(event.pointerId)
      return
    }
    const point = { x: event.clientX, y: event.clientY }

    if (pointers.size > 1) {
      const before = pinch()
      pointers.set(event.pointerId, point)
      const after = pinch()
      if (before && after) {
        moveView(before.centre, after.centre, after.distance / before.distance)
      }
      return
    }

    pointers.set(event.pointerId, point)
    if (panning) {
      moveView(last, point, 1)
      return
    }
    const threshold = event.pointerType === 'mouse' ? DRAG_THRESHOLD_MOUSE : DRAG_THRESHOLD_TOUCH
    if (Math.hypot(point.x - dragOrigin.x, point.y - dragOrigin.y) >= threshold) {
      beginPan(event.pointerId)
      moveView(dragOrigin, point, 1)
    }
  }

  function onPointerUp(event: PointerEvent) {
    if (!pointers.delete(event.pointerId)) return
    // With one finger left after a pinch, keep panning with it.
    if (pointers.size > 0) return
    panning = false
    svg.classList.remove('is-panning')
  }

  function onClick(event: MouseEvent) {
    if (!suppressClick) return
    suppressClick = false
    event.stopPropagation()
    event.preventDefault()
  }

  const resizeObserver = new ResizeObserver(() => {
    const rect = svg.getBoundingClientRect()
    if (!hasSize(rect)) return
    if (fitted) {
      stopAnimation()
      view = fittedView(rect)
    } else {
      view = limited(view, rect)
    }
    writeViewBox()
  })

  const listeners = new AbortController()
  const { signal } = listeners
  svg.addEventListener('wheel', onWheel, { passive: false, signal })
  svg.addEventListener('pointerdown', onPointerDown, { signal })
  svg.addEventListener('pointermove', onPointerMove, { signal })
  svg.addEventListener('pointerup', onPointerUp, { signal })
  svg.addEventListener('pointercancel', onPointerUp, { signal })
  svg.addEventListener('click', onClick, { capture: true, signal })

  // Without these, touch drags scroll or zoom the page instead, and mouse
  // drags select the drawing's text.
  svg.style.touchAction = 'none'
  svg.style.userSelect = 'none'
  svg.style.setProperty('-webkit-user-select', 'none')

  const initial = svg.getBoundingClientRect()
  if (hasSize(initial)) view = fittedView(initial)
  writeViewBox()
  resizeObserver.observe(svg)

  return {
    zoomIn: () => zoomBy(BUTTON_ZOOM_STEP),
    zoomOut: () => zoomBy(1 / BUTTON_ZOOM_STEP),
    fit() {
      const rect = svg.getBoundingClientRect()
      if (!hasSize(rect)) return
      fitted = true
      animateTo(fittedView(rect))
    },
    focus(box: SvgBox) {
      const rect = svg.getBoundingClientRect()
      if (!hasSize(rect)) return
      const padding = Math.max(box.width, box.height) * FOCUS_PADDING
      fitted = false
      animateTo({
        cx: box.x + box.width / 2,
        cy: box.y + box.height / 2,
        scale: Math.min(
          rect.width / (box.width + 2 * padding),
          rect.height / (box.height + 2 * padding),
        ),
      })
    },
    destroy() {
      listeners.abort()
      resizeObserver.disconnect()
      stopAnimation()
      cancelAnimationFrame(renderFrame)
    },
  }
}
