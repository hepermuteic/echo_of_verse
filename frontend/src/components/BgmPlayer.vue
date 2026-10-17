<script setup lang="ts">
import { watch, onMounted, onBeforeUnmount } from 'vue'
import { route } from '../router'
import { bgmVolume, bgmMuted } from '../store/bgm'

// 游戏内页面静音（诗篇阅读中 + 局内 HUD）
const SILENT_ROUTES = new Set(['hud', 'poem'])

const SRC = '/audio/bgm.mp3'
const FADE_STEP_MS = 30
const FADE_DURATION = 1200

let audio: HTMLAudioElement | null = null
let fadeTimer: ReturnType<typeof setInterval> | null = null
let started = false

function targetVolume(): number {
  if (bgmMuted.value) return 0
  if (SILENT_ROUTES.has(route.value)) return 0
  return bgmVolume.value / 100
}

function clearFade() {
  if (fadeTimer !== null) { clearInterval(fadeTimer); fadeTimer = null }
}

function fadeTo(target: number) {
  if (!audio) return
  clearFade()
  const steps = Math.ceil(FADE_DURATION / FADE_STEP_MS)
  const start = audio.volume
  const delta = (target - start) / steps
  let step = 0
  fadeTimer = setInterval(() => {
    if (!audio) { clearFade(); return }
    step++
    audio.volume = Math.min(1, Math.max(0, start + delta * step))
    if (step >= steps) {
      audio.volume = target
      clearFade()
      if (target === 0) audio.pause()
    }
  }, FADE_STEP_MS)
}

function onInteraction() {
  if (!audio || started) return
  document.removeEventListener('pointerdown', onInteraction, { capture: true })
  document.removeEventListener('keydown', onInteraction, { capture: true })
  audio.play().then(() => {
    started = true
    fadeTo(targetVolume())
  }).catch(() => {})
}

onMounted(() => {
  audio = new Audio(SRC)
  audio.loop = true
  audio.volume = 0

  document.addEventListener('pointerdown', onInteraction, { capture: true })
  document.addEventListener('keydown', onInteraction, { capture: true })

  audio.play().then(() => {
    started = true
    document.removeEventListener('pointerdown', onInteraction, { capture: true })
    document.removeEventListener('keydown', onInteraction, { capture: true })
    fadeTo(targetVolume())
  }).catch(() => {})
})

onBeforeUnmount(() => {
  clearFade()
  document.removeEventListener('pointerdown', onInteraction, { capture: true })
  document.removeEventListener('keydown', onInteraction, { capture: true })
  audio?.pause()
  audio = null
})

// 路由切换 → 淡入/淡出
watch(route, () => {
  if (!audio || !started) return
  const vol = targetVolume()
  if (vol > 0 && audio.paused) {
    audio.play().catch(() => {})
    fadeTo(vol)
  } else {
    fadeTo(vol)
  }
})

// 音量或静音开关变化 → 实时更新
watch([bgmVolume, bgmMuted], () => {
  if (!audio || !started) return
  if (SILENT_ROUTES.has(route.value)) return
  const vol = targetVolume()
  clearFade()
  audio.volume = vol
  if (audio.paused && vol > 0) audio.play().catch(() => {})
  else if (vol === 0) audio.pause()
})
</script>

<template><!-- 无 DOM，纯逻辑组件 --></template>
