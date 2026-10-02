/*
 * Works wheel — the portfolio index as a wheel you turn.
 *
 * A dependency-free port of the WorksWheel React component. At rest the work
 * sits in a ring around the name; the first stretch of scroll blows the ring
 * open into a vertical drum with one piece lying flat at the front, and further
 * scrolling carries the next piece round. Geometry, the transform chain and the
 * single rAF pass follow the component.
 *
 * One change for a full page: the component traps the mouse wheel while it has
 * somewhere to turn, which works for a block inside a page but would hold a
 * visitor on the first screen. Here the stage is pinned (position: sticky) while
 * its section scrolls past, and the page's own scroll position drives `turn`,
 * so wheel, trackpad, touch, keyboard and the scrollbar all turn it and nothing
 * is trapped. When scrolling stops, the wheel settles onto the nearest piece.
 */
(() => {
  "use strict"
  const section = document.getElementById("work")
  if (!section) return
  const stage = section.querySelector(".works-stage")
  const wheel = section.querySelector(".works-wheel")
  const cards = [...section.querySelectorAll(".works-card")]
  const faces = cards.map((c) => c.firstElementChild)
  const label = section.querySelector(".works-label")
  const titleBox = section.querySelector(".works-title")
  const titleText = titleBox.querySelector(".t")
  const titleMeta = titleBox.querySelector(".m")
  const indexBtns = [...section.querySelectorAll(".works-index button")]
  const counter = section.querySelector(".works-count")
  const hint = section.querySelector(".works-hint")
  const count = cards.length
  const last = Math.max(count - 1, 0)
  if (!count) return

  // Geometry, as in the component. Narrow screens get a wider card cap so the
  // work is readable on a phone; everything else still scales off the card.
  const CARD_H = 0.38
  const CARD_MAX_W = 0.34
  const CARD_MAX_W_NARROW = 0.5
  const CARD_RATIO = 1.45
  const STEP = 40
  const DRUM = 2.22
  const LENS = 2.7
  const RING_R = 1.14
  /** The ring's radius never exceeds this share of the stage's shorter side, so a short list
      (big ring cards) still closes inside the frame instead of running under the nav. */
  const RING_FIT = 0.31
  const BOW = 1.82
  const TITLE = 0.124
  const INDEX = 0.04
  const CULL = 1.6
  const EASE = 0.12
  const SETTLE = 140
  /** Page scroll, as a share of the stage height, that turns the wheel by one item. */
  const SCROLL_PER_ITEM = 0.55

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
  const lerp = (a, b, t) => a + (b - a) * t
  const rad = (deg) => (deg * Math.PI) / 180
  const bowAt = (drumDeg, bow) => -bow * (1 - Math.cos(rad(drumDeg)))
  const place = (ringDeg, drumDeg, ringR, drumR, bow, m) =>
    `translateX(${m * bowAt(drumDeg, bow)}px)` +
    ` rotateZ(${(1 - m) * ringDeg}deg) translateY(${-(1 - m) * ringR}px)` +
    ` rotateX(${m * drumDeg}deg) translateZ(${m * drumR}px)`

  const reduceMq = window.matchMedia("(prefers-reduced-motion: reduce)")
  let reduced = reduceMq.matches
  reduceMq.addEventListener("change", () => { reduced = reduceMq.matches })

  let turn = 0
  let target = 0
  let active = -1
  let metrics = null
  let stepPx = 1
  let frame = 0

  const measure = () => {
    const w = stage.clientWidth
    const h = stage.clientHeight
    if (!w || !h) return
    const cardW = Math.min(h * CARD_H * CARD_RATIO, w * (w < 700 ? CARD_MAX_W_NARROW : CARD_MAX_W))
    const cardH = cardW / CARD_RATIO
    const ringR = Math.min(cardH * RING_R, Math.min(w, h) * RING_FIT)
    const ringScale = clamp((((2 * Math.PI * ringR) / count) * 0.82) / (cardW || 1), 0.16, 1)
    metrics = { cardW, cardH, ringR, ringScale, drumR: cardH * DRUM, bow: cardH * BOW }
    stage.style.perspective = cardH * LENS + "px"
    section.style.setProperty("--works-title", cardH * TITLE + "px")
    section.style.setProperty("--works-index", cardH * INDEX + "px")
    for (const card of cards) {
      card.style.width = cardW + "px"
      card.style.height = cardH + "px"
      card.style.marginLeft = -cardW / 2 + "px"
      card.style.marginTop = -cardH / 2 + "px"
    }
    // The section is as tall as the stage plus the scroll it takes to turn every item to the front.
    stepPx = h * SCROLL_PER_ITEM
    section.style.height = h + count * stepPx + "px"
    fromScroll()
    turn = target
    kick()
  }

  const setActive = (near) => {
    if (near === active) return
    active = near
    cards.forEach((c, i) => c.setAttribute("aria-selected", String(i === near)))
    indexBtns.forEach((b, i) => b.classList.toggle("on", i === near))
    stage.setAttribute("aria-activedescendant", cards[near].id)
    titleText.textContent = cards[near].dataset.title
    titleMeta.textContent = cards[near].dataset.meta || ""
    if (counter) counter.textContent = near + 1 + " / " + count
  }

  const draw = () => {
    frame = 0
    if (!metrics) return
    const gap = target - turn
    if (Math.abs(gap) < 0.0005) turn = target
    else turn += gap * (reduced ? 1 : EASE)

    const { ringR, ringScale, drumR, bow } = metrics
    const t = turn
    const m = clamp(t, 0, 1)
    const pos = Math.max(0, t - 1)
    wheel.style.transform = `translateZ(${-m * drumR}px)`
    for (let i = 0; i < count; i++) {
      const d = i - pos
      const drumDeg = d * STEP
      const card = cards[i]
      card.style.transform = place(d * (360 / count), drumDeg, ringR, drumR, bow, m)
      const hidden = m > 0.5 && Math.abs(d) > CULL
      card.style.opacity = hidden ? "0" : "1"
      card.style.visibility = hidden ? "hidden" : ""
      card.style.zIndex = String(Math.round(100 - Math.abs(d) * 2))
      faces[i].style.transform = `scale(${lerp(ringScale, 1, m)})`
    }
    label.style.opacity = String(1 - m)
    titleBox.style.opacity = String(m)
    if (hint) hint.style.opacity = String(clamp(1 - m * 4, 0, 1))
    setActive(clamp(Math.round(pos), 0, last))
    if (turn !== target) frame = requestAnimationFrame(draw)
  }
  const kick = () => { if (!frame) frame = requestAnimationFrame(draw) }

  // Where the page's scroll puts the wheel: 0 = ring, 1 = drum with item 0 at the front.
  const rawTurn = () => clamp((window.scrollY - section.offsetTop) / stepPx, 0, count)
  const fromScroll = () => { target = rawTurn() }

  let settling = 0
  addEventListener("scroll", () => {
    fromScroll()
    kick()
    // A scroll gesture stops wherever it stops; left there the drum would sit between two
    // pieces. Settle the wheel onto the nearest one (the page itself isn't moved).
    clearTimeout(settling)
    settling = setTimeout(() => { target = Math.round(rawTurn()); kick() }, SETTLE)
  }, { passive: true })

  // Turning to an item = scrolling the page to where that item is at the front.
  const goTo = (k) => {
    const top = section.offsetTop + clamp(k, 0, count) * stepPx
    window.scrollTo({ top, behavior: reduced ? "auto" : "smooth" })
  }
  indexBtns.forEach((b, i) => b.addEventListener("click", () => goTo(i + 1)))
  stage.addEventListener("keydown", (e) => {
    const now = Math.round(rawTurn())
    if (e.key === "ArrowDown" || e.key === "ArrowRight") goTo(now + 1)
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") goTo(now - 1)
    else return
    e.preventDefault()
  })
  // Cards are links: keep a click on a card that is still in the ring from opening it mid-turn.
  cards.forEach((c, i) => c.addEventListener("click", (e) => {
    if (turn < 0.95 || Math.abs(i - Math.max(0, turn - 1)) > 0.5) {
      e.preventDefault()
      goTo(i + 1)
    }
  }))

  new ResizeObserver(measure).observe(stage)
  measure()
  setActive(0)
})()
