<script setup lang="ts">
import { computed } from 'vue'
import { go, params } from '../router'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import scene from '../assets/art/scene.png'
import { actsOf, allLines, poemById } from '../data/poems'
import { slots, write } from '../store/save'

/**
 * 诗境暂歇。三态由存档的 `lineIndex` 推导：之前已体验、等于为当前、之后为后续。
 * 存档位由 `#/pause?slot=<n>` 传入。
 */

const slot = computed(() => {
  const n = Number(params.value.slot)
  return Number.isInteger(n) && n >= 0 && n < slots.value.length ? n : null
})
const save = computed(() => (slot.value !== null ? slots.value[slot.value] : null))
const poem = computed(() => poemById(save.value?.poemId))
const lines = computed(() => (poem.value ? allLines(poem.value) : []))
const idx = computed(() => save.value?.lineIndex ?? 0)
const acts = computed(() => (poem.value ? actsOf(poem.value) : []))
const actName = computed(() => acts.value[save.value?.act ?? 0]?.t ?? '')

type St = 'done' | 'now' | 'next'
/** lineIndex == lines.length 表示全部走完，此时无「当前」句 */
const stateOf = (i: number): St => (i < idx.value ? 'done' : i === idx.value ? 'now' : 'next')
const label: Record<St, string> = { done: '已体验', now: '当前', next: '后续' }

const firstImagery = computed(() => poem.value?.imagery?.[0])

function onMenu(m: string) {
  if (m === '继续诗境') go('hud', slot.value !== null ? `slot=${slot.value}&p=${poem.value?.id ?? ''}` : '')
  else if (m === '当前诗篇') { if (poem.value) go('poem', 'p=' + poem.value.id) }
  else if (m === '重新开始本幕') {
    if (slot.value === null || !poem.value) return
    // 回到本幕首行：按幕均分估算该幕起点
    const per = Math.max(1, Math.ceil(lines.value.length / Math.max(1, acts.value.length)))
    const start = Math.min(per * (save.value?.act ?? 0), Math.max(0, lines.value.length - 1))
    write(slot.value, { poemId: poem.value.id, lineIndex: start, act: save.value?.act ?? 0 })
    go('hud', `slot=${slot.value}&p=${poem.value.id}`)
  } else if (m === '返回首页') go('home')
}

const menu = ['继续诗境', '当前诗篇', '意象解读', '重新开始本幕', '返回首页']
</script>

<template>
  <div class="pause" :class="{ tight: !firstImagery }">
    <!-- 场所：定格的江天（与局内同一张底图），开卷停止后画面仍在，只是慢下来 -->
    <SceneBackdrop
      :far="scene" position="50% 55%" tint="#93aab0" :strength="0.34" :ripple="0.22"
      :flow="0.05" :speed="0.045" :push="0.02" :depth="0.45" :modulate="true" :parallax="true"
      :glows="[{ x: 1330, y: 190, w: 400, h: 400, c: 'rgba(255,244,214,.28)', d: 9 }]"
    />
    <div class="fog" />

    <h2 class="title t-title">诗境暂歇</h2>
    <p v-if="poem" class="t-aux nowplaying">{{ poem.title }} · {{ poem.author }}<template v-if="actName"> · {{ actName }}</template></p>

    <nav class="left">
      <button
        v-for="(m, i) in menu" :key="m" class="menu-item" :class="{ active: i === 2 && !!firstImagery }"
        :disabled="m === '意象解读' && !firstImagery"
        @click="onMenu(m)"
      >
        <span class="seal sm" />{{ m }}
        <small v-if="m === '意象解读' && !firstImagery">此篇未录</small>
      </button>
    </nav>

    <!-- 意象解读：仅当该篇录有意象时才渲染 -->
    <aside v-if="firstImagery" class="note">
      <p class="tag t-aux">意象解读 · {{ firstImagery.name }}</p>
      <h3 class="q">为何以此入诗？</h3>
      <p class="orig"><span class="seal sm" />「{{ firstImagery.line }}」</p>
      <p class="body">{{ firstImagery.note }}</p>
      <p class="t-aux src-line">来源　{{ firstImagery.src }}</p>
      <p class="game t-aux"><b>游戏创作</b>　{{ firstImagery.clip }}</p>
    </aside>

    <section class="right" :class="{ wide: !firstImagery }">
      <h3 class="rt t-aux">{{ poem?.title ?? '进度' }} · 进度</h3>
      <ul v-if="lines.length">
        <li v-for="(l, i) in lines" :key="i" :class="stateOf(i)">
          <span class="mark">
            <i v-if="stateOf(i) === 'done'" class="gold" />
            <span v-else-if="stateOf(i) === 'now'" class="seal sm" />
            <i v-else class="hollow" />
          </span>
          <span class="txt">{{ l }}</span>
          <em>{{ label[stateOf(i)] }}</em>
        </li>
      </ul>
      <p v-else class="t-aux nodata">暂无进行中的诗境</p>

      <ol v-if="acts.length" class="actstrip">
        <li v-for="(a, i) in acts" :key="a.t" :class="{ on: i === (save?.act ?? 0) }">
          <span class="num t-brush">{{ a.n }}</span>{{ a.t }}
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.pause { position: absolute; inset: 0; background: #14212a; }
/* 分层：场所背板（首位）→ 雾幕（z1）→ 正文（z2）。雾幕压在背板上把画面「定住」 */
.fog { position: absolute; inset: 0; z-index: 1; background: linear-gradient(90deg, rgba(243,235,221,.82), rgba(243,235,221,.7) 55%, rgba(243,235,221,.86)); }
.pause > .title, .pause > .nowplaying, .pause > .left, .pause > .note, .pause > .right { position: absolute; z-index: 2; }
.title { position: absolute; left: 96px; top: 64px; font-size: 44px; }
.nowplaying { position: absolute; left: 96px; top: 126px; letter-spacing: .16em; }
.left { position: absolute; left: 96px; top: 220px; display: flex; flex-direction: column; gap: 8px; }
.left .menu-item { font-size: 28px; }
.left .menu-item:disabled { opacity: .4; cursor: default; }
.left .menu-item:disabled::before { opacity: 0; }
.left small { font-size: 18px; color: var(--ink-faint); margin-left: 6px; }

.note {
  position: absolute; left: 600px; top: 190px; width: 560px; padding: 32px 36px; background: #f6efe0;
  border: 1px solid var(--line); border-top: 3px solid var(--cinnabar);
}
.tag { letter-spacing: .3em; color: var(--stone); font-weight: 600; }
.q { font-size: 30px; margin: 10px 0 14px; letter-spacing: .06em; }
.orig { padding: 10px 0; display: flex; gap: 12px; align-items: center; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); font-family: var(--f-brush); font-size: 26px; }
.body { font-size: 22px; line-height: 1.85; margin: 14px 0; }
.src-line { color: var(--ink-faint); }
.game { margin-top: 18px; padding: 10px 14px; background: rgba(85,123,131,.14); font-size: 19px; }
.game b { color: var(--stone); margin-right: 8px; }

.right { position: absolute; right: 96px; top: 160px; bottom: 80px; width: 560px; }
/* 无意象时右栏左移收拢，避免中部空出一大块 */
.right.wide { left: 600px; width: auto; top: 220px; }
.rt { letter-spacing: .3em; margin-bottom: 16px; }
.right ul { border-left: 1.5px solid var(--line); }
.right li { display: grid; grid-template-columns: 40px 1fr auto; align-items: center; gap: 4px; padding: 12px 0; font-size: 22px; line-height: 1.5; }
.right li em { font-style: normal; font-size: 18px; letter-spacing: .1em; color: var(--ink-faint); }
.right li.done em { color: #8c733f; }
.right li.now { background: linear-gradient(90deg, rgba(168,68,55,.1), transparent); font-weight: 700; }
.right li.now em { color: var(--cinnabar); font-weight: 700; }
.right li.next .txt { color: var(--ink-faint); }
.mark { display: grid; place-items: center; margin-left: -8px; }
.gold { width: 12px; height: 12px; border-radius: 50%; background: var(--gold); }
.hollow { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--ink-faint); background: var(--paper); }
.nodata { padding-left: 16px; }

.actstrip { display: flex; gap: 28px; margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--line); }
.actstrip li { display: flex; align-items: center; gap: 10px; font-size: 20px; color: var(--ink-faint); letter-spacing: .12em; }
.actstrip li.on { color: var(--cinnabar); font-weight: 700; }
.num { font-size: 30px; }
</style>
