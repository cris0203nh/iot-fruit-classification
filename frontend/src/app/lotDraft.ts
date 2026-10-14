/** El state de navegación transporta referencias: solo una consulta a la API confirma que el lote existe y está abierto. */
export type FruitProduct = 'mango' | 'tomate'

export type LotDraft = {
  product: FruitProduct
  lot: string
}

const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$/

export function isValidReference(value: string): boolean {
  return REFERENCE_PATTERN.test(value.trim())
}

/** Nunca confiar en state de navegación sin comprobar su estructura. */
export function readLotDraftState(state: unknown): LotDraft | null {
  if (typeof state !== 'object' || state === null || !('lotDraft' in state)) return null
  const draft: unknown = state.lotDraft
  if (typeof draft !== 'object' || draft === null || !('product' in draft) || !('lot' in draft)) return null
  const { product, lot } = draft
  if ((product !== 'mango' && product !== 'tomate') || typeof lot !== 'string' || !isValidReference(lot)) return null
  return { product, lot: lot.trim() }
}
