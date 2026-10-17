<script setup lang="ts">
/**
 * 竹简开卷 · WebGL 着色器
 *
 * 每根简一个 quad。顶点着色器按各简自己的局部进度把简自下缘竖向张开——
 * 如同一卷竹简自左向右摊开：左侧先起、依次向右，形成一道展开的波；
 * 片元着色器负责竹纹（纵向纤维）、简缘倒角高光，以及随进度洇开又收干的墨痕。
 *
 * 文字不在此层：由 PoemPage 以 DOM 叠在其上，进度由同一个驱动器给出，
 * 所以「简开到哪儿、字浮到哪儿」天然对齐，不靠猜。
 *
 * 进度经 `drive.p` 以普通对象传入，不走 props 响应式——本组件有自己的 rAF，
 * 若每帧推一个响应式值，父组件会跟着每秒重渲染 60 次，纯属白烧。
 *
 * WebGL 不可用时静默退化：画布保持透明，页面底下的 CSS 竹席纹兜底。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 竹简贴图，按简序轮换使用 */
    srcs: string[]
    /** 开卷进度驱动器，读到 0→1 */
    drive: { p: number }
    /** 简数 */
    count?: number
    /** 单根简张开所占的进度比例，余下的留给错峰 */
    dur?: number
    /** 简与简的缝隙（占单格宽度的比例，单侧） */
    gap?: number
  }>(),
  { count: 11, dur: 0.42, gap: 0.028 },
)

const cv = ref<HTMLCanvasElement>()
let gl: WebGLRenderingContext | null = null
let prog: WebGLProgram | null = null
const uni: Record<string, WebGLUniformLocation | null> = {}
let raf = 0
let ready = false
let openedAt = 0
let t0 = 0

const MAXW = 1900 // 背板分辨率上限：竹纹是软材质，超过这个宽度肉眼无收益、只烧 GPU

const VS = `
attribute vec2 aPos;      // quad 角点，0..1
attribute float aSlip;    // 简序
uniform float uN;
uniform float uP;         // 全局开卷进度
uniform float uStag;      // 相邻简的起手错峰
uniform float uDur;       // 单简张开时长
varying vec2 vUV;
varying float vSlip;
varying float vPi;
void main() {
  float pi = clamp((uP - aSlip * uStag) / uDur, 0.0, 1.0);
  float e = 1.0 - pow(1.0 - pi, 4.0);   // easeOutQuart：快起缓落，像竹片落下咬住编绳
  vPi = pi;
  vSlip = aSlip;
  vUV = aPos;
  float x = ((aPos.x + aSlip) / uN) * 2.0 - 1.0;
  float y = aPos.y * (0.004 + 0.996 * e) * 2.0 - 1.0;   // 自下缘竖向张开
  gl_Position = vec4(x, y, 0.0, 1.0);
}`

const FS = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

varying vec2 vUV;
varying float vSlip;
varying float vPi;

uniform sampler2D uT0;
uniform sampler2D uT1;
uniform sampler2D uT2;
uniform float uP;      // 全局开卷进度：片元里要用它算墨痕何时收干
uniform float uGap;
uniform float uCrop;
uniform float uT;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float nz(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x),
             mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}

float fbm4(vec2 q) {
  float a = 0.5;
  float s = 0.0;
  for (int k = 0; k < 4; k++) { s += a * nz(q); q = q * 2.03 + vec2(3.1, 7.7); a *= 0.5; }
  return s;
}

void main() {
  float id = vSlip;

  // 简缝：露出的窄槽压深，读作简与简之间的空档
  if (vUV.x < uGap || vUV.x > 1.0 - uGap) {
    gl_FragColor = vec4(vec3(0.16, 0.14, 0.11), 0.42 * smoothstep(0.0, 0.12, vPi));
    return;
  }
  float su = (vUV.x - uGap) / (1.0 - 2.0 * uGap);   // 简面内的横向 0..1

  // 竹纹：按简序轮换三张贴图，各取一竖列，免得相邻简纹理撞脸。
  // 纵向按简序随机翻转，否则各简的竹节会连成一道横贯整片的亮带。
  float pick = mod(id, 3.0);
  float u0 = h21(vec2(id, 7.3)) * (1.0 - uCrop);
  float flip = step(0.5, h21(vec2(id, 4.1)));
  vec2 tuv = vec2(u0 + su * uCrop, mix(vUV.y, 1.0 - vUV.y, flip));
  vec3 c;
  if (pick < 1.0)      c = texture2D(uT0, tuv).rgb;
  else if (pick < 2.0) c = texture2D(uT1, tuv).rgb;
  else                 c = texture2D(uT2, tuv).rgb;

  // 纵向纤维：细条 + 宽疏两层，让竹面有丝缕感
  float fibFine = nz(vec2(su * 160.0, 3.7));
  float fibWide = nz(vec2(su * 26.0, vUV.y * 0.8 + id * 5.0));
  c *= 0.92 + 0.13 * fibFine + 0.08 * fibWide;

  // 每根简深浅略有出入，免得整片像一块板
  c *= 0.95 + 0.09 * h21(vec2(id, 2.9));

  // 简缘倒角：两侧压暗，紧贴边缘再补一道窄高光（竹片磨出的棱）
  float sd = smoothstep(0.0, 0.085, su) * smoothstep(1.0, 0.915, su);
  c *= mix(0.56, 1.0, sd);
  float hl = smoothstep(0.016, 0.0, su) + smoothstep(0.984, 1.0, su);
  c += vec3(0.20, 0.17, 0.12) * hl * 0.22;

  // 墨洇：沿纤维方向拉长，随进度洇开；展开完成后要「干」掉，
  // 否则整片暗斑会跟上面的诗句抢视线
  float dry = 1.0 - smoothstep(0.72, 0.98, uP);
  float bloom = smoothstep(0.12, 0.82, vPi);
  float inkN = fbm4(vec2(su * 4.4 + id * 13.0, vUV.y * 2.4 - uT * 0.05));
  float seep = nz(vec2(su * 90.0, vUV.y * 1.1 + uT * 0.03));
  float ink = smoothstep(0.52, 0.86, inkN) * bloom * (0.55 + 0.45 * seep) * dry;
  c = mix(c, vec3(0.155, 0.135, 0.115), ink * 0.34);
  c = mix(c, vec3(0.20, 0.17, 0.14), bloom * 0.04 * dry);

  // 起手那道湿口：简刚冒出时上缘是湿的，张到位后收干
  float top = smoothstep(0.80, 1.0, vUV.y);
  c = mix(c, vec3(0.34, 0.29, 0.21), top * (1.0 - vPi) * 0.5);

  // 归拢到宣纸色调：原图是按「新竹」的艳黄拍的，直接铺满会把整页的米白调子
  // 拽成一片金；先抽掉一半饱和度，再并入宣纸底色，才读得出是「旧竹简」。
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(c, vec3(lum), 0.45);
  c = mix(c, vec3(0.953, 0.922, 0.867), 0.42);

  // 极细颗粒，抵消大色块的塑料感
  c += (h21(gl_FragCoord.xy) - 0.5) * 0.022;

  gl_FragColor = vec4(c, smoothstep(0.0, 0.12, vPi));
}`

function compile(g: WebGLRenderingContext, type: number, src: string) {
  const s = g.createShader(type)
  if (!s) return null
  g.shaderSource(s, src)
  g.compileShader(s)
  if (!g.getShaderParameter(s, g.COMPILE_STATUS)) {
    console.warn('[InkUnroll] shader', g.getShaderInfoLog(s))
    return null
  }
  return s
}

function texture(g: WebGLRenderingContext, img: HTMLImageElement) {
  const t = g.createTexture()
  g.bindTexture(g.TEXTURE_2D, t)
  g.pixelStorei(g.UNPACK_FLIP_Y_WEBGL, true)
  g.texImage2D(g.TEXTURE_2D, 0, g.RGB, g.RGB, g.UNSIGNED_BYTE, img)
  // 贴图非 2 的幂，只能 CLAMP + LINEAR，不能生成 mipmap
  g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE)
  g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE)
  g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.LINEAR)
  g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.LINEAR)
  return t
}

/** 背板尺寸按屏幕上实际占多少像素算（舞台有 0.85× 缩放的祖先变换，不能只看布局尺寸） */
function fit() {
  const c = cv.value
  if (!c || !gl || !prog) return
  const r = c.getBoundingClientRect()
  const w = Math.max(1, Math.round(Math.min(r.width * Math.min(devicePixelRatio, 2), MAXW)))
  const h = Math.max(1, Math.round(w * (r.height / Math.max(1, r.width))))
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h }
  // 单根简（不含缝）的宽高比 ÷ 贴图宽高比 = 需要横向裁取的贴图比例
  const pitch = r.width / props.count
  const slipW = pitch * (1 - 2 * props.gap)
  const crop = Math.min(1, (slipW * 1536) / (Math.max(1, r.height) * 1024))
  gl.useProgram(prog)
  gl.uniform1f(uni.uCrop, crop)
  gl.uniform1f(uni.uGap, props.gap)
  gl.uniform1f(uni.uN, props.count)
  gl.uniform1f(uni.uDur, props.dur)
  gl.uniform1f(uni.uStag, props.count > 1 ? (1 - props.dur) / (props.count - 1) : 0)
}

function draw(now: number) {
  const g = gl
  if (!g || !prog || !ready) return
  g.useProgram(prog)
  g.uniform1f(uni.uP, props.drive.p)
  g.uniform1f(uni.uT, (now - t0) / 1000)
  g.viewport(0, 0, g.drawingBufferWidth, g.drawingBufferHeight)
  g.clearColor(0, 0, 0, 0)
  g.clear(g.COLOR_BUFFER_BIT)
  // 逐简一次 drawArrays：合成一条 TRIANGLE_STRIP 会把相邻简连成一片
  for (let i = 0; i < props.count; i++) g.drawArrays(g.TRIANGLE_STRIP, i * 4, 4)
}

function loop(now: number) {
  draw(now)
  // 开卷完成后墨痕还要收一收，多跑一段再停，省 GPU
  if (props.drive.p < 1) { raf = requestAnimationFrame(loop); return }
  if (!openedAt) openedAt = now
  raf = now - openedAt < 1600 ? requestAnimationFrame(loop) : 0
}

function kick() {
  if (props.drive.p < 1) openedAt = 0
  if (!raf) raf = requestAnimationFrame(loop)
}

function onResize() {
  fit()
  draw(performance.now())
}

onMounted(() => {
  const c = cv.value
  if (!c) return
  // data-gl 标出着色器走到了哪一步：ok 才由画布作画，否则父级显示 CSS 兜底竹席。
  // 无头环境、老显卡、被禁 WebGL 的浏览器都会走兜底，不能留一块空白面板。
  const g = c.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: true })
  if (!g) { c.dataset.gl = 'no-context'; return }
  gl = g
  const vs = compile(g, g.VERTEX_SHADER, VS)
  const fs = compile(g, g.FRAGMENT_SHADER, FS)
  if (!vs || !fs) { gl = null; c.dataset.gl = 'no-shader'; return }
  const p = g.createProgram()
  if (!p) { gl = null; c.dataset.gl = 'no-program'; return }
  g.attachShader(p, vs)
  g.attachShader(p, fs)
  g.linkProgram(p)
  if (!g.getProgramParameter(p, g.LINK_STATUS)) {
    console.warn('[InkUnroll] link', g.getProgramInfoLog(p))
    gl = null
    c.dataset.gl = 'no-link'
    return
  }
  prog = p
  g.useProgram(p)

  for (const k of ['uN', 'uP', 'uStag', 'uDur', 'uGap', 'uCrop', 'uT']) uni[k] = g.getUniformLocation(p, k)

  // 简面几何：每根简一个 quad，交错写进同一块缓冲
  const data = new Float32Array(props.count * 4 * 3)
  const quad = [[0, 0], [1, 0], [0, 1], [1, 1]]
  for (let i = 0; i < props.count; i++)
    for (let v = 0; v < 4; v++) {
      const o = (i * 4 + v) * 3
      data[o] = quad[v][0]
      data[o + 1] = quad[v][1]
      data[o + 2] = i
    }
  const buf = g.createBuffer()
  g.bindBuffer(g.ARRAY_BUFFER, buf)
  g.bufferData(g.ARRAY_BUFFER, data, g.STATIC_DRAW)
  const aPos = g.getAttribLocation(p, 'aPos')
  const aSlip = g.getAttribLocation(p, 'aSlip')
  g.enableVertexAttribArray(aPos)
  g.vertexAttribPointer(aPos, 2, g.FLOAT, false, 12, 0)
  g.enableVertexAttribArray(aSlip)
  g.vertexAttribPointer(aSlip, 1, g.FLOAT, false, 12, 8)

  // 贴图按简序轮换，绑到固定的三个单元
  const imgs = props.srcs.slice(0, 3).map((src) => {
    const im = new Image()
    im.src = src
    return im
  })
  let left = imgs.length
  const settled = () => {
    if (--left > 0) return
    const dead = imgs.some((im) => !im.naturalWidth)
    if (dead) { c.dataset.gl = 'no-image'; return }
    imgs.forEach((im, i) => {
      g.activeTexture(g.TEXTURE0 + i)
      texture(g, im)
      g.uniform1i(uni['uT' + i], i)
    })
    ready = true
    t0 = performance.now()
    fit()
    kick()
    c.dataset.gl = 'ok'
  }
  imgs.forEach((im) => {
    if (im.complete && im.naturalWidth) settled()
    else { im.onload = settled; im.onerror = settled }
  })

  g.enable(g.BLEND)
  g.blendFunc(g.SRC_ALPHA, g.ONE_MINUS_SRC_ALPHA)
  addEventListener('resize', onResize)
})

watch(() => props.count, fit)

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  raf = 0
  ready = false
  removeEventListener('resize', onResize)
})
</script>

<template>
  <canvas ref="cv" class="unroll" aria-hidden="true" />
</template>

<style scoped>
.unroll { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
