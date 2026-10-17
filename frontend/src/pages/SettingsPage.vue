<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { go } from '../router'
import SceneBackdrop from '../components/SceneBackdrop.vue'
import study from '../assets/art/bg-study.png'
import { bgmVolume, setBgmVolume } from '../store/bgm'

const cats = ['声音', '字幕与语言', '画面', '操作']
const cat = ref('声音')
const s = reactive({ master: 80, music: bgmVolume.value, ambient: 70, voice: 90, mouse: 50, size: 1, sub: 0, quality: 1, brush: true, reduce: false, subOn: true })

// 音乐滑块 ↔ bgm store 双向同步
watch(() => s.music, (v) => setBgmVolume(v))
watch(bgmVolume, (v) => { if (s.music !== v) s.music = v })
const sizes = ['小', '中', '大']
const subs = ['中文', 'English', '双语']
const quals = ['标准', '高', '极致']
const toast = ref(true)
</script>

<template>
  <div class="set paper-grain">
    <!-- 场所：文人书斋案头。案与砚在右下，左上留白给标题与类目，右侧面板浮于案上 -->
    <SceneBackdrop
      :far="study" position="72% 58%" tint="#b4bbb2" :strength="0.22" :veil="0.66"
      :speed="0.03" :push="0.025" :depth="0.5"
      :glows="[{ x: 1470, y: 430, w: 260, h: 260, c: 'rgba(255,214,150,.34)', d: 4.6 }]"
    />

    <h2 class="title t-title">系统设置</h2>

    <nav class="cats">
      <button v-for="c in cats" :key="c" class="menu-item" :class="{ active: c === cat }" @click="cat = c">
        <span class="seal sm" />{{ c }}
      </button>
    </nav>

    <section class="panel">
      <h3 class="ph">{{ cat }}</h3>

      <template v-if="cat === '声音'">
        <div v-for="r in [['主音量','master'],['音乐','music'],['环境音','ambient'],['旁白','voice']] as const" :key="r[1]" class="row">
          <label>{{ r[0] }}</label>
          <input type="range" min="0" max="100" v-model.number="s[r[1]]" :style="{ '--p': s[r[1]] + '%' }" />
          <output>{{ s[r[1]] }}</output>
        </div>
      </template>

      <template v-if="cat === '字幕与语言'">
        <div class="row"><label>字幕</label>
          <button class="sw" :class="{ on: s.subOn }" @click="s.subOn = !s.subOn"><i /></button><output>{{ s.subOn ? '开' : '关' }}</output></div>
        <div class="row"><label>字号</label>
          <div class="seg"><button v-for="(n, i) in sizes" :key="n" :class="{ on: s.size === i }" @click="s.size = i">{{ n }}</button></div></div>
        <div class="row"><label>语言</label>
          <div class="seg"><button v-for="(n, i) in subs" :key="n" :class="{ on: s.sub === i }" @click="s.sub = i">{{ n }}</button></div></div>
      </template>

      <template v-if="cat === '画面'">
        <div class="row"><label>画质</label>
          <div class="seg"><button v-for="(n, i) in quals" :key="n" :class="{ on: s.quality === i }" @click="s.quality = i">{{ n }}</button></div></div>
        <div class="row"><label>笔迹</label>
          <button class="sw" :class="{ on: s.brush }" @click="s.brush = !s.brush"><i /></button><output>{{ s.brush ? '开' : '关' }}</output></div>
        <div class="row"><label>减少动态</label>
          <button class="sw" :class="{ on: s.reduce }" @click="s.reduce = !s.reduce"><i /></button><output>{{ s.reduce ? '开' : '关' }}</output></div>
      </template>

      <template v-if="cat === '操作'">
        <div class="row"><label>鼠标灵敏度</label>
          <input type="range" min="0" max="100" v-model.number="s.mouse" :style="{ '--p': s.mouse + '%' }" /><output>{{ s.mouse }}</output></div>
      </template>

      <p v-if="toast" class="saved t-aux"><span class="seal sm" />设置已保存</p>
    </section>

    <footer class="actions">
      <button class="btn ghost">恢复默认</button>
      <button class="btn primary" @click="go('home')">返回</button>
    </footer>
  </div>
</template>

<style scoped>
.set { position: absolute; inset: 0; background: linear-gradient(110deg, #f6efe0, #eee4cf); }
/* 场所背板为首位绝对定位子元素；标题 / 类目 / 面板皆绝对定位，DOM 顺序即层序，纸纹层最上 */
.title { position: absolute; left: 96px; top: 64px; font-size: 44px; }
.cats { position: absolute; left: 96px; top: 240px; display: flex; flex-direction: column; gap: 10px; }
.cats .menu-item { font-size: 28px; }
.panel { position: absolute; left: 640px; right: 96px; top: 190px; padding: 40px 64px 48px; min-height: 560px; background: #f8f2e4; border: 1px solid var(--line); border-top: 3px solid var(--indigo); max-width: 1000px; }
.ph { font-size: 32px; letter-spacing: .3em; font-weight: 600; margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }
.row { display: grid; grid-template-columns: 220px 1fr 80px; align-items: center; height: 88px; border-bottom: 1px dashed rgba(37,42,45,.16); }
.row label { font-size: 26px; letter-spacing: .14em; }
.row output { text-align: right; font: 600 26px var(--f-en); letter-spacing: .06em; font-variant-numeric: lining-nums tabular-nums; }
.seg, .row .sw { grid-column: 2; }
.seg { display: inline-flex; width: max-content; border: 1.5px solid var(--ink); }
.seg button { min-width: 120px; height: 52px; font-size: 22px; letter-spacing: .14em; }
.seg button + button { border-left: 1.5px solid var(--ink); }
.seg button.on { background: var(--indigo); color: var(--paper); }
.sw { width: 96px; height: 44px; border: 1.5px solid var(--ink); border-radius: 22px; position: relative; justify-self: start; }
.sw i { position: absolute; top: 5px; left: 6px; width: 30px; height: 30px; border-radius: 50%; background: var(--ink-faint); transition: .25s; }
.sw.on { background: var(--indigo); border-color: var(--indigo); }
.sw.on i { left: 54px; background: var(--paper); }
input[type=range] { -webkit-appearance: none; appearance: none; width: 100%; height: 28px; background: transparent; --p: 50%; }
input[type=range]::-webkit-slider-runnable-track { height: 3px; background: linear-gradient(90deg, var(--indigo) var(--p), rgba(37,42,45,.25) var(--p)); }
input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 22px; height: 22px; margin-top: -9.5px; border-radius: 50%; background: var(--paper); border: 2.5px solid var(--indigo); }
input[type=range]:focus-visible::-webkit-slider-thumb { border-color: var(--cinnabar); }
.saved { position: absolute; right: 64px; bottom: 16px; display: flex; gap: 10px; align-items: center; }
.actions { position: absolute; left: 96px; bottom: 64px; display: flex; gap: 24px; }
</style>
