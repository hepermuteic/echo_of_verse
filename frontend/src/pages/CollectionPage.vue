<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { go, params } from '../router'
import { ART, POEMS, allLines } from '../data/poems'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import silk from '../assets/art/silk-mount.png'
import roller from '../assets/art/roller-wood.png'
import mountroom from '../assets/art/bg-mountroom.png'

/**
 * 诗心拾遗 · 陈列室。
 *
 * 版式取「装裱立轴」：天杆 / 绫绢天头（带惊燕、题签）/ 隔水 / 画心 / 隔水 /
 * 地头 / 木轴。切换条目时立轴自天头向下展开，木轴同步下移，卷面随即显影。
 * 左栏为签条目录（只列名目，不设图版——图版让给立轴），右栏为题跋。
 *
 * 三个分类共用一种条目形状（Entry），详情面板按字段有无降级渲染：
 * 缺 `clip / note / works` 者整块不渲染，缺 `line` 者不出名句。
 * 所有文案均取自 `data/poems.ts` 既有字段，未新增自拟内容。
 */

type Tab = '意象' | '名句' | '人物背景'
const tabs: Tab[] = ['意象', '名句', '人物背景']
const tab = ref<Tab>('意象')

interface Entry {
  key: string
  /** 主名：意象名 / 篇名 / 诗人 */
  name: string
  /** 名句；无则不出 */
  line?: string
  /** 出处与归属，一行小字 */
  meta: string
  art: string
  clip?: string
  note?: string
  src?: string
  /** 卷中篇目：仅「人物背景」有 */
  works?: string[]
  /** 名句之后的其余句子：仅「名句」有 */
  rest?: string[]
}

/** 意象：仅《水调歌头》带 `imagery`，其余篇目优雅降级 */
const imageryEntries = computed<Entry[]>(() =>
  POEMS.filter((p) => p.imagery?.length).flatMap((p) =>
    p.imagery!.map((im) => ({
      key: `${p.id}-${im.name}`,
      name: im.name,
      line: im.line,
      meta: `出自《${p.title}》 · ${p.author} · ${p.dynasty}`,
      art: ART[im.art],
      clip: im.clip,
      note: im.note,
      src: im.src,
    }))))

/** 名句：取各篇首句（诗库中已有的「首句」字段），不另拟「名句」 */
const lineEntries = computed<Entry[]>(() =>
  POEMS.map((p) => {
    const lines = allLines(p)
    return {
      key: `line-${p.id}`,
      name: p.title,
      line: lines[0] ?? p.first,
      meta: `《${p.title}》 · ${p.author} · ${p.dynasty}`,
      art: ART[p.art],
      rest: lines.slice(1),
      src: `${p.genre} · ${p.form === 'ci' ? '词' : p.form === 'qu' ? '曲' : '诗'}　·　卷中 ${lines.length} 句`,
    }
  }))

/**
 * 人物背景：诗库中并无诗人生平字段，故只陈列已有的事实——
 * 朝代、卷中收录篇目。不撰小传（自拟文案须经用户审校史实）。
 */
const poetEntries = computed<Entry[]>(() => {
  const by = new Map<string, { dynasty: string; works: string[]; art: string; src: string }>()
  POEMS.forEach((p) => {
    const e = by.get(p.author)
    if (e) e.works.push(p.title)
    else by.set(p.author, { dynasty: p.dynasty, works: [p.title], art: ART[p.art], src: p.genre })
  })
  return [...by.entries()].map(([author, v]) => ({
    key: `poet-${author}`,
    name: author,
    meta: `${v.dynasty} · 卷中收录 ${v.works.length} 篇`,
    art: v.art,
    works: v.works,
    src: `${v.dynasty}人 · 代表题材 ${v.src}`,
  }))
})

const entries = computed(() =>
  tab.value === '意象' ? imageryEntries.value
    : tab.value === '名句' ? lineEntries.value
      : poetEntries.value)

const cur = ref(0)
const item = computed(() => entries.value[cur.value] ?? entries.value[0])
const empty = computed(() => 'empty' in params.value)

/** 换类即回到首条，否则下标会越过新列表 */
watch(tab, () => { cur.value = 0 })

const CN = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const cn = (n: number) => (n <= 10 ? CN[n] : n < 20 ? '十' + CN[n - 10] : String(n))

/** 题签高 150px、上下各留 12px：按字数收回字号，否则「水调歌头」会折成两列 */
const tagSize = computed(() => {
  const n = item.value?.name.length ?? 2
  return Math.max(19, Math.min(32, Math.floor(126 / n)))
})

/** 预载画心图：换条时即刻出图。用 Image() 而非隐藏容器，DOM 里不留痕迹（隐藏容器会触发 audit） */
Object.values(ART).forEach((src) => { const im = new Image(); im.src = src })
</script>

<template>
  <div class="col paper-grain" :style="{ '--silk': `url(${silk})`, '--roller': `url(${roller})` }">
    <!-- 场所：装裱工坊。左侧给目录与立轴留白，所以底图取景偏右 -->
    <SceneBackdrop
      :far="mountroom" position="86% 42%" tint="#a9b8bd" :strength="0.22" :veil="0.74"
      :speed="0.035" :push="0.03" :depth="0.55"
      :glows="[{ x: 1420, y: 300, w: 300, h: 300, c: 'rgba(214,226,231,.30)', d: 7.5 }]"
    />

    <header class="masthead rise">
      <div>
        <h2 class="t-title title">诗心拾遗</h2>
        <p class="t-aux sub">入境所遇，皆录于此</p>
      </div>
      <button class="btn ghost" @click="go('home')">返回首页</button>
    </header>

    <nav class="tabs rise" style="animation-delay:.08s" aria-label="拾遗分类">
      <button
        v-for="t in tabs" :key="t" class="tab"
        :class="{ on: t === tab }" @click="tab = t"
      >{{ t }}</button>
    </nav>

    <!-- ---------------- 空状态：一幅未落墨的立轴 ---------------- -->
    <div v-if="empty || !entries.length" class="void fade">
      <div class="void-core"><span class="seal lg">境</span></div>
      <p class="void-msg t-brush">入境后，你遇见的意象会留在这里</p>
      <button class="btn primary" @click="go('select')"><span class="seal sm" />开启诗境</button>
    </div>

    <template v-else>
      <!-- ---------------- 左：签条目录 ---------------- -->
      <nav :key="tab" class="rail rise" style="animation-delay:.12s" aria-label="拾遗目录">
        <button
          v-for="(e, i) in entries" :key="e.key" class="tag"
          :class="{ on: i === cur }"
          :aria-current="i === cur"
          @click="cur = i"
        >
          <span class="tag-no">{{ cn(i + 1) }}</span>
          <span class="tag-name t-brush">{{ e.name }}</span>
          <span v-if="tab === '意象' && i === 0" class="tag-new"><span class="seal sm" />新获</span>
        </button>
      </nav>

      <!-- ---------------- 中：装裱立轴 ---------------- -->
      <figure :key="'s' + item.key" class="scroll" aria-hidden="true">
        <span class="cord" />
        <span class="rod top" />
        <div class="scroll-body">
          <div class="mount sky">
            <span class="jingyan a" /><span class="jingyan b" />
            <span class="tichien"><i class="t-brush" :style="{ fontSize: tagSize + 'px' }">{{ item.name }}</i></span>
          </div>
          <span class="seam a" />
          <div class="core"><img :src="item.art" alt="" /></div>
          <span class="seam b" />
          <div class="mount earth" />
        </div>
        <span class="rod bottom"><i class="cap l" /><i class="cap r" /></span>
      </figure>

      <!-- ---------------- 右：题跋 ---------------- -->
      <article :key="'n' + item.key" class="note">
        <p class="kick t-aux">{{ tab }}</p>
        <h3 class="name t-brush">{{ item.name }}</h3>
        <p v-if="item.line" class="verse">
          <span class="mark">「</span>{{ item.line }}<span class="mark">」</span>
        </p>
        <p class="meta t-aux">{{ item.meta }}</p>
        <div class="rule"><span class="seal" /></div>

        <template v-if="item.clip">
          <h4 class="lbl">此行片段 <em>游戏创作</em></h4>
          <p class="para">{{ item.clip }}</p>
        </template>
        <template v-if="item.note">
          <h4 class="lbl">文化说明</h4>
          <p class="para">{{ item.note }}</p>
        </template>
        <template v-if="item.rest?.length">
          <h4 class="lbl">卷中余句</h4>
          <p class="para rest"><span v-for="l in item.rest" :key="l">{{ l }}</span></p>
        </template>
        <template v-if="item.works">
          <h4 class="lbl">卷中篇目</h4>
          <p class="para works">{{ item.works.join('　·　') }}</p>
        </template>
        <p v-if="item.src" class="src t-aux">来源　{{ item.src }}</p>
      </article>
    </template>
  </div>
</template>

<style scoped>
.col { position: absolute; inset: 0; background: linear-gradient(110deg, #f6efe0, #eee4cf); }
/* 场所背板为末位绝对定位子元素……实为首位；各版块皆绝对定位，DOM 顺序即层序，
   纸纹层 .paper-grain::after 在最上。不动版块的 position / z-index。 */

/* ---------- 页首 ---------- */
.masthead { position: absolute; left: 96px; right: 96px; top: 56px; display: flex; align-items: flex-start; justify-content: space-between; }
.title { font-size: 46px; letter-spacing: .22em; }
.sub { margin-top: 8px; letter-spacing: .16em; }

.tabs { position: absolute; left: 96px; top: 164px; display: flex; gap: 34px; }
.tab { position: relative; padding: 0 2px 10px; font-size: 24px; font-weight: 500; letter-spacing: .22em; color: var(--ink-soft); transition: color .25s; }
.tab::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: var(--cinnabar);
  transform: scaleX(0); transform-origin: left; transition: transform .34s cubic-bezier(.2, .7, .2, 1);
}
.tab:hover { color: var(--ink); }
.tab.on { color: var(--ink); font-weight: 700; }
.tab.on::after { transform: scaleX(1); }

/* ---------- 左：签条目录 ---------- */
/* 只列名目，不著出处（出处已在右栏题跋）。双列，12 条不必滚动 */
.rail {
  position: absolute; left: 96px; top: 250px; width: 384px; height: 690px;
  display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 62px;
  gap: 10px; align-content: start;
}

.tag {
  position: relative; display: flex; align-items: center; gap: 8px;
  padding: 0 10px 0 12px; text-align: left; min-width: 0;
  background: rgba(251, 246, 234, .58); border: 1px solid var(--line);
  transition: background .25s, border-color .25s, box-shadow .25s, transform .25s;
}
.tag::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--stone); opacity: .45; transition: opacity .25s, background .25s;
}
.tag-no { flex: none; width: 15px; font-family: var(--f-en); font-size: 15px; color: var(--ink-faint); }
/* min-width:0 让 flex 子项能收缩到内容宽度以下，ellipsis 才会生效。
   21px + .04em 是量出来的：列宽 187、内容宽 165，而最长篇名「送元二使安西」
   在 22px/.08em 下需 168px（差 3px 被截）。再长则优雅降级为省略号——
   完整篇名在右栏题跋里。 */
.tag-name { min-width: 0; font-size: 21px; letter-spacing: .04em; line-height: 1.1; color: var(--indigo); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tag-new { position: absolute; right: 6px; top: 2px; display: flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--cinnabar); }
.tag:hover { background: #fbf6ea; border-color: rgba(37, 42, 45, .42); }
.tag:hover::before { opacity: 1; }
.tag:focus-visible { outline: none; background: #fbf6ea; border-color: rgba(37, 42, 45, .42); }
.tag.on { background: #fbf6ea; box-shadow: 0 8px 20px rgba(37, 42, 45, .12); transform: translateX(5px); }
.tag.on::before { background: var(--cinnabar); opacity: 1; }
.tag.on .tag-name { color: var(--ink); }

/* ---------- 中：装裱立轴 ---------- */
.scroll { position: absolute; left: 528px; top: 230px; width: 520px; height: 770px; }

/* 挂绳：自天杆上行 */
.cord {
  position: absolute; left: 50%; top: -36px; width: 2px; height: 40px; transform: translateX(-50%);
  background: linear-gradient(180deg, rgba(37, 42, 45, .12), rgba(37, 42, 45, .55));
}

/* 天杆与木轴（轴头在木轴的圆底之上） */
.rod { position: absolute; left: -24px; width: 568px; overflow: hidden; border-radius: 3px; background: #4a2a20; }
.rod.top { top: 0; height: 16px; }
.rod.bottom { top: 746px; height: 24px; animation: descend .9s cubic-bezier(.2, .75, .3, 1) both; }
.rod::before {
  content: ''; position: absolute; inset: 0; opacity: .92;
  background-image: var(--roller); background-size: cover; background-position: center;
  filter: saturate(.62) brightness(.86);
}
.rod::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(0, 0, 0, .5), rgba(255, 244, 220, .16) 42%, rgba(255, 244, 220, .08) 58%, rgba(0, 0, 0, .55));
}
.cap { position: absolute; top: 0; bottom: 0; width: 34px; background: linear-gradient(180deg, rgba(0, 0, 0, .34), rgba(255, 240, 210, .3) 46%, rgba(0, 0, 0, .4)); }
.cap.l { left: 0; box-shadow: inset -2px 0 0 rgba(26, 14, 9, .45); }
.cap.r { right: 0; box-shadow: inset 2px 0 0 rgba(26, 14, 9, .45); }

/* 卷身：自天头向下展开 */
.scroll-body {
  position: absolute; left: 0; top: 16px; width: 520px; height: 730px; overflow: hidden;
  animation: unroll .9s cubic-bezier(.2, .75, .3, 1) both;
}
.scroll-body::after { content: ''; position: absolute; inset: 0; pointer-events: none; box-shadow: inset 0 0 64px rgba(90, 63, 32, .15); }
@keyframes unroll { from { clip-path: inset(0 0 100% 0); } to { clip-path: inset(0 0 0 0); } }
@keyframes descend { from { top: 16px; } to { top: 746px; } }

/* 绫绢天头 / 地头 */
.mount { position: absolute; left: 0; width: 520px; overflow: hidden; background: #efe4cd; }
.mount.sky { top: 0; height: 190px; }
.mount.earth { top: 562px; height: 168px; }
.mount::before {
  content: ''; position: absolute; inset: 0;
  background-image: var(--silk); background-size: 300px auto; background-position: center;
  mix-blend-mode: multiply; opacity: .5;
}

/* 惊燕：天头上两条窄绫 */
.jingyan { position: absolute; top: 0; width: 13px; height: 146px; background: rgba(150, 118, 68, .26); box-shadow: inset 1px 0 0 rgba(37, 42, 45, .13), inset -1px 0 0 rgba(37, 42, 45, .13); }
.jingyan.a { left: 130px; }
.jingyan.b { left: 377px; }

/* 题签：天头左上，竖书 */
.tichien {
  position: absolute; left: 26px; top: 26px; width: 48px; height: 150px;
  display: grid; place-items: center; background: #f8f2e2;
  border: 1px solid rgba(168, 68, 55, .5); box-shadow: 0 2px 7px rgba(37, 42, 45, .1);
}
.tichien i { writing-mode: vertical-rl; font-style: normal; font-size: 32px; letter-spacing: .16em; color: var(--ink); }

/* 隔水 */
.seam {
  position: absolute; left: 0; width: 520px; height: 16px;
  background: linear-gradient(180deg, #dcc9a4, #e8dabd);
  border-top: 1px solid rgba(37, 42, 45, .16); border-bottom: 1px solid rgba(37, 42, 45, .16);
}
.seam.a { top: 190px; }
.seam.b { top: 546px; }

/* 画心 */
.core { position: absolute; left: 56px; top: 206px; width: 408px; height: 340px; padding: 8px; background: #f8f2e4; border: 1px solid rgba(37, 42, 45, .35); }
.core img { display: block; width: 100%; height: 100%; object-fit: cover; filter: saturate(.82) contrast(1.04); }

/* ---------- 右：题跋 ---------- */
.note { position: absolute; left: 1152px; top: 240px; width: 672px; }
.note > * { animation: rise .72s cubic-bezier(.2, .7, .2, 1) both; }
.note > *:nth-child(1) { animation-delay: .16s; }
.note > *:nth-child(2) { animation-delay: .22s; }
.note > *:nth-child(3) { animation-delay: .28s; }
.note > *:nth-child(4) { animation-delay: .34s; }
.note > *:nth-child(5) { animation-delay: .4s; }
.note > *:nth-child(n + 6) { animation-delay: .46s; }

.kick { font-weight: 600; letter-spacing: .44em; color: var(--stone); }
.name { margin-top: 6px; font-size: 76px; line-height: 1.06; color: var(--indigo); }
.verse { margin-top: 18px; font-family: var(--f-kai); font-size: 38px; line-height: 1.55; letter-spacing: .02em; color: var(--ink); }
.verse .mark { font-family: var(--f-song); font-size: 30px; color: var(--gold); }
.meta { margin-top: 14px; letter-spacing: .14em; }
.rule { display: flex; align-items: center; gap: 16px; margin: 24px 0 22px; }
.rule::before, .rule::after { content: ''; height: 1px; background: var(--line); }
.rule::before { flex: 0 0 60px; }
.rule::after { flex: 1; }

.lbl { display: flex; align-items: center; gap: 12px; margin: 22px 0 8px; font-size: 20px; font-weight: 400; letter-spacing: .32em; color: var(--stone); }
.lbl em { font-style: normal; font-size: 15px; letter-spacing: .1em; padding: 1px 8px; border: 1px solid var(--stone); }
.para { max-width: 632px; font-size: 22px; line-height: 1.9; color: var(--ink); }
/* 卷中余句：每句独占一行，楷体，比首句轻 */
.rest { display: flex; flex-direction: column; font-family: var(--f-kai); font-size: 24px; line-height: 1.85; color: var(--ink); }
.works { font-family: var(--f-kai); letter-spacing: .04em; }
.src { margin-top: 22px; letter-spacing: .1em; color: var(--ink-faint); }

/* ---------- 空状态 ---------- */
.void { position: absolute; inset: 0; padding-top: 130px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 30px; }
.void-core {
  display: grid; place-items: center; width: 340px; height: 300px;
  background: #f8f2e4; border: 1px solid rgba(37, 42, 45, .3);
  box-shadow: inset 0 0 56px rgba(90, 63, 32, .12);
}
.void-core .seal { opacity: .5; }
.void-msg { font-size: 46px; letter-spacing: .1em; color: var(--ink); text-align: center; }
</style>
