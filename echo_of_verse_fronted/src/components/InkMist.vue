<script setup lang="ts">
// 水墨雾气着色器：低频 fbm 噪声缓慢流动，极低透明度叠加。WebGL 不可用时静默退化。
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{ tint?: string; strength?: number; speed?: number }>(), {
  tint: '#a9c0c4',
  strength: 0.35,
  speed: 0.04,
})
const cv = ref<HTMLCanvasElement>()
let raf = 0

const VS = `attribute vec2 p; varying vec2 uv; void main(){ uv = p*.5+.5; gl_Position = vec4(p,0.,1.); }`
const FS = `precision mediump float; varying vec2 uv; uniform float t; uniform vec3 tint; uniform float k;
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float n(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(h(i),h(i+vec2(1,0)),f.x), mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float a=.5, s=0.; for(int i=0;i<5;i++){ s+=a*n(p); p=p*2.02+vec2(1.7,9.2); a*=.5; } return s; }
void main(){
  vec2 p = uv*vec2(3.2,1.8);
  float q = fbm(p + vec2(t, -t*.6));
  float m = fbm(p*1.3 + q*1.6 + vec2(-t*.7, t*.3));
  float band = smoothstep(.0,.55,uv.y) * (1.-smoothstep(.55,1.,uv.y)) ;   // 偏中下部的雾带
  float a = smoothstep(.38,.8,m) * (.35+band*.9) * k;
  gl_FragColor = vec4(tint*a, a);
}`

onMounted(() => {
  const c = cv.value!
  const gl = c.getContext('webgl', { premultipliedAlpha: true, alpha: true })
  if (!gl) return
  const sh = (type: number, src: string) => {
    const s = gl.createShader(type)!
    gl.shaderSource(s, src); gl.compileShader(s); return s
  }
  const prog = gl.createProgram()!
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS))
  gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS))
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return
  gl.useProgram(prog)
  const buf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, buf)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
  const loc = gl.getAttribLocation(prog, 'p')
  gl.enableVertexAttribArray(loc)
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
  const hex = props.tint.replace('#', '')
  const rgb = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  gl.uniform3f(gl.getUniformLocation(prog, 'tint'), rgb[0], rgb[1], rgb[2])
  gl.uniform1f(gl.getUniformLocation(prog, 'k'), props.strength)
  const ut = gl.getUniformLocation(prog, 't')
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const t0 = performance.now()
  const frame = () => {
    gl.viewport(0, 0, c.width, c.height)
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(ut, reduce ? 3 : 3 + ((performance.now() - t0) / 1000) * props.speed)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    if (!reduce) raf = requestAnimationFrame(frame)
  }
  frame()
})
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <canvas ref="cv" class="ink-mist" width="960" height="540" aria-hidden="true" />
</template>

<style scoped>
.ink-mist { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
