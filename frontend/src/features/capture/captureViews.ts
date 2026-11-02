/** Siguiente etiqueta de vista según la evidencia persistida, nunca según un contador local de tomas. */
export function nextCaptureView(views: readonly string[]): string {
  let last = 0
  for (const value of views) {
    const match = /^vista-([1-9]\d*)$/.exec(value)
    if (match) last = Math.max(last, Number(match[1]))
  }
  return `vista-${last + 1}`
}
