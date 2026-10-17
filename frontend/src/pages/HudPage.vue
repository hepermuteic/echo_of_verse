<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import scene from '../assets/art/scene.png'
import { go, params } from '../router'
import { allLines, poemById } from '../data/poems'
import { claimSlot, slots, write } from '../store/save'

/**
 * 局内。进度按「句」推进：每举一次杯，当前句前进一句，并即时写入存档位。
 * 存档位由 `#/hud?slot=<n>&p=<id>` 传入；直接访问无参时认领一个空位。
 */
const mono = computed(() => 'mono' in params.value)

const slot = computed(() => {
  const n = Number(params.value.slot)
  return Number.isInteger(n) && n >= 0 && n < slots.value.length ? n : null
})
const poem = computed(() => poemById(params.value.p) ?? (slot.value !== null ? poemById(slots.value[slot.value]?.poemId) : undefined))
const lines = computed(() => (poem.value ? allLines(poem.value) : []))
const idx = computed(() => {
  const s = slot.value !== null ? slots.value[slot.value] : null
  if (!s || !poem.value || s.poemId !== poem.value.id) return 0
  return Math.min(s.lineIndex, Math.max(0, lines.value.length - 1))
})
const current = computed(() => lines.value[idx.value] ?? '明月几时有，把酒问青天。')
const finished = computed(() => lines.value.length > 0 && idx.value >= lines.value.length - 1)

/** 举杯：推进一句并落盘 */
function raise() {
  const p = poem.value
  if (!p) return
  const s = slot.value ?? claimSlot()
  const next = Math.min(idx.value + 1, lines.value.length - 1)
  const act = Math.min(2, Math.floor((next / Math.max(1, lines.value.length)) * 3))
  write(s, { poemId: p.id, lineIndex: next, act })
  if (next >= lines.value.length - 1) go('ending', `slot=${s}`)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') go('pause', slot.value !== null ? `slot=${slot.value}` : '')
  if (e.key === 'e' || e.key === 'E') raise()
}

onMounted(() => addEventListener('keydown', onKey))
onBeforeUnmount(() => removeEventListener('keydown', onKey))
</script>

<template>
  <div class="hud">
    <!-- 场所：夜宴水岸。原先是一张平铺的平面图，现拆成远（江天）/中（雾气与水纹）/近三层，
         随指针微动读出纵深；涟漪层落在水面一带 -->
    <SceneBackdrop
      :far="scene" position="50% 58%" tint="#9fb8bd" :strength="0.30" :ripple="0.34"
      :flow="0.06" :speed="0.05" :push="0.03" :depth="0.8" :modulate="true" :parallax="true"
      :glows="[
        { x: 1330, y: 200, w: 480, h: 480, c: 'rgba(255,246,218,.30)', d: 7 },
        { x: 1240, y: 900, w: 400, h: 280, c: 'rgba(255,222,150,.26)', d: 5.4 },
      ]"
    />
    <div class="vignette" />

    <button class="pausehint t-aux" @click="go('pause', slot !== null ? `slot=${slot}` : '')">ESC 暂停</button>

    <!-- 空间诗句：随进度换句，避开月光与目标 -->
    <p v-if="!mono" class="spatial t-brush fade" :key="current">{{ current }}</p>

    <!-- 交互目标：酒杯 -->
    <button class="target" :aria-label="finished ? '回望' : '举杯'" @click="raise()">
      <span class="ring" />
      <span class="prompt"><kbd>E</kbd> {{ finished ? '回望此行' : '举杯' }}</span>
    </button>

    <!-- 进度：第 n / m 句 -->
    <p v-if="poem" class="progress t-aux">{{ poem.title }} · {{ Math.min(idx + 1, lines.length) }} / {{ lines.length }}</p>

    <!-- 心理独白与空间诗句错峰：URL 带 ?mono 时显示独白、隐藏空间诗句 -->
    <p v-if="mono" class="mono fade">今夜这一盏，不知该敬向何处。</p>
  </div>
</template>

<style scoped>
.hud { position: absolute; inset: 0; background: #14212a; }
/* 分层：场所背板（首位）→ 暗角（z1）→ HUD 诸元素（z2）。
   背板铺在最下即是最暗的一层，其上的暗角只需压两边、不必再压中心，
   否则整幅会闷掉——故暗角只保留四周收边与下缘渐隐。 */
.vignette { position: absolute; inset: 0; z-index: 1; background: radial-gradient(ellipse at 55% 45%, transparent 42%, rgba(8,16,22,.34) 100%), linear-gradient(0deg, rgba(8,16,22,.5), transparent 24%); }
.hud > .pausehint, .hud > .spatial, .hud > .target, .hud > .progress, .hud > .mono { z-index: 2; }
.pausehint { position: absolute; left: 96px; top: 64px; color: rgba(243,235,221,.8); font-size: 20px; letter-spacing: .2em; text-shadow: 0 1px 6px rgba(0,0,0,.6); }
.pausehint:hover { color: #f3ebdd; }
.spatial { position: absolute; left: 96px; top: 190px; font-size: 56px; color: #f3ebdd; text-shadow: 0 2px 14px rgba(8,16,22,.8); line-height: 1.3; width: 560px; }
.progress { position: absolute; right: 96px; bottom: 64px; color: rgba(243,235,221,.7); letter-spacing: .18em; text-shadow: 0 1px 6px rgba(0,0,0,.6); }

.target { position: absolute; left: 860px; top: 760px; width: 48px; height: 48px; }
.ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid rgba(243,235,221,.85);
  background: radial-gradient(circle, rgba(243,235,221,.12), transparent 70%);
  box-shadow: 0 0 0 5px rgba(37,42,45,.28), 0 0 18px rgba(243,235,221,.25);
  animation: ringPulse 3.2s ease-in-out infinite;
}
.target:hover .ring { border-color: #fff; box-shadow: 0 0 0 5px rgba(37,42,45,.28), 0 0 26px rgba(243,235,221,.5); }
.prompt { position: absolute; left: 50%; top: 66px; transform: translateX(-50%); white-space: nowrap; font-size: 22px; color: #f3ebdd; letter-spacing: .14em; text-shadow: 0 1px 8px rgba(0,0,0,.8); display: flex; align-items: center; gap: 10px; }
kbd { font: 600 18px var(--f-en); font-variant-numeric: lining-nums;padding: 2px 9px; border: 1px solid rgba(243,235,221,.8); border-radius: 2px; background: rgba(36,55,70,.6); }

.mono { position: absolute; left: 50%; bottom: 64px; transform: translateX(-50%); font-size: 26px; letter-spacing: .2em; color: #efe6d2; padding: 12px 40px; background: linear-gradient(90deg, transparent, rgba(8,16,22,.55) 20%, rgba(8,16,22,.55) 80%, transparent); text-shadow: 0 1px 8px rgba(0,0,0,.7); }
</style>
