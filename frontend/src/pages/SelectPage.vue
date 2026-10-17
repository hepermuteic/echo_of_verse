<script setup lang="ts">
import { computed, ref } from 'vue'
import { go } from '../router'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import corridor from '../assets/art/bg-corridor.png'
import { POEMS, totalLines, facets, type Dynasty, type Genre } from '../data/poems'

/**
 * 选诗页 · 书棚题名录。
 *
 * 版式取「签架」：一道木架横贯台上，十二枚签自架上垂落——竖排题名（马善政）
 * 居右，朝代·作者·题材以小字缀于左，签脚压一枚朱印编号。与诗篇页的「竹简」、
 * 诗心拾遗的「装裱立轴」合为三种古典形制，各不相犯。
 *
 * 三维（题材 / 作者 / 朝代）交叉筛选取交集，可任意清除。
 * 被筛掉的签条以淡墨留在原位，不移除、不重排——筛选过程本身可见。
 *
 * 筛选状态放在模块级：`App.vue` 以 `:key` 强制重挂载页面，
 * 若用组件内 ref，从诗篇页返回时条件会被清空。
 */

type Sel = { genre?: Genre; author?: string; dynasty?: Dynasty }
const sel = ref<Sel>({})

function pick<K extends keyof Sel>(key: K, v: NonNullable<Sel[K]>) {
  sel.value = { ...sel.value, [key]: sel.value[key] === v ? undefined : v }
}
function clearAll() { sel.value = {} }

const anyFilter = computed(() => Object.values(sel.value).some(Boolean))

function matches(p: (typeof POEMS)[number]) {
  const s = sel.value
  return (!s.genre || p.genre === s.genre)
    && (!s.author || p.author === s.author)
    && (!s.dynasty || p.dynasty === s.dynasty)
}

const shown = computed(() => POEMS.filter(matches))
/** 交叉筛选可能得到空集（如「明 + 边塞」），需有空态 */
const none = computed(() => anyFilter.value && shown.value.length === 0)
const activeFilters = computed(() => Object.entries(sel.value).filter(([, v]) => v))

/** 某条件项在其余两维已选的前提下是否还有结果 */
function reachable(key: keyof Sel, v: string): boolean {
  const s = { ...sel.value, [key]: v }
  return POEMS.some((p) =>
    (!s.genre || p.genre === s.genre)
    && (!s.author || p.author === s.author)
    && (!s.dynasty || p.dynasty === s.dynasty))
}

const CN = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二']
const cn = (n: number) => CN[n] ?? String(n)

const FORM = { ci: '词', qu: '曲', shi: '诗' } as const

/**
 * 悬停 / 获焦的签：题名录下缘的落款带据此显示该篇首句。
 * 只在仍然合于筛选条件时出——否则刚被筛掉的签会拖着一行字不放。
 */
const hovered = ref<string | null>(null)
const preview = computed(() => {
  const p = hovered.value ? POEMS.find((x) => x.id === hovered.value) : undefined
  return p && matches(p) ? p : undefined
})
/** 指针自 A 移到 B 时 leave 可能晚于 enter，故按 id 比对后再清，免得来回闪 */
const unhover = (id: string) => { if (hovered.value === id) hovered.value = null }

const bands = [
  { key: 'genre' as const, label: '题材', items: facets.genre },
  { key: 'author' as const, label: '作者', items: facets.author },
  { key: 'dynasty' as const, label: '朝代', items: facets.dynasty },
]
</script>

<template>
  <div class="sel paper-grain">
    <!-- 场所：夜园游廊。签架几占满幅，故底图取水与月那段（偏中上），
         露在架上缘与签与签的缝间，作「廊外有园」的一层 -->
    <SceneBackdrop
      :far="corridor" position="50% 42%" tint="#a9bcc4" :strength="0.26" :veil="0.6"
      :ripple="0.5" :speed="0.05" :push="0.035" :depth="0.7" :modulate="true"
      :glows="[{ x: 1330, y: 250, w: 420, h: 420, c: 'rgba(255,248,224,.34)', d: 8 }]"
    />

    <header class="top rise">
      <div>
        <h2 class="t-title title">题名录</h2>
        <p class="t-aux sub">十二篇诗，择一入境</p>
      </div>
      <p class="t-aux count">
        录 <b>{{ cn(POEMS.length) }}</b> 篇　合 <b :class="{ hit: anyFilter }">{{ cn(shown.length) }}</b> 篇
        <button v-if="anyFilter" class="clear t-aux" @click="clearAll">清除全部条件</button>
      </p>
    </header>

    <!-- 检目：三行索引，行间以墨线分，行首竖线隔出类目名 -->
    <section class="index" aria-label="检目">
      <div
        v-for="(b, bi) in bands" :key="b.key" class="band rise"
        :style="{ animationDelay: 0.1 + bi * 0.06 + 's' }"
      >
        <p class="blabel" :class="{ on: sel[b.key] }"><span>{{ b.label }}</span></p>
        <div class="terms">
          <button
            v-for="it in b.items" :key="it" class="term"
            :class="{ on: sel[b.key] === it, dead: !reachable(b.key, it) }"
            :aria-pressed="sel[b.key] === it"
            @click="pick(b.key, it as never)"
          >
            <span class="dot" />{{ it }}
          </button>
        </div>
      </div>
    </section>

    <!-- 签架：木架一道，十二签垂落其下 -->
    <section class="rack" aria-label="题名">
      <div class="bar" aria-hidden="true"><i class="cap l" /><i class="cap r" /></div>
      <div class="hangs" aria-live="polite">
        <div
          v-for="(p, i) in POEMS" :key="p.id" class="hang"
          :style="{ animationDelay: 0.44 + i * 0.055 + 's' }"
        >
          <span class="cord" aria-hidden="true" />
          <button
            class="tag"
            :class="{ out: !matches(p), on: hovered === p.id }"
            :aria-hidden="!matches(p)"
            :tabindex="matches(p) ? 0 : -1"
            @mouseenter="hovered = p.id"
            @mouseleave="unhover(p.id)"
            @focus="hovered = p.id"
            @blur="unhover(p.id)"
            @click="go('poem', 'p=' + p.id)"
          >
            <span class="cols">
              <span class="tc title t-brush">{{ p.title }}</span>
              <span class="tc meta">{{ p.dynasty }}·{{ p.author }}·{{ p.genre }}</span>
            </span>
            <!-- 签脚朱印：编号。「十二」两字比「一」宽，字号随字数收 -->
            <span class="no" :style="{ fontSize: (cn(i + 1).length > 1 ? 12 : 19) + 'px' }">{{ cn(i + 1) }}</span>
          </button>
        </div>
      </div>
    </section>

    <!-- 落款带 -->
    <footer class="foot rise" style="animation-delay:.86s">
      <div class="pv">
        <template v-if="preview">
          <p class="pv-line"><span class="mark">「</span>{{ preview.first }}<span class="mark">」</span></p>
          <p class="pv-meta t-aux">
            《{{ preview.title }}》　{{ preview.dynasty }} · {{ preview.author }}
            　·　{{ preview.genre }}　{{ FORM[preview.form] }}　共 {{ totalLines(preview) }} 句
          </p>
        </template>
        <p v-else-if="none" class="pv-none t-brush">此条件之下，卷中无诗</p>
        <p v-else class="pv-idle t-aux">十二篇俱在 ｜ 悬停签条，此处显其首句</p>
      </div>

      <div class="acts">
        <p v-if="anyFilter" class="picked t-aux">
          已选
          <span v-for="([k, v]) in activeFilters" :key="k" class="chip">{{ v }}</span>
        </p>
        <button class="btn ghost" @click="go('home')">返回首页</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.sel { position: absolute; inset: 0; background: linear-gradient(115deg, #f6efe0, #eee4cf); overflow: hidden; }
/* 场所背板是首位绝对定位子元素，页首 / 检目 / 签架 / 落款带皆绝对定位，故 DOM 顺序即层序；
   纸纹层 .paper-grain::after 是末位生成内容，仍在最上。不必也不能给它们加 position/z-index——
   那会把本就绝对定位的版块压回文档流。 */

/* ---------- 页首 ---------- */
.top { position: absolute; left: 96px; right: 96px; top: 44px; display: flex; align-items: flex-end; justify-content: space-between; }
.title { font-size: 46px; letter-spacing: .22em; }
.sub { margin-top: 8px; letter-spacing: .16em; }
.count { display: flex; align-items: center; gap: 10px; }
.count b { font-size: 24px; font-weight: 600; color: var(--ink); transition: color .3s; }
.count b.hit { color: var(--cinnabar); }
.clear { margin-left: 14px; color: var(--ink); border-bottom: 1px solid var(--cinnabar); padding-bottom: 1px; }
.clear:hover { color: var(--cinnabar); }

/* ---------- 检目：三行索引 ---------- */
.index {
  position: absolute; left: 96px; right: 96px; top: 148px;
  border-top: 1.5px solid var(--line); border-bottom: 1.5px solid var(--line);
}
.band { display: flex; align-items: center; min-height: 58px; }
.band + .band { border-top: 1px solid var(--line); }
.blabel { flex: 0 0 118px; display: flex; align-items: center; border-right: 1px solid var(--line); }
.blabel span { font-size: 18px; font-weight: 600; letter-spacing: .34em; color: var(--stone); transition: color .28s; }
.blabel.on span { color: var(--cinnabar); }
.terms { display: flex; align-items: center; gap: 6px; padding-left: 22px; }

/* 条目：常驻一个顿点，选中时化作朱印 */
.term {
  display: inline-flex; align-items: center; gap: 11px; height: 46px;
  padding: 0 calc(14px - .14em) 0 14px; font-size: 21px; letter-spacing: .14em;
  color: var(--ink-soft); white-space: nowrap; transition: color .22s, background .22s;
}
.dot {
  flex: none; width: 5px; height: 5px; border-radius: 50%;
  background: var(--ink-faint); opacity: .5;
  transition: width .24s, height .24s, border-radius .24s, background .24s, opacity .24s, transform .24s;
}
.term:hover { color: var(--ink); background: rgba(37, 42, 45, .06); }
.term:hover .dot { opacity: 1; transform: scale(1.4); }
.term:focus-visible { outline: none; background: rgba(37, 42, 45, .1); color: var(--ink); }
.term.on { color: var(--cinnabar); font-weight: 700; }
.term.on .dot { width: 13px; height: 13px; border-radius: 2px; background: var(--cinnabar); opacity: 1; transform: rotate(-3deg); }
/* 与其余两维已选条件无法组合的条件：淡下去但仍可点（便于看清为何无果） */
.term.dead:not(.on) { opacity: .3; }

/* ---------- 签架 ---------- */
.rack { position: absolute; left: 96px; right: 96px; top: 372px; height: 552px; }

/* 木架：比签列每侧宽 10px，两端出轴头 */
.bar {
  position: relative; height: 16px; margin: 0 -10px; border-radius: 3px;
  background: #4a2a20; box-shadow: 0 5px 12px rgba(37, 42, 45, .2);
}
.bar::before {
  content: ''; position: absolute; inset: 0; opacity: .92; border-radius: 3px;
  background: url('../assets/art/roller-wood.png') center / cover;
  filter: saturate(.62) brightness(.86);
}
.bar::after {
  content: ''; position: absolute; inset: 0; border-radius: 3px;
  background: linear-gradient(180deg, rgba(0, 0, 0, .5), rgba(255, 244, 220, .18) 44%, rgba(255, 244, 220, .08) 60%, rgba(0, 0, 0, .5));
}
.cap { position: absolute; top: 0; bottom: 0; width: 32px; background: linear-gradient(180deg, rgba(0, 0, 0, .34), rgba(255, 240, 210, .3) 46%, rgba(0, 0, 0, .4)); }
.cap.l { left: 0; border-radius: 3px 0 0 3px; box-shadow: inset -2px 0 0 rgba(26, 14, 9, .45); }
.cap.r { right: 0; border-radius: 0 3px 3px 0; box-shadow: inset 2px 0 0 rgba(26, 14, 9, .45); }

.hangs { display: flex; gap: 36px; align-items: flex-start; }

/* 一挂：绳 + 签。旋轴在架（顶心），动画与 hover 各占一层 transform，互不打架 */
.hang {
  flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; align-items: center;
  transform-origin: 50% 0;
  animation: hang 1.2s cubic-bezier(.24, .72, .32, 1) both;
}
@keyframes hang {
  0% { opacity: 0; transform: translateY(-34px) rotate(0deg); }
  26% { opacity: 1; transform: translateY(0) rotate(-3.2deg); }
  46% { transform: translateY(0) rotate(2.1deg); }
  64% { transform: translateY(0) rotate(-1.2deg); }
  80% { transform: translateY(0) rotate(.6deg); }
  92% { transform: translateY(0) rotate(-.2deg); }
  100% { opacity: 1; transform: translateY(0) rotate(0deg); }
}

.cord { position: relative; flex: none; width: 2px; height: 38px; background: linear-gradient(180deg, rgba(37, 42, 45, .2), rgba(37, 42, 45, .6)); }
.cord::before {
  content: ''; position: absolute; left: 50%; top: -4px; width: 8px; height: 8px; margin-left: -4px;
  border-radius: 50%; background: #35200f; box-shadow: 0 0 0 1px rgba(0, 0, 0, .3);
}

/* 签：竖书两列，题名居右，小字缀左。
   文字自天头起笔（同诗篇页各列首字对齐天头之例）——十二篇共一条起笔线，
   读作名录；长短不一的收笔自然成为参差的签脚，与底部齐平的朱印成对照。 */
.tag {
  position: relative; width: 100%; height: 488px; padding: 36px 0 0;
  display: flex; align-items: flex-start; justify-content: center;
  background: linear-gradient(180deg, #fbf7ec, #f4ecda);
  border: 1px solid rgba(37, 42, 45, .3);
  box-shadow: 0 10px 22px rgba(37, 42, 45, .11), inset 0 0 0 1px rgba(255, 255, 255, .4);
  transition: transform .3s cubic-bezier(.2, .7, .2, 1), box-shadow .3s, border-color .3s, opacity .5s, filter .5s;
}
.tag:hover, .tag:focus-visible {
  transform: translateY(-7px); outline: none;
  border-color: rgba(168, 68, 55, .42);
  box-shadow: 0 18px 32px rgba(37, 42, 45, .18), inset 0 0 0 1px rgba(255, 255, 255, .5);
}
/* row-reverse：题名先入 DOM 故落在右侧（竖排自右向左的读序） */
.cols { display: flex; flex-direction: row-reverse; justify-content: center; align-items: flex-start; gap: 12px; width: 100%; }
.tc { writing-mode: vertical-rl; }
.tc.title { font-size: 46px; line-height: 1.06; letter-spacing: .06em; color: var(--indigo); }
.tc.meta { font-size: 18px; line-height: 1.1; letter-spacing: .16em; color: var(--stone); }

/* 签脚朱印编号：平时只在纸上留一点淡红，选中才实 */
.no {
  position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%) rotate(-3deg);
  display: grid; place-items: center; width: 30px; height: 30px;
  background: var(--cinnabar); color: #f6e9d6; border-radius: 2px;
  box-shadow: inset 0 0 0 1.5px rgba(246, 233, 214, .35);
  font-family: var(--f-brush); line-height: 1; opacity: .28;
  transition: opacity .3s, transform .3s cubic-bezier(.2, .7, .2, 1);
}
.tag:hover .no, .tag:focus-visible .no, .tag.on .no { opacity: 1; transform: translateX(-50%) rotate(-3deg) scale(1.08); }

/* 被筛掉：淡墨留原位，不重排、不响应指针 */
.tag.out { opacity: .15; filter: blur(.7px) saturate(.35); pointer-events: none; transform: none; box-shadow: none; border-color: rgba(37, 42, 45, .18); }

/* ---------- 落款带 ---------- */
.foot { position: absolute; left: 96px; right: 96px; bottom: 36px; height: 92px; display: flex; align-items: center; justify-content: space-between; gap: 48px; }
.pv { flex: 1; min-width: 0; }
.pv-line { font-family: var(--f-kai); font-size: 30px; line-height: 1.2; letter-spacing: .02em; color: var(--ink); }
.pv-line .mark { font-family: var(--f-song); font-size: 24px; color: var(--gold); }
.pv-meta { margin-top: 5px; letter-spacing: .12em; }
.pv-idle { letter-spacing: .14em; }
.pv-none { font-size: 38px; letter-spacing: .18em; color: var(--ink-faint); }

.acts { flex: none; display: flex; align-items: center; gap: 24px; }
.picked { display: flex; align-items: center; gap: 10px; }
.chip { padding: 2px 12px; border: 1px solid var(--cinnabar); color: var(--cinnabar); letter-spacing: .16em; }
</style>
