<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { route, go, type RouteName } from './router'
import { params } from './router'
import BrushCursor from './components/BrushCursor.vue'
import BgmPlayer from './components/BgmPlayer.vue'
import BgmToggle from './components/BgmToggle.vue'
import HomePage from './pages/HomePage.vue'
import SelectPage from './pages/SelectPage.vue'
import PoemPage from './pages/PoemPage.vue'
import ArchivePage from './pages/ArchivePage.vue'
import HudPage from './pages/HudPage.vue'
import PausePage from './pages/PausePage.vue'
import EndingPage from './pages/EndingPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import CollectionPage from './pages/CollectionPage.vue'

const pages = { home: HomePage, select: SelectPage, poem: PoemPage, scroll: ArchivePage, hud: HudPage, pause: PausePage, ending: EndingPage, settings: SettingsPage, collection: CollectionPage }
const list: [RouteName, string][] = [['home', '首页'], ['select', '开启诗境'], ['poem', '诗篇'], ['scroll', '诗篇卷轴'], ['hud', '局内'], ['pause', '暂停'], ['ending', '此行心迹'], ['settings', '设置'], ['collection', '诗心拾遗']]

// 自适应：舞台等比缩放并居中；留边区域与页面底色一致，视觉上无黑边
const scale = ref(1)
const SHRINK = 0.85 // 整体等比缩小系数（1 = 铺满窗口）
const fit = () => (scale.value = Math.min(innerWidth / 1920, innerHeight / 1080) * SHRINK)
onMounted(() => { fit(); addEventListener('resize', fit) })
onBeforeUnmount(() => removeEventListener('resize', fit))

const cur = computed(() => pages[route.value])
const dark = computed(() => route.value === 'hud' || route.value === 'pause' && false)
/** 同路由但参数变化（如换诗、换档）也要重挂载，否则页面内状态会串 */
const pageKey = computed(() => route.value + '?' + JSON.stringify(params.value))
</script>

<template>
  <div class="stage-wrap" :class="[route, { dark }]">
    <div class="stage" :class="{ dark }" :style="{ transform: `translate(-50%, -50%) scale(${scale})` }">
      <component :is="cur" :key="pageKey" />
    </div>
  </div>
  <BgmPlayer />
  <BgmToggle />
  <BrushCursor :scale="scale" :dark="dark" />
  <nav class="preview-nav">
    <a v-for="[n, t] in list" :key="n" :href="'#/' + n" :class="{ on: route === n }" @click.prevent="go(n)">{{ t }}</a>
  </nav>
</template>
