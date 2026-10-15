import { ref } from 'vue'
import { poemById, type Poem } from '../data/poems'

/**
 * 存档：3 个卷轴位，落在 localStorage。
 * 无后端，无跨设备能力；清缓存即失。
 */

export interface SaveSlot {
  poemId: string
  /** 已体验到第几句（0-based）；之前为已体验，等于者为当前，之后为后续 */
  lineIndex: number
  /** 0..2 */
  act: number
  /** epoch ms */
  savedAt: number
}

const KEY = 'eov:saves:v1'
export const SLOT_COUNT = 3

type Raw = (SaveSlot | null)[]

/** 因诗库增删而失效的旧存档（仍留在 localStorage，但诗篇已不存在） */
export interface Orphan { slot: number; poemId: string; savedAt: number }
export const orphans = ref<Orphan[]>([])

function read(): Raw {
  const empty: Raw = Array.from({ length: SLOT_COUNT }, () => null)
  const dropped: Orphan[] = []
  try {
    const s = localStorage.getItem(KEY)
    if (!s) return empty
    const parsed: unknown = JSON.parse(s)
    if (!Array.isArray(parsed)) return empty
    return empty.map((_, i) => {
      const v = parsed[i] as Partial<SaveSlot> | null | undefined
      if (!v || typeof v.poemId !== 'string') return null
      // 诗库增删后旧存档可能指向已不存在的篇目 → 该位失效，标记为「佚」
      if (!poemById(v.poemId)) {
        dropped.push({ slot: i, poemId: v.poemId, savedAt: Number(v.savedAt) || 0 })
        return null
      }
      return {
        poemId: v.poemId,
        lineIndex: Math.max(0, Number(v.lineIndex) || 0),
        act: Math.min(2, Math.max(0, Number(v.act) || 0)),
        savedAt: Number(v.savedAt) || Date.now(),
      }
    })
  } catch {
    return empty
  } finally {
    orphans.value = dropped
  }
}

/** 响应式存档位，供卷轴页直接渲染 */
export const slots = ref<Raw>(read())

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(slots.value))
  } catch {
    /* 隐私模式 / 配额满：忽略，内存态仍可用 */
  }
}

export function reload() {
  slots.value = read()
}

export function load(): Raw {
  return read()
}

export function write(slot: number, data: Omit<SaveSlot, 'savedAt'> & { savedAt?: number }) {
  if (slot < 0 || slot >= SLOT_COUNT) return
  slots.value[slot] = { ...data, savedAt: data.savedAt ?? Date.now() }
  persist()
}

export function clear(slot: number) {
  if (slot < 0 || slot >= SLOT_COUNT) return
  slots.value[slot] = null
  persist()
}

/** 最近一次写入的存档位号，无存档时返回 -1（首页「继续诗境」用） */
export function latest(): number {
  let best = -1
  slots.value.forEach((s, i) => {
    if (s && (best < 0 || s.savedAt > slots.value[best]!.savedAt)) best = i
  })
  return best
}

/** 认领一个存档位：优先空位，全满则覆盖最旧的一卷 */
export function claimSlot(): number {
  const free = slots.value.findIndex((s) => !s)
  if (free >= 0) return free
  let oldest = 0
  slots.value.forEach((s, i) => {
    if (s && s.savedAt < (slots.value[oldest]?.savedAt ?? Infinity)) oldest = i
  })
  return oldest
}

export function resolvePoem(slot: number): Poem | undefined {
  return poemById(slots.value[slot]?.poemId)
}

export function fmtTime(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
