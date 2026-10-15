<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { go } from '../router'
import InkMist from '../components/InkMist.vue'
import { latest, slots, resolvePoem } from '../store/save'
import homeArt from '../assets/art/home.png'
import branch from '../assets/art/branch.png'

// 有存档则「开启诗境」变为「继续诗境」，直接回到最近一卷
const recent = computed(() => latest())
const recentPoem = computed(() => (recent.value < 0 ? undefined : resolvePoem(recent.value)))
const hasSave = computed(() => recent.value >= 0 && !!slots.value[recent.value])

function onPrimary() {
  if (hasSave.value) go('hud', `slot=${recent.value}`)
  else go('select')
}

const menu: { label: string; to: 'scroll' | 'collection' | 'settings' }[] = [
  { label: '诗篇卷轴', to: 'scroll' },
  { label: '诗心拾遗', to: 'collection' },
  { label: '系统设置', to: 'settings' },
]

// 3D 视差：指针 → 目标倾角，逐帧缓动（含惯性）
const world = ref<HTMLElement>()
const root = ref<HTMLElement>()
let tx = 0, ty = 0, cx = 0, cy = 0, raf = 0
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

function onMove(e: PointerEvent) {
  const r = root.value!.getBoundingClientRect()
  tx = ((e.clientX - r.left) / r.width - 0.5) * 2
  ty = ((e.clientY - r.top) / r.height - 0.5) * 2
}
function loop() {
  cx += (tx - cx) * 0.06
  cy += (ty - cy) * 0.06
  const w = world.value
  if (w) {
    w.style.setProperty('--rx', (-cy * 2.6).toFixed(3) + 'deg')
    w.style.setProperty('--ry', (cx * 3.6).toFixed(3) + 'deg')
    w.style.setProperty('--mx', cx.toFixed(3))
    w.style.setProperty('--my', cy.toFixed(3))
  }
  raf = requestAnimationFrame(loop)
}
onMounted(() => {
  if (reduce) return
  addEventListener('pointermove', onMove)
  raf = requestAnimationFrame(loop)
})
onBeforeUnmount(() => { removeEventListener('pointermove', onMove); cancelAnimationFrame(raf) })

// 萤火 / 墨点粒子（纯 CSS 动画，位置固定种子）
const motes = Array.from({ length: 16 }, (_, i) => {
  const r = (n: number) => { const x = Math.sin(i * 91.7 + n * 13.3) * 10000; return x - Math.floor(x) }
  return { x: 900 + r(1) * 960, y: 380 + r(2) * 560, s: 3 + r(3) * 4, d: 7 + r(4) * 8, de: -r(5) * 12 }
})
</script>

<template>
  <div ref="root" class="home paper-grain">
    <!-- 3D 场景 -->
    <div class="persp">
      <div ref="world" class="world">
        <div class="layer far"><img class="art" :src="homeArt" alt="" /></div>
        <div class="layer moonglow" />
        <div class="layer door" />
        <div class="layer lake">
          <svg width="0" height="0" aria-hidden="true">
            <filter id="ripple" x="0" y="0" width="100%" height="100%">
              <feTurbulence type="fractalNoise" baseFrequency="0.004 0.045" numOctaves="2" seed="3" result="n">
                <animate attributeName="baseFrequency" dur="14s" values="0.004 0.045;0.007 0.06;0.004 0.045" repeatCount="indefinite" />
              </feTurbulence>
              <feDisplacementMap in="SourceGraphic" in2="n" scale="14" />
            </filter>
          </svg>
        </div>
        <div class="layer mid"><InkMist tint="#c4d6d8" :strength="0.34" :speed="0.05" /></div>
        <div class="layer motes">
          <i v-for="(m, k) in motes" :key="k" :style="{ left: m.x + 'px', top: m.y + 'px', width: m.s + 'px', height: m.s + 'px', animationDuration: m.d + 's', animationDelay: m.de + 's' }" />
        </div>
        <div class="layer near"><img :src="branch" alt="" /></div>
      </div>
    </div>

    <div class="fade-left" />

    <header class="brand rise">
      <h1 class="t-brush">诗画入境</h1>
      <p class="t-en en">Echoes of Verse</p>
      <span class="rule" />
      <p class="t-aux sub">唐宋名篇 · 十二个诗境</p>
    </header>

    <nav class="menu" aria-label="主菜单">
      <button
        class="menu-item rise" :class="{ active: true }" style="animation-delay:.25s"
        @click="onPrimary()"
      >
        <span class="seal sm" />{{ hasSave ? '继续诗境' : '开启诗境' }}
        <small v-if="recentPoem">{{ recentPoem.title }} · {{ recentPoem.author }}</small>
      </button>
      <button
        v-for="(m, i) in menu" :key="m.label" class="menu-item rise"
        :style="{ animationDelay: 0.35 + i * 0.1 + 's' }"
        @click="go(m.to)"
      >
        <span class="seal sm" />{{ m.label }}
      </button>
      <button class="redo rise" style="animation-delay:.7s" @click="go('select')">
        <span class="t-aux">{{ hasSave ? '另择诗篇' : '从诗篇卷轴续读' }}</span>
      </button>
    </nav>

    <footer class="foot rise" style="animation-delay:.8s">
      <button class="t-aux link">关于与致谢</button>
      <span class="dot" />
      <button class="t-aux link">退出</button>
    </footer>
  </div>
</template>

<style scoped>
.home { position: absolute; inset: 0; background: #f3ebdd; overflow: hidden; }
.persp { position: absolute; inset: 0; perspective: 1500px; perspective-origin: 62% 45%; }
.world {
  --rx: 0deg; --ry: 0deg; --mx: 0; --my: 0;
  position: absolute; inset: 0; transform-style: preserve-3d;
  transform: rotateX(var(--rx)) rotateY(var(--ry));
  animation: enter 2.4s cubic-bezier(.2,.7,.2,1) both;
}
@keyframes enter { from { opacity: 0; transform: scale(1.06) rotateY(-3deg); } to { opacity: 1; } }
.layer { position: absolute; inset: 0; transform-style: preserve-3d; pointer-events: none; }

/* 远景：向后推并放大，补偿透视缩小；叠加极缓呼吸式推拉 */
.far { transform: translateZ(-160px) scale(1.1) translate(calc(var(--mx) * -14px), calc(var(--my) * -8px)); }
.far .art { width: 100%; height: 100%; object-fit: cover; object-position: 50% 0%; animation: push 26s ease-in-out infinite alternate; }
@keyframes push { from { transform: scale(1); } to { transform: scale(1.045) translateX(-10px); } }

/* 月晕：对准画面中月亮 (≈76%, 17%) */
.moonglow {
  transform: translateZ(-150px) scale(1.1) translate(calc(var(--mx) * -14px), calc(var(--my) * -8px));
}
.moonglow::before {
  content: ''; position: absolute; left: 1459px; top: 226px; width: 520px; height: 520px; margin: -260px 0 0 -260px;
  background: radial-gradient(circle, rgba(255,246,218,.5), rgba(255,240,200,.16) 40%, transparent 68%);
  mix-blend-mode: screen; animation: breathe 7s ease-in-out infinite;
}
/* 门灯：对准画面暖光中心 (≈66%, 79%) */
.door { transform: translateZ(-150px) scale(1.1) translate(calc(var(--mx) * -14px), calc(var(--my) * -8px)); }
.door::before {
  content: ''; position: absolute; left: 1267px; top: 1007px; width: 420px; height: 300px; margin: -150px 0 0 -210px;
  background: radial-gradient(ellipse, rgba(255,222,150,.42), transparent 68%);
  mix-blend-mode: screen; animation: breathe 5.2s ease-in-out infinite;
}
.lake { display: none; }

.mid { transform: translateZ(-30px) scale(1.03) translate(calc(var(--mx) * -26px), calc(var(--my) * -14px)); mix-blend-mode: screen; opacity: .65; }
.mid :deep(canvas) { clip-path: inset(0 0 0 38%); }

.motes { transform: translateZ(10px) translate(calc(var(--mx) * -40px), calc(var(--my) * -20px)); }
.motes i {
  position: absolute; border-radius: 50%; background: #ffe9b0; box-shadow: 0 0 10px 3px rgba(255,226,150,.55);
  opacity: 0; animation: mote linear infinite;
}
@keyframes mote {
  0% { opacity: 0; transform: translate(0, 0); }
  20% { opacity: .85; }
  80% { opacity: .55; }
  100% { opacity: 0; transform: translate(60px, -140px); }
}

/* 近景：松枝向前探出，视差最强 */
.near { transform: translateZ(140px) translate(calc(var(--mx) * -70px), calc(var(--my) * -36px)); }
.near img { position: absolute; right: -180px; top: -150px; width: 1150px; opacity: .92; transform-origin: 90% 5%; animation: sway 9s ease-in-out infinite alternate; filter: drop-shadow(0 6px 10px rgba(10,20,26,.18)); }
@keyframes sway { from { transform: rotate(-.9deg); } to { transform: rotate(1.1deg); } }

.fade-left {
  position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(90deg, #f3ebdd 0%, #f3ebdd 24%, rgba(243,235,221,.92) 33%, rgba(243,235,221,.5) 43%, rgba(243,235,221,0) 56%);
}

.brand { position: absolute; left: 96px; top: 64px; }
.brand h1 { font-size: 80px; line-height: 1.1; color: var(--ink); }
.en { font-size: 30px; color: var(--ink-soft); margin-top: 6px; }
.rule { display: block; width: 120px; height: 2px; margin: 18px 0 12px; background: linear-gradient(90deg, var(--cinnabar), transparent); }

.menu { position: absolute; left: 96px; top: 372px; display: flex; flex-direction: column; gap: 14px; }
.redo { margin: 6px 0 0 28px; text-align: left; }
.redo:hover .t-aux { color: var(--cinnabar); }

.foot { position: absolute; left: 96px; bottom: 64px; display: flex; align-items: center; gap: 22px; }
.link { padding: 8px 4px; color: var(--ink-soft); border-bottom: 1px solid transparent; }
.link:hover { color: var(--ink); border-color: var(--cinnabar); }
.dot { width: 4px; height: 4px; border-radius: 50%; background: var(--ink-faint); }
</style>
