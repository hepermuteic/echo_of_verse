// 仅用于开发审查：?audit 时检测溢出 / 重叠 / 居中，结果写入 #audit-out
export function runAudit() {
  const out: string[] = []
  const stage = document.querySelector('.stage') as HTMLElement
  const sr = stage.getBoundingClientRect()
  out.push(`stage ${Math.round(sr.left)},${Math.round(sr.top)} ${Math.round(sr.width)}x${Math.round(sr.height)} vp ${innerWidth}x${innerHeight}`)
  const sheet = document.querySelector('.panel, .sheet') as HTMLElement | null
  if (sheet) {
    const r = sheet.getBoundingClientRect()
    out.push(`panel center dx=${Math.round(r.left + r.width / 2 - innerWidth / 2)} dy=${Math.round(r.top + r.height / 2 - innerHeight / 2)}`)
  }

  /* ---- 诗篇页专用：竖排列心是否压在竹简简心上、是否出简 ----
     舞台有 SHRINK 缩放，getBoundingClientRect 拿到的是设备像素，
     必须先除以 k 换算回 1920×1080 布局坐标，否则每个数字都失真。 */
  const vb = stage.querySelector('.verse-block') as HTMLElement | null
  if (vb) {
    const k = sr.width / 1920
    const pitch = parseFloat(getComputedStyle(vb).getPropertyValue('--pitch')) || 0
    const panel = vb.closest('.panel') as HTMLElement
    const inner = vb.closest('.inner') as HTMLElement
    const pr = panel.getBoundingClientRect()
    const ir = inner.getBoundingClientRect()
    const ics = getComputedStyle(inner)
    // .inner 的内容盒高度 = 真正可用的净高（不含自身内边距）
    const innerH = (ir.height - parseFloat(ics.paddingTop) - parseFloat(ics.paddingBottom)) / k
    const cols = Array.from(vb.querySelectorAll<HTMLElement>('.vline'))
    const txt = cols[0]?.querySelector<HTMLElement>('.line-text')
    const fs = txt ? parseFloat(getComputedStyle(txt).fontSize) : 0
    const vr = vb.getBoundingClientRect()
    out.push(`POEM fs=${fs}px cols=${cols.length} pitch=${pitch.toFixed(1)} 净高=${Math.round(innerH)} 列容量=${Math.floor(innerH / (fs * 1.36))}字`)
    // 每列文字实高 vs 可用净高
    let worst = 0
    let worstTx = ''
    const drift: string[] = []
    cols.forEach((c, i) => {
      const r = c.getBoundingClientRect()
      const center = (r.left + r.width / 2 - pr.left) / k
      const ki = Math.round(center / pitch - 0.5)
      const d = center - (ki + 0.5) * pitch
      if (Math.abs(d) > 1) drift.push(`#${i}=${d > 0 ? '+' : ''}${d.toFixed(1)}`)
      const t = c.querySelector<HTMLElement>('.line-text')
      const th = t ? t.getBoundingClientRect().height / k : 0
      if (th > worst) { worst = th; worstTx = t?.textContent?.slice(0, 10) ?? '' }
    })
    out.push(`POEM-FIT 最长列="${worstTx}" 高=${Math.round(worst)} 净高=${Math.round(innerH)} ${worst > innerH + 1 ? '溢出!' : 'ok'}`)
    out.push(drift.length ? `POEM-ALIGN 偏离简心 ${drift.join(' ')}` : 'POEM-ALIGN ok')
    const l = (vr.left - pr.left) / k
    const rb = (vr.right - pr.left) / k
    out.push(`POEM-BOX 块左=${Math.round(l)} 块右=${Math.round(rb)} 简宽=${Math.round(pr.width / k)} ${l < -1 || rb > pr.width / k + 1 ? '出简!' : 'ok'}`)
  }
  const els = Array.from(stage.querySelectorAll<HTMLElement>('h1,h2,h3,h4,p,li,button,summary,span,label,output,em,small,kbd'))
    .filter((e) => e.offsetParent !== null && e.textContent!.trim() && e.getBoundingClientRect().width > 0)
  const k = sr.width / 1920
  for (const e of els) {
    if (e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).display !== 'inline') out.push(`OVERFLOW-X ${e.className}|${e.textContent!.trim().slice(0, 14)}`)
    if (e.scrollHeight > e.clientHeight + 2 && getComputedStyle(e).display !== 'inline') out.push(`OVERFLOW-Y ${e.className}|${e.textContent!.trim().slice(0, 14)}`)
    const r = e.getBoundingClientRect()
    if (r.right > sr.right + 1 || r.bottom > sr.bottom + 1 || r.left < sr.left - 1 || r.top < sr.top - 1) out.push(`OFFSTAGE ${e.textContent!.trim().slice(0, 14)}`)
  }
  for (const e of Array.from(stage.querySelectorAll<HTMLElement>('*'))) {
    if (e.closest('svg,canvas')) continue
    const cs = getComputedStyle(e)
    // layer / persp / world / scene 是分层景（scene 即场所背板）：其子层按比例放大是为了
    // 视差移动时四周不露图边，多出的可滚动区由自身 overflow:hidden 裁掉，非真实溢出。
    if (cs.position === 'absolute' && e.children.length && e.scrollHeight > e.clientHeight + 2 && e.clientHeight > 0 && !e.classList.contains('layer') && !e.classList.contains('persp') && !e.classList.contains('world') && !e.classList.contains('scene')) out.push(`BOX-OVERFLOW ${e.className} sh=${e.scrollHeight} ch=${e.clientHeight}`)
  }
  // 叶子文本块之间的重叠
  const leaves = els.filter((e) => !Array.from(e.children).some((c) => (c as HTMLElement).textContent!.trim()) || e.tagName === 'BUTTON')
  const rect = (e: HTMLElement) => { const r = e.getBoundingClientRect(); return { l: r.left / k, r: r.right / k, t: r.top / k, b: r.bottom / k } }
  for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
    const a = leaves[i], b = leaves[j]
    if (a.contains(b) || b.contains(a)) continue
    const A = rect(a), B = rect(b)
    const ox = Math.min(A.r, B.r) - Math.max(A.l, B.l), oy = Math.min(A.b, B.b) - Math.max(A.t, B.t)
    if (ox > 4 && oy > 4) out.push(`OVERLAP ${a.textContent!.trim().slice(0, 10)} × ${b.textContent!.trim().slice(0, 10)} (${Math.round(ox)}x${Math.round(oy)})`)
  }
  const pre = document.createElement('pre'); pre.id = 'audit-out'; pre.textContent = out.join('\n'); document.body.appendChild(pre)
}
