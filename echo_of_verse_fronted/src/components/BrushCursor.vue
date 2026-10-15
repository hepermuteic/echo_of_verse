<script setup lang="ts">
// 毛笔光标 + 短暂墨痕。光标尺寸随舞台缩放，保持与界面等比。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ scale: number; dark: boolean }>()
const cv = ref<HTMLCanvasElement>()
const brush = ref<HTMLElement>()
const shown = ref(false)
const down = ref(false)

type P = { x: number; y: number; t: number; w: number }
const pts: P[] = []
const LIFE = 1400
let raf = 0, last: P | null = null, dpr = 1, W = 0, H = 0
let ctx: CanvasRenderingContext2D | null = null
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

function resize() {
  dpr = Math.min(devicePixelRatio || 1, 2)
  W = innerWidth; H = innerHeight
  const c = cv.value!
  c.width = W * dpr; c.height = H * dpr
  ctx = c.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function move(e: PointerEvent) {
  shown.value = true
  brush.value!.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`
  if (reduce) return
  const now = performance.now()
  if (last) {
    const d = Math.hypot(e.clientX - last.x, e.clientY - last.y)
    // 速度越快笔画越细，模拟飞白；静止点自然不产生痕迹
    const w = Math.max(2, Math.min(15, 17 - d * 0.55)) * props.scale
    const prev = last
    const n = Math.max(1, Math.ceil(d / 6))
    for (let i = 1; i <= n; i++) {
      const k = i / n
      pts.push({ x: prev.x + (e.clientX - prev.x) * k, y: prev.y + (e.clientY - prev.y) * k, t: now, w: prev.w + (w - prev.w) * k })
    }
    last = { x: e.clientX, y: e.clientY, t: now, w }
  } else last = { x: e.clientX, y: e.clientY, t: now, w: 6 * props.scale }
  if (!raf) raf = requestAnimationFrame(draw)
}

function draw() {
  const c = ctx!
  const now = performance.now()
  c.clearRect(0, 0, W, H)
  while (pts.length && now - pts[0].t > LIFE) pts.shift()
  const rgb = props.dark ? '214,226,230' : '37,42,45'
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i]
    if (b.t - a.t > 80) continue // 断笔
    const age = (now - b.t) / LIFE
    const alpha = Math.pow(1 - age, 1.6) * (props.dark ? 0.5 : 0.42)
    c.strokeStyle = `rgba(${rgb},${alpha})`
    c.lineWidth = b.w * (1 + age * 0.35) // 墨向外洇开
    c.lineCap = 'round'
    c.beginPath(); c.moveTo(a.x, a.y); c.lineTo(b.x, b.y); c.stroke()
  }
  if (pts.length) raf = requestAnimationFrame(draw)
  else { raf = 0; last = null }
}

const leave = () => { shown.value = false; last = null }
const dn = () => (down.value = true)
const up = () => (down.value = false)

onMounted(() => {
  resize()
  addEventListener('resize', resize)
  addEventListener('pointermove', move)
  addEventListener('pointerdown', dn)
  addEventListener('pointerup', up)
  document.documentElement.addEventListener('mouseleave', leave)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  removeEventListener('resize', resize)
  removeEventListener('pointermove', move)
  removeEventListener('pointerdown', dn)
  removeEventListener('pointerup', up)
  document.documentElement.removeEventListener('mouseleave', leave)
})
watch(() => props.dark, () => {})
</script>

<template>
  <canvas ref="cv" class="trail" aria-hidden="true" />
  <div ref="brush" class="brush-cursor" :class="{ shown, down }" aria-hidden="true">
    <svg :style="{ width: 72 * scale + 'px', height: 72 * scale + 'px', margin: `${-75.7 * scale}px 0 0 ${5.25 * scale}px` }" viewBox="0 0 72 72">
      <defs>
        <linearGradient id="bamboo" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#8a6a43" /><stop offset=".5" stop-color="#c9a56f" /><stop offset="1" stop-color="#6e5232" />
        </linearGradient>
      </defs>
      <!-- 笔杆：从笔尖(4,68)向右上延伸 -->
      <g transform="rotate(-42 4 68)">
        <rect x="4" y="64" width="62" height="7" rx="3.5" fill="url(#bamboo)" stroke="#3b2a18" stroke-width=".8" />
        <rect x="60" y="64" width="6" height="7" rx="3" fill="#a84437" />
        <!-- 笔头：饱墨 -->
        <path d="M-8 67.5 C4 60 18 62 26 64 L26 71 C18 73 4 75 -8 67.5 Z" fill="#252a2d" />
        <path d="M18 64 L28 64 L28 71 L18 71 Z" fill="#d8ccb4" opacity=".0" />
        <path d="M24 63.5 h5 v8 h-5 z" fill="#3a3f43" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.trail { position: fixed; inset: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 998; }
.brush-cursor {
  position: fixed; left: 0; top: 0; z-index: 999; pointer-events: none; opacity: 0; transition: opacity .2s;
  will-change: transform;
}
.brush-cursor.shown { opacity: 1; }
.brush-cursor svg { display: block; overflow: visible; filter: drop-shadow(1px 2px 1.5px rgba(0,0,0,.28)); transition: transform .12s; transform-origin: 0 100%; }
.brush-cursor.down svg { transform: rotate(6deg) scale(.94); }
</style>
