import type { LotRecord } from '../../services/agroscanApi'

export type LotStatusFilter = 'all' | 'open' | 'closed'

/** Filtro visual: no modifica datos ni vuelve a consultar la API. */
export function filterVisibleLots(
  lots: readonly LotRecord[],
  search: string,
  status: LotStatusFilter,
): LotRecord[] {
  const term = search.trim().toLowerCase()
  return lots.filter((lot) => {
    if (status !== 'all' && lot.status !== status) return false
    return !term || lot.code.toLowerCase().includes(term)
  })
}
