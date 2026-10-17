import { ref, watch } from 'vue'

const KEY = 'eov:bgm:v1'
const MUTE_KEY = 'eov:bgm:mute:v1'
const DEFAULT_VOL = 20   // 首次试听轻声约 20%，用户可在设置中调整

function load(): number {
  try {
    const v = localStorage.getItem(KEY)
    if (v !== null) return Math.min(100, Math.max(0, Number(v)))
  } catch { /* 隐私模式 / 安全策略：忽略 */ }
  return DEFAULT_VOL
}

function loadMuted(): boolean {
  try { return localStorage.getItem(MUTE_KEY) === '1' } catch { return false }
}

/** 音乐音量（0–100），自动持久化到 localStorage */
export const bgmVolume = ref<number>(load())
/** 音乐开关，自动持久化到 localStorage */
export const bgmMuted = ref<boolean>(loadMuted())

watch(bgmVolume, (v) => {
  try { localStorage.setItem(KEY, String(v)) } catch { /* 忽略 */ }
})

watch(bgmMuted, (v) => {
  try { localStorage.setItem(MUTE_KEY, v ? '1' : '0') } catch { /* 忽略 */ }
})

export function setBgmVolume(v: number) {
  bgmVolume.value = Math.min(100, Math.max(0, v))
}

export function toggleBgmMute() {
  bgmMuted.value = !bgmMuted.value
}
