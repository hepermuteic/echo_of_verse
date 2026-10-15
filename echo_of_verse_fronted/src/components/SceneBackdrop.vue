<script setup lang="ts">
/**
 * 场所背板 · 分层视差 + 墨气着色器
 *
 * 首页之外各页原先只有一道米白渐变，读不出「身在何处」。这里给每页一个场所：
 *   远 — 场所底图，向后推、随指针反向微移，叠一层极缓推拉；
 *   中 — InkAtmos 墨气（雾 / 水晕），是「空间厚度」的主要来源；
 *   近 — 可选的近景剪影（松枝、竹梢），向前探出，视差最强。
 * 三层用同一份指针驱动，凭位移量之差读出纵深。
 *
 * 视差走 rAF 缓动，把 --rx/--ry/--mx/--my 写在根元素上（CSS 变量赋值即样式重算，
 * 不经 Vue 响应式，页面不会每帧重渲染）。`prefers-reduced-motion` 下不挂 rAF，
 * 只保留静态构图。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import InkAtmos from './InkAtmos.vue'

const props = withDefaults(
  defineProps<{
    /** 场所底图 */
    far: string
    /** 近景剪影（可选） */
    near?: string
    /** 墨气色 */
    tint?: string
    /** 墨气浓度 */
    strength?: number
    /** 水纹强度，0 则只作雾 */
    ripple?: number
    /** 水流速度，>0 时墨气沿 x 平移 */
    flow?: number
    /** 墨气游移速度 */
    speed?: number
    /** 底图取景：cover 的对齐点 */
    position?: string
    /** 底图明暗是否调制墨气（暗处更浓） */
    modulate?: boolean
    /** 推拉动画幅度（0 关闭） */
    push?: number
    /** 视差总强度倍率 */
    depth?: number
    /** 宣纸罩：0–1，罩在场所上把调子拉回宣纸米白，保证正文可读。0 则不加 */
    veil?: number
    /** 指针视差：关掉则场所不随鼠标移动（推拉 / 呼吸 / 水纹等固有动画照常）。默认关 */
    parallax?: boolean
    /** 光斑：{ x, y, w, h, c } 以舞台像素定位的暖光 / 月光 */
    glows?: { x: number; y: number; w: number; h: number; c: string; d?: number }[]
  }>(),
  {
    tint: '#c4d6d8', strength: 0.3, ripple: 0, flow: 0, speed: 0.05,
    position: '50% 0%', modulate: false, push: 0.04, depth: 1, veil: 0, parallax: false,
  },
)

const root = ref<HTMLElement>()
const world = ref<HTMLElement>()
/** 传给 InkAtmos 的视差偏移（普通对象，非响应式） */
const drive = { x: 0, y: 0 }

let tx = 0, ty = 0, cx = 0, cy = 0, raf = 0
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

function onMove(e: PointerEvent) {
  const el = root.value
  if (!el) return
  const r = el.getBoundingClientRect()
  tx = ((e.clientX - r.left) / r.width - 0.5) * 2
  ty = ((e.clientY - r.top) / r.height - 0.5) * 2
}
function loop() {
  cx += (tx - cx) * 0.055
  cy += (ty - cy) * 0.055
  drive.x = cx
  drive.y = cy
  const w = world.value
  if (w) {
    w.style.setProperty('--rx', (-cy * 1.5).toFixed(3) + 'deg')
    w.style.setProperty('--ry', (cx * 2.1).toFixed(3) + 'deg')
    w.style.setProperty('--mx', cx.toFixed(3))
    w.style.setProperty('--my', cy.toFixed(3))
  }
  raf = requestAnimationFrame(loop)
}
onMounted(() => {
  // 只有开了视差才挂指针与 rAF；否则一帧都不跑，场所完全随鼠标不动
  if (!props.parallax || reduce) return
  addEventListener('pointermove', onMove)
  raf = requestAnimationFrame(loop)
})
onBeforeUnmount(() => { removeEventListener('pointermove', onMove); cancelAnimationFrame(raf) })
</script>

<template>
  <div ref="root" class="scene" :style="{ '--depth': depth, '--push': push }">
    <div class="persp">
      <div ref="world" class="world">
        <!-- 远：场所底图 -->
        <div class="layer far">
          <img class="art" :src="far" :style="{ objectPosition: position }" alt="" />
        </div>

        <!-- 光斑：与底图同步缓移，screen 混合读出亮处 -->
        <div v-if="glows?.length" class="layer glow">
          <span
            v-for="(g, i) in glows" :key="i"
            :style="{
              left: g.x + 'px', top: g.y + 'px', width: g.w + 'px', height: g.h + 'px',
              marginLeft: -g.w / 2 + 'px', marginTop: -g.h / 2 + 'px',
              background: `radial-gradient(ellipse, ${g.c}, transparent 68%)`,
              animationDuration: (g.d ?? 6) + 's',
            }"
          />
        </div>

        <!-- 中：墨气 -->
        <div class="layer mid">
          <InkAtmos
            :tint="tint" :strength="strength" :ripple="ripple" :flow="flow"
            :speed="speed" :drive="drive" :src="modulate ? far : ''"
          />
        </div>

        <!-- 近：剪影 -->
        <div v-if="near" class="layer near"><img :src="near" alt="" /></div>
      </div>
    </div>

    <!-- 宣纸罩：定在视口、不带透视，把场所的调子收敛回米白；正文浮于其上 -->
    <div v-if="veil > 0" class="veil" :style="{ opacity: veil }" />

    <slot />
  </div>
</template>

<style scoped>
/* 自带层叠上下文：`.scene` 无 z-index 时不算上下文，其内部（含宣纸罩）会拿去和页面同级
   元素比 z-index，罩层会压到正文之上。给 z-index:0 把它关起来，内部层序便只在本组件内有效。 */
.scene { position: absolute; inset: 0; overflow: hidden; z-index: 0; }
/* 罩层只叠在场所的三层之上，不带 z-index，靠 DOM 顺序落在 .persp 之后 */
.veil {
  position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(160deg, #f3ebdd 0%, rgba(243, 235, 221, .88) 46%, #f3ebdd 100%);
}
.persp { position: absolute; inset: 0; perspective: 1500px; perspective-origin: 58% 46%; }
.world {
  --rx: 0deg; --ry: 0deg; --mx: 0; --my: 0;
  position: absolute; inset: 0; transform-style: preserve-3d;
  transform: rotateX(var(--rx)) rotateY(var(--ry));
}
.layer { position: absolute; inset: 0; transform-style: preserve-3d; pointer-events: none; }

/* 远景：向后推，并放大补偿透视缩小 */
.far { transform: translateZ(-170px) scale(1.12) translate(calc(var(--mx) * -13px * var(--depth)), calc(var(--my) * -7px * var(--depth))); }
.far .art { width: 100%; height: 100%; object-fit: cover; animation: push 34s ease-in-out infinite alternate; }
@keyframes push {
  from { transform: scale(1); }
  to { transform: scale(calc(1 + var(--push))) translateX(-8px); }
}

.glow { transform: translateZ(-160px) scale(1.12) translate(calc(var(--mx) * -13px * var(--depth)), calc(var(--my) * -7px * var(--depth))); }
.glow span { position: absolute; mix-blend-mode: screen; animation: breathe 7s ease-in-out infinite; }
@keyframes breathe { 0%, 100% { opacity: .78; } 50% { opacity: 1; } }

.mid { transform: translateZ(-30px) scale(1.03) translate(calc(var(--mx) * -26px * var(--depth)), calc(var(--my) * -13px * var(--depth))); }

.near { transform: translateZ(150px) translate(calc(var(--mx) * -66px * var(--depth)), calc(var(--my) * -32px * var(--depth))); }
.near img { position: absolute; right: -170px; top: -140px; width: 1080px; opacity: .9; transform-origin: 90% 5%; animation: sway 11s ease-in-out infinite alternate; filter: drop-shadow(0 6px 10px rgba(10, 20, 26, .16)); }
@keyframes sway { from { transform: rotate(-.8deg); } to { transform: rotate(1deg); } }
</style>
