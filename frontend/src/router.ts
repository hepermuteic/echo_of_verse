import { computed, ref } from 'vue'

export type RouteName =
  | 'home'
  | 'select'
  | 'poem'
  | 'scroll'
  | 'hud'
  | 'pause'
  | 'ending'
  | 'settings'
  | 'collection'

const NAMES: RouteName[] = ['home', 'select', 'poem', 'scroll', 'hud', 'pause', 'ending', 'settings', 'collection']

const hash = ref(window.location.hash)
window.addEventListener('hashchange', () => (hash.value = window.location.hash))

/** 解析 #/name?key=value&flag */
const parsed = computed(() => {
  const raw = hash.value.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  const params: Record<string, string> = {}
  query.split('&').filter(Boolean).forEach((kv) => {
    const [k, v = '1'] = kv.split('=')
    // 值可能含中文（如筛选条件），需解码后再比较
    let val = v
    try { val = decodeURIComponent(v) } catch { /* 非法转义：保留原值 */ }
    params[decodeURIComponent(k)] = val
  })
  return { name: (NAMES as string[]).includes(path) ? (path as RouteName) : 'home', params }
})

export const route = computed(() => parsed.value.name)
export const params = computed(() => parsed.value.params)

export function go(name: RouteName, query = '') {
  window.location.hash = `#/${name}${query ? '?' + query : ''}`
}
