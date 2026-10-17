<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { go, params } from '../router'
import { actsOf, poemById, totalLines } from '../data/poems'
import { claimSlot, slots, write } from '../store/save'
import InkUnroll from '../components/InkUnroll.vue'
import mist from '../assets/art/mist.png'
import bambooA from '../assets/art/bamboo-1.png'
import bambooB from '../assets/art/bamboo-2.png'
import bambooC from '../assets/art/bamboo-3.png'

const poem = computed(() => poemById(params.value.p))
const halves = computed(() => {
  const p = poem.value
  if (!p) return ['', '']
  // 与 poems.ts 的约定一致：词 → 上阕/下阕；曲 → 前段/后段；诗 → 前半/后半
  if (p.form === 'ci') return ['上阕', '下阕']
  if (p.form === 'qu') return ['前段', '后段']
  return ['前半', '后半']
})
const acts = computed(() => (poem.value ? actsOf(poem.value) : []))
const minutes = computed(() => Math.max(6, Math.round(totalLines(poem.value ?? { stanzas: [[], []] } as never) * 1.6)))

/**
 * 竖排分列
 *
 * 一句一列；一句若长过一列的净高，多出来的字**自动换到下一列**（接着这一句往下排），
 * 后面各句整体右移。上下阕之间插一根分隔列作视觉断句。
 */
interface VCol {
  key: string
  chars: string[]   // 竖排逐字
  stanza: number    // 所属阕序号
  head: boolean     // 该阕首句的首列 → 阕名贴在这一列
  cont: boolean     // 跨列续排（本列是上一列的延续）
  isDivider?: true  // 阕间分隔列
}

/* ---------------- 版式：让每一列落在一根竹简上 ----------------
 * 竹简由 InkUnroll 画成 11 根等宽的简，格宽 PITCH = 1440 / 11 ≈ 130.9px。
 * 旧版版心左右各留 72px 内边距、再用 space-evenly 散布，列距 ≈ 112px ≠ 130.9px，
 * 于是每一列都骑在简缝上——看着就是「没对齐」。
 * 现在整块铺满 1440（与面板同宽），每列固定占一格，列心就正好压在简心上。
 */
const PANEL_W = 1440
const PANEL_H = 680
/* 竹简根数。定 11（奇数）是为了让中缝落在一根简的正中；
   少于 11 篇的诗（如四句的五绝）多余简在两侧均分，整组仍居中。 */
const SLIPS = 11
/* 一格 = 一根简。版心铺满 PANEL_W，列心压在简心上（见 .verse-block 注释）。 */
const PITCH = PANEL_W / SLIPS

const PAD_T = 44                  // .inner 内边距（与 CSS 一致）
const PAD_B = 40
const BAND = 58                   // 天头留给竖排阕名的空带（做在 .verse-block 的 padding-top 上）
const PREFACE_H = 68              // 序言连同下边距
/* 每字纵向占位 = 字号 × LH。
   LH = 1.36 是实测值（楷体 52px 的 8 字列，实测 566 布局 px ÷ 8 ÷ 52）。
   早先按 1.06 估的，偏小近三成，长句因此顶穿地脚。 */
const LH = 1.36
const FS_MAX = 56
const FS_MIN = 22
const SLIP_FILL = 0.96            // 一列最多用净高的 96%，留一点地脚呼吸

/** 正文能用的净高（扣掉上下内边距、阕名留白、序言） */
const verseH = computed(
  () => PANEL_H - PAD_T - PAD_B - BAND - (poem.value?.preface ? PREFACE_H : 0),
)

/** 给定字号下，一列能放几个字 */
const capAt = (fs: number) => Math.max(1, Math.floor((verseH.value * SLIP_FILL) / (fs * LH)))

/** 全部句子展平，用于取最长句 */
const allLines = computed(() => {
  const p = poem.value
  return p ? [...p.stanzas[0], ...p.stanzas[1]] : []
})

/** 句读：断列时用来找「气口」 */
const PUNCT = '，。、；：？！'
/** 收尾标点：绝不可落在列首（避头）。 */
const CLOSERS = '，。、；：？！）」』”’》〉】'
/** 起首标点：绝不可落在列尾（避尾）。 */
const OPENERS = '（「『“‘《〈【'

/**
 * 断句：把一句切成若干列。
 *
 * 竖排断列守两条老规矩：
 *   · 断在标点之后——标点收在上一列尾，读来是一口气说完再换列；
 *   · 避头尾——收尾标点不落列首，起首标点不落列尾。
 *
 * 贪心：每列先按满格放，再往前退到最近的气口；退到 40% 都找不到标点才硬切。
 * （旧版的 55% 下限太高：《我欲乘风归去，又恐琼楼玉宇，高处不胜寒。》
 * 在 cap=13 时逗号落在第 7 字，被下限挡在搜索范围外，于是硬切正好切在
 * 第二个逗号之前，`，高处不胜寒。` 以标点起头——这正是避头要禁的。）
 */
function cutLine(chars: string[], cap: number): string[][] {
  if (chars.length <= cap) {
    // 短句照排；只有「开来」的引号不留在列尾孤零零一个
    const last = chars[chars.length - 1]
    return chars.length > 1 && OPENERS.includes(last)
      ? [chars.slice(0, -1), chars.slice(-1)]
      : [chars]
  }
  const out: string[][] = []
  let rest = chars
  while (rest.length > cap) {
    let take = cap
    for (let f = cap; f >= Math.max(2, Math.ceil(cap * 0.4)); f--) {
      if (PUNCT.includes(rest[f - 1])) { take = f; break }
    }
    // 这一列若正好停在标点前，就再多收一个字，免得下一列以标点起头
    while (take < cap && CLOSERS.includes(rest[take])) take++
    out.push(rest.slice(0, take))
    rest = rest.slice(take)
  }
  if (rest.length) out.push(rest)
  return out
}

/** 按给定字号排一次版：返回列数组（不含阕间分隔列） */
function layoutAt(fs: number): VCol[] {
  const p = poem.value
  if (!p) return []
  const cap = capAt(fs)
  const out: VCol[] = []
  ;[p.stanzas[0], p.stanzas[1]].forEach((lines, si) => {
    lines.forEach((line, li) => {
      cutLine([...line], cap).forEach((seg, pi) => {
        out.push({
          key: `${si}-${li}-${pi}`,
          chars: seg,
          stanza: si,
          head: li === 0 && pi === 0,   // 阕名只贴该阕首句的首列
          cont: pi > 0,
        })
      })
    })
  })
  return out
}

/** 阕间分隔列（占一整格，否则后面的列又会错格） */
const DIVIDER: VCol = { key: 'divider', chars: [], stanza: -1, head: false, cont: false, isDivider: true }

/**
 * 自适应，按优先级两轮：
 *   1. 先试「不折列」——最多字的句子也塞得进一列，那就用最大的这种字号。
 *      七言八句能一路顶到 56px，字最大最好看。
 *   2. 折列不可避免时（《水调歌头》20 字长句），才允许折列，
 *      在「列数 ≤ 10（给分隔列留一格）」的前提下取最大字号。
 * 两轮都从 FS_MAX 往下找，取第一个成立的。
 */
const fitted = computed(() => {
  if (!poem.value) return { fs: FS_MAX, cols: [] as VCol[] }
  const longest = Math.max(1, ...allLines.value.map((l) => [...l].length))

  // 第 1 轮：不折列
  for (let fs = FS_MAX; fs >= FS_MIN; fs--) {
    if (longest <= capAt(fs)) {
      const cols = layoutAt(fs)
      if (cols.length <= SLIPS - 1) return { fs, cols }
    }
  }
  // 第 2 轮：允许折列
  for (let fs = FS_MAX; fs >= FS_MIN; fs--) {
    const cols = layoutAt(fs)
    if (cols.length <= SLIPS - 1) return { fs, cols }
  }
  return { fs: FS_MIN, cols: layoutAt(FS_MIN) }
})

/** 最终列序：上阕 … 分隔 … 下阕，从右向左排 */
const vcols = computed((): VCol[] => {
  const { cols } = fitted.value
  if (!cols.length) return []
  const mid = cols.findIndex((c) => c.stanza === 1)
  if (mid < 0) return cols
  return [...cols.slice(0, mid), DIVIDER, ...cols.slice(mid)]
})

const fontPx = computed(() => fitted.value.fs)

/** 多余的简在左右两侧均分：整组居中，且首列仍落在整数格上 */
const offsetPx = computed(() => Math.max(0, Math.floor((SLIPS - vcols.value.length) / 2)) * PITCH)

/** 传给模板的版式变量 */
const layout = computed(() => ({
  '--pitch': `${PITCH}px`,
  '--off': `${offsetPx.value}px`,
  '--band': `${BAND}px`,
  '--fs': `${fontPx.value}px`,
}))

/** 入境：认领存档位（优先空位），写入初始进度，带着位号进入局内 */
function enter() {
  const p = poem.value
  if (!p) return
  const slot = claimSlot()
  const existing = slots.value[slot]
  // 同一位上已是同一首诗 → 续读，不重置进度
  const lineIndex = existing && existing.poemId === p.id ? existing.lineIndex : 0
  write(slot, { poemId: p.id, lineIndex, act: existing && existing.poemId === p.id ? existing.act : 0 })
  go('hud', `slot=${slot}&p=${p.id}`)
}

/* ---------------- 开卷 ----------------
 * 竹简自左向右摊开，文字随后洇在其上。两件事由同一个进度 p 驱动：
 * 着色器读 drive.p 决定每根简张到几分，本页读同一个值决定文字何时起笔——
 * 因此「简开到哪儿、字浮到哪儿」不会各走各的。
 *
 * drive 是普通对象，不是 ref：着色器逐帧读它，模板绝不可读它，
 * 否则这个页面会跟着每秒重渲染 60 次，纯属白烧。开卷是否到位另用 opened 记录。
 */
const HOLD = 140          // 起手顿一拍，像先握稳再摊开
const OPEN = 1900         // 摊开时长
const REVEAL = 0.5        // 摊到这个比例，文字开始起笔

const REDUCE = matchMedia('(prefers-reduced-motion: reduce)').matches
const drive = { p: REDUCE ? 1 : 0 }
const lit = ref(REDUCE)
const opened = ref(REDUCE)
let raf = 0

// 起手慢（竹片有分量）· 中段快 · 末尾缓停，比弹性更贴合简牍的凝重
const easeInOutQuart = (t: number) => (t < 0.5 ? 8 * t * t * t * t : 1 - Math.pow(-2 * t + 2, 4) / 2)
const clamp01 = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t)

/* 开卷进度可用 hash 参数冻结，供人工与脚本核对画面：`#/poem?p=x&fr=0.6` 停在 60%。
   无头截图工具会冻结 rAF 时间戳，动画只能停在首帧，靠这个参数才拍得到中途与终态。 */
const FR = Number(params.value.fr)
const FROZEN: number | null = Number.isFinite(FR) ? clamp01(FR) : null

function run() {
  if (REDUCE) return
  if (FROZEN !== null) {
    drive.p = FROZEN
    lit.value = FROZEN > REVEAL
    opened.value = FROZEN >= 1
    return
  }
  const t0 = performance.now()
  const tick = (now: number) => {
    const k = easeInOutQuart(clamp01((now - t0 - HOLD) / OPEN))
    drive.p = k
    if (k > REVEAL) lit.value = true
    if (k >= 1) { opened.value = true; raf = 0; return }
    raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

onMounted(run)
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <div class="scroll paper-grain">
    <img class="fill mistimg" :src="mist" alt="" />
    <div class="veil" />

    <button class="back-top t-aux" @click="go('select')">‹ 返回题名录</button>

    <!-- 整组在舞台内上下左右居中 -->
    <div class="stack" :class="{ lit, opened, still: FROZEN !== null }">

      <!-- 上方：标题区 -->
      <header v-if="poem" class="head">
        <p class="t-aux kicker rv" style="--i:0">诗篇卷轴</p>
        <h2 class="t-brush title rv" style="--i:2">{{ poem.title }}</h2>
        <p class="sub rv" style="--i:4">{{ poem.first }}</p>
        <p class="t-aux author rv" style="--i:6">
          <span class="seal sm" /> {{ poem.author }} · {{ poem.dynasty }}
          <span class="genre">{{ poem.genre }}</span>
        </p>
      </header>

      <!-- 中间：竹简面板 -->
      <div class="panel">
        <InkUnroll class="mat" :srcs="[bambooA, bambooB, bambooC]" :drive="drive" :count="SLIPS" />
        <span class="cord top" />
        <span class="cord bot" />
        <span class="frame" />

        <div class="content">
          <!-- 失效降级 -->
          <main v-if="!poem" class="inner missing">
            <span class="seal lg rv" style="--i:2">佚</span>
            <p class="mt rv" style="--i:3">此篇已不在卷中</p>
            <p class="t-aux rv" style="--i:5">诗库或已更动，请回题名录重择一首。</p>
            <button class="btn primary rv" style="--i:7" @click="go('select')"><span class="seal sm" />回到题名录</button>
          </main>

          <!-- 竖排诗文：整块在竹简内居中 -->
          <main v-else class="inner">
            <!-- 序言横排在竹简顶部 -->
            <p v-if="poem.preface" class="preface t-aux rv" style="--i:4">{{ poem.preface }}</p>

            <!-- 竖排诗文：writing-mode:vertical-rl 整块容器，每句占一个「简格」（= 一根竹简宽），
                 列心落在简心上；块整体左右居中，多余的简两侧均分 -->
            <div class="verse-block" :style="layout">
              <template v-for="(col, ci) in vcols" :key="col.key">
                <span v-if="col.isDivider" class="col-divider" />
                <div v-else class="vline rv" :style="{ '--col': ci }">
                  <span v-if="col.head" class="stanza-label">{{ halves[col.stanza] }}</span>
                  <span class="line-text">{{ col.chars.join('') }}</span>
                </div>
              </template>
            </div>
          </main>
        </div>
      </div>

      <!-- 下方：三幕概览 + 操作按钮（在竹简外） -->
      <div v-if="poem" class="below rv" style="--i:2">
        <div class="acts-row">
          <span class="t-aux acts-label">三幕概览</span>
          <span class="t-aux time">约 {{ minutes }} 分钟</span>
          <ul class="acts-list">
            <li v-for="(a, ai) in acts" :key="a.t" class="rv" :style="{ '--i': 4 + ai }">
              <span class="num t-brush">{{ a.n }}</span>
              <span class="name">{{ a.t }}</span>
            </li>
          </ul>
        </div>
        <footer class="actions rv" style="--i:8">
          <button class="btn primary" @click="enter()">入境</button>
          <button class="btn ghost" @click="go('select')">另择诗篇</button>
          <button class="btn ghost" @click="go('scroll')">诗篇卷轴</button>
        </footer>
      </div>

    </div>
  </div>
</template>

<style scoped>
.scroll { position: absolute; inset: 0; }
.mistimg { opacity: .45; object-position: center bottom; }
.veil { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(243,235,221,.6), rgba(243,235,221,.18) 60%, rgba(243,235,221,.6)); }
.back-top { position: absolute; left: 96px; top: 64px; z-index: 3; padding: 8px 4px; }
.back-top:hover { color: var(--cinnabar); }

/* ---------------- 整组居中 ---------------- */
/* 组高 ≈ 标题 130 + gap 16 + 竹简 680 + gap 16 + 下栏 84 = 926，上下余 77px */
.stack {
  position: absolute; inset: 0; z-index: 2;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px;
}

/* ---------------- 标题区 ---------------- */
.head { flex: none; text-align: center; }
.kicker { letter-spacing: .5em; }
.title { font-size: 60px; line-height: 1.15; margin-top: 4px; color: var(--indigo); }
.sub { font-size: 28px; font-weight: 600; letter-spacing: .3em; margin-top: 2px; }
.author { margin-top: 6px; display: inline-flex; align-items: center; gap: 12px; }
.genre { padding: 1px 10px; border: 1px solid var(--line); letter-spacing: .2em; font-size: 17px; }

/* ---------------- 竹简面板 ---------------- */
.panel {
  position: relative; flex: none; width: 1440px; height: 680px;
  box-shadow: 0 26px 60px rgba(37, 42, 45, .20);
}
.mat { z-index: 1; }
.panel:not(:has(.mat[data-gl='ok'])) {
  background:
    repeating-linear-gradient(90deg, rgba(37,42,45,.16) 0 2px, transparent 2px 130.9px),
    repeating-linear-gradient(90deg, rgba(201,172,114,.55) 2px 127px, transparent 127px 130.9px),
    linear-gradient(180deg, #efe7d6, #e6dcc6);
}

/* 编绳 */
.cord {
  position: absolute; left: -18px; right: -18px; height: 15px; z-index: 2;
  background-image: url('../assets/art/bamboo-cord.png');
  background-size: 190px 15px; background-repeat: repeat-x;
  box-shadow: 0 1px 3px rgba(37,42,45,.35), inset 0 -1px 0 rgba(243,235,221,.18);
  opacity: 0;
}
.opened .cord { animation: cordIn .9s cubic-bezier(.2, .7, .2, 1) .12s both; }
.cord.top { top: 22px; }
.cord.bot { bottom: 22px; }

.frame {
  position: absolute; inset: 0; z-index: 3; pointer-events: none;
  box-shadow: inset 0 0 74px rgba(37,42,45,.22), inset 0 0 0 1px rgba(37,42,45,.12);
}

.content { position: absolute; inset: 0; z-index: 4; }

/* ---------------- 显影动画 ---------------- */
@keyframes inkReveal {
  from { opacity: 0; filter: blur(8px); transform: translateY(6px); }
  60%  { opacity: .85; filter: blur(1.5px); }
  to   { opacity: 1; filter: blur(0); transform: none; }
}
@keyframes cordIn { from { opacity: 0; transform: scaleX(.6); } to { opacity: 1; transform: none; } }

/* .rv 默认不可见；竹简摊开到 REVEAL 比例后（.lit）按 --col 逐列、每列内按 --chi 逐字显影
   列延迟 = --col * 180ms，字内延迟 = --chi * 55ms，最右列 --col 最小所以最先出 */
.rv { opacity: 0; }
.lit .rv {
  animation: inkReveal 1.1s cubic-bezier(.2,.7,.2,1) both;
  animation-delay: calc(var(--col, 0) * 180ms + var(--chi, 0) * 55ms);
}
.still .rv { animation: none; opacity: 1; filter: none; transform: none; }
.still .cord { opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .rv  { opacity: 1; }
  .cord { opacity: 1; }
}

/* ---------------- 竖排诗文版式 ---------------- */
.inner {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  /* 左右不留内边距：竹简格宽 1440 必须与面板等宽，列心才能压在简心上。
     序言文本自己加左右缩进。 */
  padding: 44px 0 40px;
}

/* 序言横排，紧贴天头，有上下细线 */
.preface {
  flex: none; text-align: center;
  padding: 8px 0; margin: 0 72px 16px;
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  font-size: 20px; letter-spacing: .08em;
}

/* verse-block：整块铺满竹简版心宽（1440px），逐列分格。
   本层保持 horizontal-tb，用 row-reverse 让列自右向左排——
   比在竖排容器里推「主轴/交叉轴对调」直观得多，也不会踩 direction:rtl 的坑。
   每列宽固定 = 一根简（--pitch），配合 padding-right: --off 让首列落在整数格上，
   于是「列心 = 简心」，整组左右也居中。
   天头用 padding-top 留出阕名的空带。 */
.verse-block {
  flex: 1;                              /* 吃掉序言以下的全部高度 */
  width: 1440px;
  padding-right: var(--off, 0px);
  padding-top: var(--band, 58px);
  display: flex;
  flex-direction: row-reverse;          /* 列自右向左 */
  justify-content: flex-start;          /* 从右缘起排 */
  align-items: center;                  /* 各列在净高内竖直居中 */
}

/* 每一竖列 = 一格 = 一根简。
   本层管「格内水平居中」，竖排交给里面的 .line-text：
   竖排文字默认贴着格的右缘，阕名也在右缘，两者会叠字（audit 报 OVERLAP）；
   居中后文字左右各让出 (格宽−字号)/2，阕名便有落脚处。 */
.vline {
  position: relative;
  flex: none;
  width: var(--pitch, 130.9px);
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

/* 阕名：竖排、朱砂，压在本阕首字所在那根简的天头。
   绝对定位、不参与排布，首字对齐得以保持。
   left:50% + translateX(-50%) 让它落在**简面**正中——早先写 right:0 会把它顶到
   格的右缘，正好骑在简缝上，看着像浮在两简之间、不像刻在这根简上。
   天头高度已由 --band 留出，阕名在里面，不下压正文。
   writing-mode:vertical-rl + direction:ltr 让「上/阕」自上而下读；
   不写 line-height: 1（盒子会矮于字形，audit 的 scrollHeight 恒大于 clientHeight）。 */
.stanza-label {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  font-family: var(--f-kai);
  font-size: 20px;
  line-height: 1.15;
  min-height: 1em;
  color: var(--cinnabar);
  font-weight: 700;
  letter-spacing: .2em;                 /* 竖排下即字与字的纵向间距 */
  white-space: nowrap;
  writing-mode: vertical-rl;
  direction: ltr;                       /* 否则 rtl 会把「上阕」倒成「阕上」 */
}

/* 整句文字：竖排（一行字自上而下），字号由 --fs 自适应，唐楷加粗。
   .vline 已改为 horizontal-tb，所以 writing-mode 必须落在这一层。
   direction:ltr 不可少：vertical-rl 默认 rtl，会把整句倒着读。 */
.line-text {
  font-family: var(--f-kai);
  font-size: var(--fs, 40px);
  line-height: 1;
  color: var(--ink);
  letter-spacing: .06em;
  white-space: nowrap;
  font-weight: 700;
  writing-mode: vertical-rl;
  direction: ltr;
}

/* 阕间分隔竖线：占满一格，可见线段画在中段 */
.col-divider {
  width: var(--pitch, 130.9px);
  flex: none;
  align-self: stretch;                  /* 跨轴撑满，不参与高度计算 */
  position: relative;
}
.col-divider::after {
  content: '';
  position: absolute; left: 50%; top: 34%;
  width: 1px; height: 32%;
  background: var(--line);
  transform: translateX(-50%);
}

/* ---------------- 竹简外：三幕 + 按钮 ---------------- */
.below {
  flex: none;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  width: 1440px;
}
.acts-row {
  display: flex; align-items: center; gap: 32px;
  width: 100%; padding: 12px 8px 0;
  border-top: 1px solid var(--line);
}
.acts-label { letter-spacing: .3em; }
.time { color: #6e5526; font-weight: 600; letter-spacing: .1em; flex: 1; text-align: right; }
.acts-list { display: flex; gap: 32px; }
.acts-list li { display: flex; align-items: center; gap: 12px; font-size: 22px; font-weight: 600; letter-spacing: .12em; }
.num { font-size: 34px; color: var(--indigo); width: 48px; height: 48px; display: grid; place-items: center; border: 1.5px solid var(--indigo); border-radius: 50%; }

.actions { display: flex; justify-content: center; gap: 24px; }

/* 失效篇目 */
.missing { align-items: center; justify-content: center; gap: 20px; }
.mt { font-family: var(--f-brush); font-size: 52px; }
</style>
