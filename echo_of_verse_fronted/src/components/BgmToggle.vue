<script setup lang="ts">
import { computed } from 'vue'
import { route } from '../router'
import { bgmMuted, toggleBgmMute } from '../store/bgm'

// 游戏内页面（与 BgmPlayer 保持一致）不显示开关
const HIDDEN_ROUTES = new Set(['hud', 'poem'])
const visible = computed(() => !HIDDEN_ROUTES.has(route.value))
</script>

<template>
  <button
    v-if="visible"
    class="bgm-toggle"
    :class="{ muted: bgmMuted }"
    :aria-label="bgmMuted ? '开启音乐' : '关闭音乐'"
    :title="bgmMuted ? '开启音乐' : '关闭音乐'"
    @click="toggleBgmMute"
  >
    <!-- 音符图标：开启态 -->
    <svg v-if="!bgmMuted" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M9 18V6l11-2v12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.8"/>
      <circle cx="17" cy="16" r="3" stroke="currentColor" stroke-width="1.8"/>
    </svg>
    <!-- 静音图标：关闭态（带划线） -->
    <svg v-else viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M9 18V6l11-2v12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="6" cy="18" r="3" stroke="currentColor" stroke-width="1.8"/>
      <circle cx="17" cy="16" r="3" stroke="currentColor" stroke-width="1.8"/>
      <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  </button>
</template>

<style scoped>
.bgm-toggle {
  position: fixed;
  bottom: 48px;
  right: 48px;
  z-index: 200;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1.5px solid rgba(36, 55, 70, 0.35);
  background: rgba(243, 235, 221, 0.72);
  color: var(--indigo, #243746);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: background 160ms, border-color 160ms, opacity 160ms, transform 160ms;
  opacity: 0.7;
}
.bgm-toggle svg {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
.bgm-toggle:hover {
  opacity: 1;
  background: rgba(243, 235, 221, 0.92);
  border-color: rgba(36, 55, 70, 0.6);
}
.bgm-toggle:active {
  transform: scale(0.92);
}
.bgm-toggle:focus-visible {
  outline: 2px solid var(--cinnabar, #A84437);
  outline-offset: 3px;
}
.bgm-toggle.muted {
  color: rgba(36, 55, 70, 0.45);
  border-color: rgba(36, 55, 70, 0.2);
}
</style>
