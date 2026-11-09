/** AG-040: evita aceptar totales inflados o identidades repetidas desde la API. */
export type PieceAggregate = {
  lotCode: string
  pieceCode: string
  attemptCount: number
  captureCount: number
  reviewEventCount: number
  automaticAssessmentCount: number
}

export function validatePieceAggregates(
  pieces: PieceAggregate[],
  expected: { pieceCount: number; attemptCount: number; captureCount: number },
): boolean {
  const keys = new Set<string>()
  let attempts = 0
  let captures = 0
  for (const piece of pieces) {
    const key = JSON.stringify([piece.lotCode, piece.pieceCode])
    if (keys.has(key) || !piece.lotCode || !piece.pieceCode) return false
    keys.add(key)
    for (const count of [piece.attemptCount, piece.captureCount, piece.reviewEventCount, piece.automaticAssessmentCount]) {
      if (!Number.isSafeInteger(count) || count < 0) return false
    }
    attempts += piece.attemptCount
    captures += piece.captureCount
  }
  return pieces.length === expected.pieceCount
    && attempts === expected.attemptCount
    && captures === expected.captureCount
}
