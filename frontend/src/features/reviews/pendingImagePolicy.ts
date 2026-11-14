/** AG-056 I04: choose only an eligible pending photo, without mutating evidence. */
export function eligibleReviewImages<T extends { id: string }>(
  evidence: readonly T[],
  pendingImageIds?: readonly string[],
): T[] {
  if (!pendingImageIds?.length) return [...evidence]
  const allowed = new Set(pendingImageIds)
  return evidence.filter(image => allowed.has(image.id))
}

/** Prefer the unreviewed image; preserve an explicit, still-eligible selection. */
export function chooseReviewImage(
  evidence: readonly { id: string }[],
  decisions: readonly { imageId: string }[],
  selection = '',
): string {
  if (selection && evidence.some(image => image.id === selection)) return selection
  const reviewed = new Set(decisions.map(item => item.imageId))
  return evidence.find(image => !reviewed.has(image.id))?.id ?? evidence[0]?.id ?? ''
}
