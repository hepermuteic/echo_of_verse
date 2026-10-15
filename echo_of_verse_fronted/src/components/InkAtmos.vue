<script setup lang="ts">
/**
 * 墨气 · WebGL 着色器
 *
 * 给「场所背景」添活气的一层，两项效果共用一套 fbm：
 *   雾气 — 低频噪声缓慢游移，覆在远景与中景之间，把底图从「一张平图」读成「一层空间」；
 *   水晕 — 更高的频段取阈值后作同心扩散，读作水面被风揉出的细纹与波光。
 *
 * `flow` 为 0 时只剩雾；大于 0 时雾的噪声整体沿 x 缓慢平移，读作水流。
 * 与 InkMist 的区别：这层支持贴图调制（可由底图的明暗决定哪里更浓），
 * 并按「屏幕空间 + 视差偏移」取噪声，因此可以与父级的分层视差同拍。
 *
 * WebGL 不可用时静默退化：画布保持透明，页面照常显示。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    tint?: string
    /** 全层浓度上限 */
    strength?: number
    /** 噪声游移速度 */
    speed?: number
    /** 水纹强度：0 则只作雾 */
    ripple?: number
    /** 水流速度：>0 时雾沿 x 平移（江面 / 水岸用） */
    flow?: number
    /** 底图地址：给出后由底图明暗调制雾的浓淡（暗处更浓），留空则均匀铺开 */
    src?: string
    /** 视差偏移，-1..1，由父级每帧写入（普通对象，不走响应式）；不给则恒为 0 */
    drive?: { x: number; y: number }
  }>(),
  { tint: '#9fb8bd', strength: 0.3, speed: 0.05, ripple: 0, flow: 0, src: '' },
)

const cv = ref<HTMLCanvasElement>()
let raf = 0
let ready = false

const VS = `attribute vec2 p; varying vec2 uv; void main(){ uv = p*.5+.5; gl_Position = vec4(p,0.,1.); }`

const FS = `
precision mediump float;
varying vec2 uv;
uniform float t;
uniform vec3 tint;
uniform float k;
uniform float rip;
uniform float flow;
uniform vec2 par;      // 视差偏移
uniform sampler2D mod;  // 底图（明暗调制用）
uniform float hasMod;

float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float nz(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x),
             mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 q){
  float a = 0.5, s = 0.0;
  for (int i = 0; i < 5; i++) { s += a * nz(q); q = q * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
  return s;
}

void main() {
  // 屏幕坐标，含视差：噪声随之轻微位移，视差层才有「厚度」
  vec2 sp = uv + par * 0.035;
  vec2 q = sp * vec2(3.0, 1.7) + vec2(t * flow, -t * 0.55);

  // ---- 雾：两层 fbm 域扭曲，得到缓慢翻卷的墨气 ----
  float a1 = fbm(q);
  float a2 = fbm(q * 1.35 + vec2(a1 * 1.5, -t * 0.3));
  float mist = smoothstep(0.36, 0.82, a2);

  // 雾带：偏中下部浓、上下缘收，避免压住页首标题
  float band = smoothstep(0.0, 0.42, uv.y) * (1.0 - smoothstep(0.72, 1.0, uv.y));
  mist *= 0.34 + band * 0.9;

  // 底图明暗调制：暗处墨气更重（水面上更明显），亮处近乎消失
  if (hasMod > 0.5) {
    vec3 c = texture2D(mod, uv).rgb;
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    mist *= mix(1.25, 0.45, smoothstep(0.30, 0.92, lum));
  }

  // ---- 水晕：噪声域内取曲率，读作被风揉出的细纹；只在噪声高处起纹，其余留白 ----
  float water = 0.0;
  if (rip > 0.0) {
    // 拖长 x、压缩 y：水纹横向延展，而非等向的斑块
    vec2 w = sp * vec2(9.0, 2.6) + vec2(t * (0.05 + flow * 2.0), 0.0);
    float w1 = fbm(w);
    float pat = abs(sin(w1 * 23.0));   // w1 空间频率低，相乘后不会退化成平行细线
    float rr = smoothstep(0.22, 0.60, w1) * (0.40 + 0.60 * uv.y);
    water = smoothstep(0.55, 1.0, pat) * rr * rip;
  }

  float alpha = clamp((mist * k) + water * 0.5, 0.0, 1.0);
  // 水纹偏冷偏亮，雾偏 tint
  vec3 col = mix(tint, vec3(0.88, 0.93, 0.94), water * 0.6);
  gl_FragColor = vec4(col * alpha, alpha);
}`

onMounted(() => {
  const c = cv.value
  if (!c) return
  const gl = c.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false })
  if (!gl) { c.dataset.gl = 'no-context'; return }

  const sh = (type: number, src: string) => {
    const s = gl.createShader(type)!
    gl.shaderSource(s, src); gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn('[InkAtmos]', gl.getShaderInfoLog(s)); return null }
    return s
  }
  const vs = sh(gl.VERTEX_SHADER, VS)
  const fs = sh(gl.FRAGMENT_SHADER, FS)
  if (!vs || !fs) { c.dataset.gl = 'no-shader'; return }
  const prog = gl.createProgram()!
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { c.dataset.gl = 'no-link'; return }
  gl.useProgram(prog)

  const buf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, buf)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
  const loc = gl.getAttribLocation(prog, 'p')
  gl.enableVertexAttribArray(loc)
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

  const hex = props.tint.replace('#', '')
  const rgb = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  gl.uniform3f(gl.getUniformLocation(prog, 'tint'), rgb[0], rgb[1], rgb[2])
  gl.uniform1f(gl.getUniformLocation(prog, 'k'), props.strength)
  gl.uniform1f(gl.getUniformLocation(prog, 'rip'), props.ripple)
  gl.uniform1f(gl.getUniformLocation(prog, 'flow'), props.flow)
  const uT = gl.getUniformLocation(prog, 't')
  const uPar = gl.getUniformLocation(prog, 'par')
  const uHas = gl.getUniformLocation(prog, 'hasMod')

  if (props.src) {
    const im = new Image()
    im.src = props.src
    const bind = () => {
      if (!im.naturalWidth) return
      const tx = gl.createTexture()
      gl.activeTexture(gl.TEXTURE0)
      gl.bindTexture(gl.TEXTURE_2D, tx)
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, im)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.uniform1i(gl.getUniformLocation(prog, 'mod'), 0)
      gl.uniform1f(uHas, 1)
      ready = true
    }
    if (im.complete && im.naturalWidth) bind()
    else { im.onload = bind; im.onerror = bind }
  } else {
    gl.uniform1f(uHas, 0)
    ready = true
  }

  gl.enable(gl.BLEND)
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const t0 = performance.now()
  const dpr = Math.min(devicePixelRatio, 2)
  const resizec = () => {
    const r = c.getBoundingClientRect()
    const w = Math.max(1, Math.round(Math.min(r.width * dpr, 1600)))
    const h = Math.max(1, Math.round(w * (r.height / Math.max(1, r.width))))
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h }
  }
  resizec()
  addEventListener('resize', resizec)

  const frame = () => {
    if (!ready) { raf = requestAnimationFrame(frame); return }
    gl.viewport(0, 0, c.width, c.height)
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(uT, reduce ? 4 : 4 + ((performance.now() - t0) / 1000) * props.speed)
    // 无 drive 即无视差：偏移恒为 0，雾与水纹仍按 uT 自行流动
    const d = props.drive
    gl.uniform2f(uPar, d ? d.x : 0, d ? d.y : 0)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    if (!reduce) raf = requestAnimationFrame(frame)
    else c.dataset.gl = 'static'
  }
  frame()
  c.dataset.gl = 'ok'
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  raf = 0
  ready = false
})
</script>

<template>
  <canvas ref="cv" class="ink-atmos" aria-hidden="true" />
</template>

<style scoped>
.ink-atmos { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
