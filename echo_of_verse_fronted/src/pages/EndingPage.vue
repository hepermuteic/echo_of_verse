<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { go, params } from '../router'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import river from '../assets/art/bg-river.png'
import { ART, allLines, poemById } from '../data/poems'
import { slots, write } from '../store/save'

/**
 * 此行心迹。走完一首诗后显示；进度取自存档位 `#/ending?slot=<n>`。
 * 心迹节点按已体验的句数比例点亮，不再是假数据。
 */

const slot = computed(() => {
  const n = Number(params.value.slot)
  return Number.isInteger(n) && n >= 0 && n < slots.value.length ? n : null
})
const save = computed(() => (slot.value !== null ? slots.value[slot.value] : null))
const poem = computed(() => poemById(save.value?.poemId))
const lines = computed(() => (poem.value ? allLines(poem.value) : []))
const done = computed(() => save.value?.lineIndex ?? 0)

/** 心迹四站：按行程均分，已过者点亮 */
const stations = ['入境', '循句', '登临', '回望']
const reached = computed(() => {
  const t = Math.max(1, lines.value.length)
  const r = done.value / t
  return stations.map((_, i) => r >= i / (stations.length - 1) - 1e-6)
})

const lastVerse = computed(() => lines.value.at(-1) ?? '')
const poemArt = computed(() => (poem.value ? ART[poem.value.art] : ART.mist))
const imagery = computed(() => poem.value?.imagery ?? [])
const cards = computed(() => (imagery.value.length ? imagery.value.map((i) => ART[i.art]) : [poemArt.value]))
const selected = computed(() => (imagery.value[0]?.art ? ART[imagery.value[0].art] : poemArt.value))

const cards3 = computed(() => {
  const list = cards.value
  return list.length >= 3 ? list.slice(0, 3) : [...list, ...Array(3 - list.length).fill(poemArt.value)]
})

/** 进入心迹页即标记完成 */
onMounted(() => {
  if (slot.value !== null && poem.value) {
    write(slot.value, { poemId: poem.value.id, lineIndex: lines.value.length, act: 2 })
  }
})

/** 保存诗境卡：独立导出本行心迹，不改动进度 */
function saveCard() {
  const data = {
    poem: poem.value?.title,
    author: poem.value?.author,
    dynasty: poem.value?.dynasty,
    lines: done.value,
    total: lines.value.length,
    verse: lastVerse.value,
    at: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `诗境卡-${poem.value?.title ?? '诗篇'}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<template>
  <div class="end paper-grain">
    <!-- 场所：江天暮色。空舟停在右侧近处，寄语浮于左侧江天之上 -->
    <SceneBackdrop
      :far="river" position="58% 52%" tint="#aebac2" :strength="0.22" :veil="0.55"
      :ripple="0.42" :flow="0.07" :speed="0.04" :push="0.03" :depth="0.6" :modulate="true"
      :glows="[{ x: 1180, y: 300, w: 520, h: 360, c: 'rgba(255,240,206,.34)', d: 8 }]"
    />

    <h2 class="title t-title">此行心迹</h2>
    <p v-if="poem" class="t-aux nowplaying">{{ poem.title }} · {{ poem.author }} · {{ poem.dynasty }}</p>

    <!-- 淡墨连线 -->
    <svg class="trail" viewBox="0 0 1200 120" aria-hidden="true">
      <path d="M60 70 C240 20 300 110 450 62 S700 20 820 66 1000 100 1140 54" stroke="#252a2d" stroke-opacity=".35" stroke-width="2.5" fill="none" stroke-linecap="round" />
    </svg>
    <ol class="events">
      <li
        v-for="(e, i) in stations" :key="e"
        :class="{ lit: reached[i] }"
        :style="{ left: 60 + i * 360 + 'px', top: (i % 2 ? 78 : 44) + 'px' }"
      >
        <i class="node" /><span>{{ e }}</span>
      </li>
    </ol>

    <main class="center rise">
      <p class="t-aux kicker">此行寄语</p>
      <p class="msg">
        <template v-if="poem">你已走完《{{ poem.title }}》的 {{ lines.length }} 句，共 {{ done }} 句留在卷上。</template>
        <template v-else>尚无走完的诗境，可先择一诗入境。</template>
      </p>
      <div class="rule"><span class="seal" /></div>
      <p v-if="lastVerse" class="verse t-brush">{{ lastVerse }}</p>
      <p v-if="imagery[0]" class="t-aux note">{{ imagery[0].note }}</p>
      <template v-if="poem">
        <details class="en">
          <summary class="t-aux">本篇信息</summary>
          <p class="t-aux src">题材　{{ poem.genre }}　·　体裁　{{ poem.form === 'ci' ? '词' : poem.form === 'qu' ? '曲' : '诗' }}</p>
          <p class="t-aux src">卷中句数　{{ lines.length }}（已体验 {{ done }}）</p>
        </details>
      </template>
    </main>

    <aside class="cards">
      <p class="t-aux">诗境卡</p>
      <div class="row">
        <img v-for="(c, i) in cards3" :key="i" :src="c" :class="{ pick: c === selected && i === 0 }" alt="" />
      </div>
    </aside>

    <footer class="actions">
      <button class="btn primary" @click="saveCard()"><span class="seal sm" />保存诗境卡</button>
      <button class="btn ghost" @click="go('select')">另择诗篇</button>
      <button class="btn ghost" @click="go('scroll')">诗篇卷轴</button>
      <button class="btn ghost" @click="go('home')">返回首页</button>
    </footer>
  </div>
</template>

<style scoped>
.end { position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 40%, #f7f0e1, #efe5d1); }
/* 场所背板为首位绝对定位子元素；页首 / 心迹 / 诗境卡 / 页脚皆绝对定位，DOM 顺序即层序，纸纹层最上 */
.title { position: absolute; left: 96px; top: 64px; font-size: 44px; }
.nowplaying { position: absolute; left: 96px; top: 124px; letter-spacing: .16em; }
.trail { position: absolute; left: 96px; top: 168px; width: 1200px; height: 120px; }
.events { position: absolute; left: 96px; top: 168px; width: 1200px; height: 120px; }
.events li { position: absolute; display: flex; flex-direction: column; align-items: center; gap: 8px; font-size: 22px; font-weight: 600; letter-spacing: .14em; transform: translateX(-30px); color: var(--ink-faint); }
.events li.lit { color: var(--ink); }
.events li:nth-child(odd) { transform: translate(-30px, -34px); }
.events li:nth-child(even) { transform: translate(-30px, 10px); }
.node { order: 1; width: 14px; height: 14px; border-radius: 50%; background: var(--paper); box-shadow: 0 0 0 4px rgba(123,128,130,.18); border: 1.5px solid var(--ink-faint); }
.events li.lit .node { background: var(--gold); border-color: var(--gold); box-shadow: 0 0 0 4px rgba(185,154,97,.25); }
.events li span { order: 0; }
.events li:nth-child(even) .node { order: 0; }
.events li:nth-child(even) span { order: 1; }

.center { position: absolute; left: 96px; top: 350px; width: 960px; }
.kicker { letter-spacing: .5em; color: var(--cinnabar); font-weight: 600; }
.msg { font-size: 28px; line-height: 2; margin-top: 12px; letter-spacing: .06em; }
.rule { display: flex; align-items: center; gap: 16px; margin: 28px 0 14px; }
.rule::before { content: ''; flex: 0 0 120px; height: 1px; background: var(--line); }
.rule::after { content: ''; flex: 1; height: 1px; background: var(--line); }
.verse { font-size: 64px; line-height: 1.3; color: var(--indigo); }
.note { margin-top: 10px; max-width: 800px; }
.en { margin-top: 12px; }
.en summary { cursor: pointer; display: inline-block; color: var(--stone); font-weight: 600; border-bottom: 1px solid var(--stone); }
.src { margin-top: 8px; }

.cards { position: absolute; right: 96px; top: 330px; width: 520px; }
.cards .row { display: flex; gap: 14px; margin-top: 12px; }
.cards img { width: 160px; height: 160px; object-fit: cover; border: 1px solid var(--line); padding: 5px; background: #fbf6ea; opacity: .85; }
.cards img.pick { opacity: 1; outline: 2px solid var(--cinnabar); outline-offset: 2px; transform: translateY(-6px); }

.actions { position: absolute; left: 96px; right: 96px; bottom: 64px; display: flex; gap: 24px; justify-content: flex-start; }
</style>
