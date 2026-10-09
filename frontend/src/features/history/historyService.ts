/**
 * Modelo interno del frontend. Contrato PROVISIONAL: debe acordarse con Backend
 * antes de implementar una API o persistir resultados.
 */
export type EvaluatedProduct = 'mango' | 'tomate'
export type EvaluationStatus = 'completed' | 'pending_review' | 'error' | 'cancelled'

export type EvaluationSummary = {
  id: string
  lotId: string
  pieceId: string
  product: EvaluatedProduct
  registeredAt: string // Fecha ISO-8601 reportada por el backend
  status: EvaluationStatus
  weightGrams: number | null
  imageCount: number
}

export type EvaluationDetail = EvaluationSummary & {
  // Las URLs o identificadores de evidencia deberán resolverse desde la API real.
  evidence: Array<{ id: string; view: string; imageUrl: string }>
  visualCategory: string | null
  reviewNote: string | null
}

export type HistoryService = {
  list: () => Promise<EvaluationSummary[]>
  getById: (id: string) => Promise<EvaluationDetail | null>
}

export class HistoryNotConnectedError extends Error {
  constructor() {
    super('El historial todavía no dispone de un servicio conectado.')
    this.name = 'HistoryNotConnectedError'
  }
}

/**
 * Sin datos falsos ni llamadas a endpoints no acordados.
 * Josmely podrá sustituir estos métodos cuando se defina el contrato API.
 */
export const historyService: HistoryService = {
  async list() {
    throw new HistoryNotConnectedError()
  },
  async getById() {
    throw new HistoryNotConnectedError()
  },
}

export const HISTORY_STATUS_LABELS: Record<EvaluationStatus, string> = {
  completed: 'Completada',
  pending_review: 'Por revisar',
  error: 'Error',
  cancelled: 'Anulada',
}

export function formatWeight(weightGrams: number | null): string {
  if (weightGrams === null || !Number.isFinite(weightGrams) || weightGrams < 0) return 'No disponible'
  return `${new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 }).format(weightGrams)} g`
}

export function formatDate(isoDate: string): string {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return 'No disponible'
  return new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export type HistoryFilters = {
  query: string
  product: '' | EvaluatedProduct
  status: '' | EvaluationStatus
}

export function filterHistory(items: EvaluationSummary[], filters: HistoryFilters): EvaluationSummary[] {
  const query = filters.query.trim().toLocaleLowerCase('es-PE')
  return items.filter((item) => {
    const matchesText = !query || [item.id, item.lotId, item.pieceId]
      .some((value) => value.toLocaleLowerCase('es-PE').includes(query))
    return matchesText
      && (!filters.product || item.product === filters.product)
      && (!filters.status || item.status === filters.status)
  })
}
