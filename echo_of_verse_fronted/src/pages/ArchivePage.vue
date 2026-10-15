<script setup lang="ts">
import { computed } from 'vue'
import { go } from '../router'
import { ART, totalLines } from '../data/poems'
import { clear, fmtTime, orphans, reload, resolvePoem, slots } from '../store/save'
import brocade from '../assets/art/brocade.png'
import silk from '../assets/art/silk-mount.png'
import roller from '../assets/art/roller-wood.png'

/**
 * 诗篇卷轴 · 存档 / 读档。
 *
 * 版式取「装裱横卷」（手卷）。自右端向左，一段完整的手卷依次是：
 *   天杆 → 锦包首 → 引首 → 隔水 → 画心一 → 隔水 → 画心二 → 隔水 → 画心三
 *   → 隔水 → 拖尾 → 地杆
 * 三位存档各居一段画心，画心之内即该篇的画心图——存档位于是成了三幅装裱好的画。
 *
 * 展卷方向与读序一致：左端地杆自右向左移出，卷身随其由右端渐次展开，
 * 先见锦包首，再见引首，最后是画心与拖尾。DOM 用 row-reverse，
 * 因此源码照读序书写（锦包首在前），渲染出来自然是最右端。
 *
 * 引首押一枚朱印并记「存 N 卷」；拖尾即跋，竖书存录说明。文案均为既有字符串，未新拟。
 */

interface Row {
  i: number
  poem: ReturnType<typeof resolvePoem>
  total: number
  done: number
  stamp: string
  act: number
  orphan: boolean
  orphanId?: string
}

const rows = computed<Row[]>(() =>
  slots.value.map((s, i) => {
    const poem = resolvePoem(i)
    const orph = orphans.value.find((o) => o.slot === i)
    return {
      i,
      poem,
      total: poem ? totalLines(poem) : 0,
      done: s ? s.lineIndex : 0,
      stamp: s ? fmtTime(s.savedAt) : '',
      act: s ? s.act : 0,
      orphan: !s && !!orph,
      orphanId: orph?.poemId,
    }
  }),
)

const hasAny = computed(() => rows.value.some((r) => r.poem))
/** 引首记存卷数 */
const used = computed(() => rows.value.filter((r) => r.poem).length)

const CN = ['零', '一', '二', '三']
const cn = (n: number) => CN[n] ?? String(n)
const VOL = ['一', '二', '三']

function resume(i: number) {
  const r = rows.value[i]
  if (r.poem) go('hud', `slot=${i}&p=${r.poem.id}`)
}

function remove(i: number) {
  // 失效位：连同 localStorage 里的残迹一并抹去
  clear(i)
  reload()
}
</script>

<template>
  <div
    class="arch paper-grain"
    :style="{ '--silk': `url(${silk})`, '--brocade': `url(${brocade})`, '--roller': `url(${roller})` }"
  >
    <header class="top rise">
      <h2 class="t-title title">诗篇卷轴</h2>
      <p class="t-aux sub">三卷存录 · 择一卷续读</p>
    </header>

    <!-- ---------------- 装裱横卷 ---------------- -->
    <figure class="handscroll">
      <!-- 天杆：右端细杆，展卷时握持不动 -->
      <span class="rod tian"><i class="cap t" /><i class="cap b" /></span>
      <!-- 地杆：左端粗杆，随卷身展开自右向左移出 -->
      <span class="rod di"><i class="cap t" /><i class="cap b" /></span>
      <!-- 绦带：天杆上的束卷丝绦 -->
      <span class="tie" />

      <div class="body">
        <!-- 锦包首：包在卷外的一段织锦 -->
        <div class="brocade" />

        <!-- 引首：卷首题额，押朱印并记存卷数 -->
        <div class="yinshou">
          <span class="seal lg">卷</span>
          <p class="t-aux ct">存 {{ cn(used) }} 卷</p>
        </div>

        <!-- 三段画心：每段一位存档 -->
        <template v-for="r in rows" :key="r.i">
          <span class="seam" />
          <article class="vol" :class="{ empty: !r.poem, lost: r.orphan, live: !!r.poem }">
            <!-- 已存 -->
            <template v-if="r.poem">
              <p class="t-aux idx">卷 {{ VOL[r.i] }}</p>
              <div class="core">
                <img :src="ART[r.poem.art]" alt="" />
                <span class="mat" />
              </div>
              <h3 class="ptitle t-brush">{{ r.poem.title }}</h3>
              <p class="who t-aux">{{ r.poem.author }} · {{ r.poem.dynasty }} · {{ r.poem.genre }}</p>

              <div class="dots" :aria-label="`进度 ${r.done} / ${r.total} 句`">
                <i
                  v-for="n in r.total" :key="n"
                  :class="{ past: n - 1 < r.done, now: n - 1 === r.done }"
                />
              </div>
              <p class="t-aux prog">{{ r.done }}/{{ r.total }} 句 · 第{{ VOL[r.act] }}幕</p>
              <p class="t-aux stamp">{{ r.stamp }}</p>

              <div class="acts">
                <button class="btn primary" @click="resume(r.i)"><span class="seal sm" />续读</button>
                <button class="btn ghost small" @click="remove(r.i)">誊清</button>
              </div>
            </template>

            <!-- 失效：诗篇已不在卷中 -->
            <template v-else-if="r.orphan">
              <p class="t-aux idx">卷 {{ VOL[r.i] }}</p>
              <div class="core bare"><span class="seal lg ghostseal lostseal">佚</span></div>
              <h3 class="empty-title">此卷已佚</h3>
              <p class="t-aux hint">所记篇目「{{ r.orphanId }}」<i>已不在诗库中</i></p>
              <div class="acts">
                <button class="btn ghost small" @click="remove(r.i)">抹去此卷</button>
              </div>
            </template>

            <!-- 空位 -->
            <template v-else>
              <p class="t-aux idx">卷 {{ VOL[r.i] }}</p>
              <div class="core bare"><span class="seal lg ghostseal">空</span></div>
              <h3 class="empty-title">此处尚未落墨</h3>
              <p class="t-aux hint">择一诗入境<i>进度自会记于此卷</i></p>
              <div class="acts">
                <button class="btn ghost small" @click="go('select')">开启诗境</button>
              </div>
            </template>
          </article>
        </template>

        <!-- 隔水（拖尾之前） -->
        <span class="seam" />

        <!-- 拖尾：卷尾余纸，即跋 -->
        <div class="weiba">
          <p class="t-aux col">存档仅存于本机浏览器；清除浏览数据将一并失去。</p>
          <span class="seal sm" />
        </div>
      </div>
    </figure>

    <footer class="foot rise" style="animation-delay:.4s">
      <button class="btn ghost" @click="go('home')">返回首页</button>
      <button v-if="hasAny" class="btn ghost" @click="go('select')">另择诗篇</button>
    </footer>
  </div>
</template>

<style scoped>
.arch { position: absolute; inset: 0; background: linear-gradient(115deg, #f6efe0, #eee4cf); overflow: hidden; }
.top { position: absolute; left: 96px; top: 56px; }
.title { font-size: 46px; letter-spacing: .22em; }
.sub { margin-top: 8px; letter-spacing: .16em; }

/* ---------- 横卷：总体定位 ----------
   body 1630×680，两杆各外探 20（宽）/22（高）→ 外框 1670×724，居中于舞台
   （125 … 1795，中线 960）。外框按 724 撑足，卷身内缩 22——地杆的轴头
   因此不越出外框，audit 的 BOX-OVERFLOW 不再报。 */
.handscroll { position: absolute; left: 145px; top: 222px; width: 1630px; height: 724px; }

/* ---------- 杆 ---------- */
.rod {
  position: absolute; overflow: hidden; border-radius: 3px; background: #4a2a20;
  box-shadow: 0 10px 26px rgba(37, 42, 45, .22);
}
.rod::before {
  content: ''; position: absolute; inset: 0; opacity: .92;
  background-image: var(--roller); background-size: cover; background-position: center;
  filter: saturate(.62) brightness(.86);
}
/* 圆杆的柱面明暗：横杆取竖向渐变，此处为竖杆，故取横向 */
.rod::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(90deg, rgba(0, 0, 0, .52), rgba(255, 244, 220, .18) 40%, rgba(255, 244, 220, .08) 60%, rgba(0, 0, 0, .55));
}
/* 轴头：杆两端露出的木轴头 */
.cap {
  position: absolute; left: -7px; right: -7px; height: 24px;
  background: linear-gradient(180deg, rgba(0, 0, 0, .34), rgba(255, 240, 210, .3) 46%, rgba(0, 0, 0, .4));
}
.cap.t { top: 0; box-shadow: inset 0 -2px 0 rgba(26, 14, 9, .45); }
.cap.b { bottom: 0; box-shadow: inset 0 2px 0 rgba(26, 14, 9, .45); }

.rod.tian { right: -20px; top: 8px; width: 16px; height: 708px; }
.rod.di {
  left: -20px; top: 0; width: 26px; height: 724px;
  animation: draw 1.05s cubic-bezier(.22, .75, .25, 1) both;
}
@keyframes draw { from { left: 1604px; } to { left: -20px; } }

/* 绦带：束卷的丝绦，横过天杆一道。
   right:-20px + width:16px 落在天杆上（布局坐标 x 1779…1795）；
   top 是天杆的竖向中点（天杆在卷身 y 8…716，中点 362）。 */
.tie {
  position: absolute; right: -20px; top: 358px; width: 16px; height: 9px;
  background: var(--cinnabar); opacity: .82; box-shadow: 0 0 0 1px rgba(26, 14, 9, .3);
  animation: fade .6s ease .9s both;
}
/* 绦结：垂在天杆外的一小段 */
.tie::after {
  content: ''; position: absolute; left: 3px; top: 9px; width: 10px; height: 22px;
  background: linear-gradient(180deg, var(--cinnabar), rgba(168, 68, 55, .05));
  clip-path: polygon(0 0, 100% 0, 74% 100%, 26% 100%); opacity: .72;
}

/* ---------- 卷身 ----------
   row-reverse：源码按读序写（锦包首在前），渲染即最右端。 */
.body {
  position: absolute; inset: 0; display: flex; flex-direction: row-reverse;
  overflow: hidden; background: #f4ecdc;
  animation: unroll 1.05s cubic-bezier(.22, .75, .25, 1) both;
}
@keyframes unroll { from { clip-path: inset(0 0 0 100%); } to { clip-path: inset(0 0 0 0); } }
.body::after {
  content: ''; position: absolute; inset: 0; pointer-events: none; z-index: 3;
  box-shadow: inset 0 0 70px rgba(90, 63, 32, .16);
}

/* ---------- 锦包首 ---------- */
.brocade {
  position: relative; flex: none; width: 112px; overflow: hidden; background: var(--indigo);
}
.brocade::before {
  content: ''; position: absolute; inset: 0;
  background-image: var(--brocade); background-size: 208px auto; background-position: 42% center;
  opacity: .96; filter: saturate(.9) brightness(.94);
}
/* 贴边的一道暗影，使锦与卷身分得开 */
.brocade::after {
  content: ''; position: absolute; inset: 0;
  box-shadow: inset 14px 0 22px rgba(12, 18, 24, .5), inset 0 0 0 1px rgba(37, 42, 45, .3);
}

/* ---------- 引首 ---------- */
.yinshou {
  position: relative; flex: none; width: 140px; overflow: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 22px;
  background: #f8f2e4;
}
.yinshou::before {
  content: ''; position: absolute; inset: 0;
  background-image: var(--silk); background-size: 300px auto; background-position: center;
  mix-blend-mode: multiply; opacity: .28;
}
.yinshou > * { position: relative; }
.ct { writing-mode: vertical-rl; letter-spacing: .3em; color: var(--indigo); font-weight: 600; }

/* ---------- 隔水 ---------- */
.seam {
  position: relative; flex: none; width: 12px;
  background: linear-gradient(90deg, #dcc9a4, #ecdfc4, #dcc9a4);
  border-left: 1px solid rgba(37, 42, 45, .18); border-right: 1px solid rgba(37, 42, 45, .18);
}

/* ---------- 画心：一段存档 ---------- */
.vol {
  position: relative; flex: 1 1 0; min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; align-items: center;
  padding: 32px 34px 30px; text-align: center;
  transition: background .3s;
}
/* 纸帘竖纹 */
.vol::before {
  content: ''; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background: repeating-linear-gradient(90deg, transparent 0 26px, rgba(37, 42, 45, .035) 26px 27px);
}
.vol > * { position: relative; }
.vol.live:hover { background: rgba(251, 246, 234, .72); }

/* 画心内的图版：装裱面上的一幅小画 */
.core {
  position: relative; width: 100%; height: 178px; margin-top: 12px; padding: 7px;
  background: #fbf6ea; border: 1px solid rgba(37, 42, 45, .34);
  box-shadow: 0 3px 10px rgba(37, 42, 45, .1);
}
.core img {
  display: block; width: 100%; height: 100%; object-fit: cover;
  filter: saturate(.84) contrast(1.04);
}
/* 褪色的一道内框，仿装裱的转边 */
.core .mat { position: absolute; inset: 7px; pointer-events: none; box-shadow: inset 0 0 0 1px rgba(37, 42, 45, .1); }
/* 空位 / 失效位：不设图版，只余一方空纸 */
.core.bare {
  display: grid; place-items: center; background: rgba(251, 246, 234, .5);
  box-shadow: inset 0 0 48px rgba(90, 63, 32, .1);
}
.core.bare .seal { opacity: .55; }

.idx { letter-spacing: .5em; color: var(--stone); font-weight: 600; }
.ptitle { margin-top: 14px; font-size: 42px; line-height: 1.18; color: var(--indigo); }
.who { margin-top: 6px; letter-spacing: .12em; }

/* 进度：与暂停页同一套编码——已过淡金实心、当前朱砂、未完空心（朱砂仍只作焦点） */
.dots { display: flex; flex-wrap: wrap; justify-content: center; gap: 7px; margin-top: 16px; }
.dots i { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid var(--ink-faint); background: transparent; }
.dots i.past { background: var(--gold); border-color: var(--gold); }
.dots i.now { border-color: var(--cinnabar); background: var(--cinnabar); box-shadow: 0 0 0 3px rgba(168, 68, 55, .22); }
.prog { margin-top: 10px; }
.stamp { margin-top: 2px; color: var(--ink-faint); font-size: 18px; }

.acts { display: flex; gap: 12px; margin-top: auto; padding-top: 18px; }
.btn.small { height: 44px; padding: 0 calc(22px - .16em) 0 22px; font-size: 20px; letter-spacing: .16em; }
.vol .btn.primary { height: 48px; padding: 0 calc(30px - .18em) 0 30px; font-size: 21px; letter-spacing: .18em; }

.ghostseal { background: transparent; color: rgba(37, 42, 45, .26); box-shadow: inset 0 0 0 2px rgba(37, 42, 45, .22); }
.lostseal { color: rgba(168, 68, 55, .5); box-shadow: inset 0 0 0 2px rgba(168, 68, 55, .4); }
.empty-title { font-family: var(--f-brush); font-weight: 400; font-size: 34px; margin-top: 14px; color: rgba(37, 42, 45, .5); }
/* 提示语限宽：不设 max-width 会铺满 312px 的图版宽，「卷」字会孤在第二行 */
.hint { margin-top: 8px; color: var(--ink-faint); max-width: 232px; }
.hint i { display: block; font-style: normal; }

/* 画心逐段显影：随展卷铺开 */
.vol > * { animation: rise .68s cubic-bezier(.2, .7, .2, 1) both; }
.vol > *:nth-child(1) { animation-delay: .42s; }
.vol > *:nth-child(2) { animation-delay: .48s; }
.vol > *:nth-child(3) { animation-delay: .54s; }
.vol > *:nth-child(4) { animation-delay: .6s; }
.vol > *:nth-child(5) { animation-delay: .66s; }
.vol > *:nth-child(n + 6) { animation-delay: .72s; }

/* ---------- 拖尾：卷尾跋语 ---------- */
.weiba {
  position: relative; flex: none; width: 190px; overflow: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
  background: rgba(249, 244, 232, .72);
}
.weiba::before {
  content: ''; position: absolute; inset: 0;
  background-image: var(--silk); background-size: 300px auto; background-position: center;
  mix-blend-mode: multiply; opacity: .2;
}
.weiba > * { position: relative; }
.col {
  /* 竖书跋语。height 460 只装得下 18 字（18×1.5×18 = 486），「清除浏览数据将一并失去。」
     共 22 字必折第二列、且末字成孤——故放宽到 620 让它一列到底。
     竖向留白：620 + 印 28 + gap 20 = 668 < 680，不溢。 */
  writing-mode: vertical-rl; height: 620px; font-size: 18px; line-height: 1.5;
  letter-spacing: .14em; color: var(--ink-soft); text-align: start;
}
.weiba .seal { animation: fade .8s ease 1s both; }

/* ---------- 页脚 ---------- */
.foot { position: absolute; left: 96px; bottom: 64px; display: flex; align-items: center; gap: 20px; }
</style>
