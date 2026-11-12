/** AG-054: la caja describe proyecciones en pixeles, NO dimensiones fisicas. */
export function projectedBoundingSize(box: readonly number[]): { widthPx: number; heightPx: number } | null {
  if (box.length !== 4 || !box.every(Number.isFinite)) return null
  const widthPx = box[2] - box[0]
  const heightPx = box[3] - box[1]
  if (widthPx <= 0 || heightPx <= 0) return null
  return { widthPx, heightPx }
}
