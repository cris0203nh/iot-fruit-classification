/** Contrato de EvaluationCreate.pieceId en backend/app/evaluation_schemas.py. */
const PIECE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/

export function isValidPieceId(value: string): boolean {
  return PIECE_ID_PATTERN.test(value.trim())
}
