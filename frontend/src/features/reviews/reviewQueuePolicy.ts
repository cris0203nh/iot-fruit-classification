/** AG-056 I03: strict, side-effect-free API contracts and UI formatting. */
export type ReviewPriority = 'high' | 'normal'
export type ReviewProduct = 'mango' | 'tomate'
export type ReviewQueueFilters = {
  lot?: string
  product?: ReviewProduct
  priority?: ReviewPriority
  limit?: number
  offset?: number
}
export type ReviewQueueReason = {
  code: string
  priority: ReviewPriority
  imageId: string | null
  source: string
}
export type ReviewQueueItem = {
  evaluationId: string
  lotId: string
  pieceId: string
  product: ReviewProduct
  status: 'processing' | 'pending_review' | 'completed'
  registeredAt: string
  imageCount: number
  imageIds: string[]
  priority: ReviewPriority
  reasons: ReviewQueueReason[]
  ruleVersion: string
}
export type ReviewQueueResponse = {
  items: ReviewQueueItem[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
  counts: { high: number; normal: number; all: number }
  ruleVersion: string
}
const EVAL = /^E-\d{1,9}$/
const IMAGE = /^I-\d{1,9}$/
const VERSION = 'ag056-review-selection-v1'
const obj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) >= 0
const priority = (v: unknown): v is ReviewPriority => v === 'high' || v === 'normal'
const product = (v: unknown): v is ReviewProduct => v === 'mango' || v === 'tomate'
const reason = (v: unknown): v is ReviewQueueReason => obj(v) && typeof v.code === 'string'
  && v.code.length > 0 && priority(v.priority)
  && (v.imageId === null || typeof v.imageId === 'string' && IMAGE.test(v.imageId))
  && typeof v.source === 'string' && v.source.length > 0
const item = (v: unknown): v is ReviewQueueItem => obj(v) && typeof v.evaluationId === 'string'
  && EVAL.test(v.evaluationId) && typeof v.lotId === 'string' && v.lotId.length > 0
  && typeof v.pieceId === 'string' && product(v.product)
  && ['processing', 'pending_review', 'completed'].includes(String(v.status))
  && typeof v.registeredAt === 'string' && Number.isFinite(Date.parse(v.registeredAt))
  && integer(v.imageCount) && Array.isArray(v.imageIds)
  && v.imageIds.every((id: unknown) => typeof id === 'string' && IMAGE.test(id))
  && new Set(v.imageIds).size === v.imageIds.length && priority(v.priority)
  && Array.isArray(v.reasons) && v.reasons.length > 0 && v.reasons.every(reason)
  && v.reasons.some((r: ReviewQueueReason) => r.priority === v.priority)
  && v.ruleVersion === VERSION

/** Avoid silently displaying partial, inconsistent or invented queue metrics. */
export function parseReviewQueue(v: unknown, expected: { limit: number; offset: number }): ReviewQueueResponse {
  if (!obj(v) || !Array.isArray(v.items) || !v.items.every(item)
      || !integer(v.total) || !integer(v.limit) || !integer(v.offset)
      || v.limit !== expected.limit || v.offset !== expected.offset || v.limit < 1 || v.limit > 100
      || v.items.length > v.limit || v.items.length > Math.max(0, v.total - v.offset)
      || v.hasMore !== (v.offset + v.limit < v.total)
      || !obj(v.counts) || !integer(v.counts.high) || !integer(v.counts.normal)
      || !integer(v.counts.all) || v.counts.all !== v.counts.high + v.counts.normal
      || v.total > v.counts.all || v.ruleVersion !== VERSION) {
    throw new Error('La API devolvió una cola AG-056 inconsistente.')
  }
  const entries = v.items as ReviewQueueItem[]
  if (new Set(entries.map(x => x.evaluationId)).size !== entries.length) {
    throw new Error('La API devolvió evaluaciones duplicadas.')
  }
  return v as unknown as ReviewQueueResponse
}

export function buildReviewQueueQuery(f: ReviewQueueFilters): string {
  const lot = f.lot?.trim() ?? ''
  const limit = f.limit ?? 20
  const offset = f.offset ?? 0
  if (lot.length > 32 || (f.product !== undefined && !product(f.product))
      || (f.priority !== undefined && !priority(f.priority))
      || !Number.isSafeInteger(limit) || limit < 1 || limit > 100
      || !Number.isSafeInteger(offset) || offset < 0) {
    throw new Error('Filtros AG-056 inválidos.')
  }
  const p = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (lot) p.set('lot', lot)
  if (f.product) p.set('product', f.product)
  if (f.priority) p.set('priority', f.priority)
  return p.toString()
}

const DESCRIPTIONS: Record<string, string> = {
  acquisition_pending_review: 'Captura lista para revisión humana',
  acquisition_evidence_missing: 'Captura sin evidencia fotográfica',
  evidence_unavailable: 'Fotografía original no disponible o ilegible',
  manual_or_uncertain_detection: 'Se solicitó revisión manual de la detección',
  uncertain_detection: 'Detección automática incierta',
  unknown_detection_outcome: 'Resultado de detección no reconocido',
  uncertainty_without_image_identity: 'Incidencia sin identidad verificable de fotografía',
  source_not_in_evaluation: 'Fuente no asociada a esta evaluación',
  source_hash_unverified: 'No se pudo verificar la integridad de la fuente',
  source_hash_mismatch: 'El SHA-256 de la evidencia no coincide',
  quality_source_missing: 'La propuesta carece de fuentes verificables',
  quality_views_inconsistent: 'Inconsistencia entre las vistas analizadas',
  quality_view_missing: 'Falta el análisis de una vista',
  quality_analysis_requires_review: 'El análisis de calidad requiere intervención',
  quality_not_evaluable: 'Fotografía no evaluable por el modelo',
  quality_partial_coverage: 'Cobertura parcial de la fruta',
  quality_possible_e2: 'Propuesta experimental E2; sin confirmar',
  quality_disagreement: 'Las propuestas experimentales por vista difieren',
  quality_proposal_unconfirmed: 'Propuesta E0/E1/E2 experimental sin confirmación humana',
}
export function describeReviewReason(code: string): string {
  return DESCRIPTIONS[code] ?? `Revisión requerida (${code})`
}
export function mayRecordReview(status: ReviewQueueItem['status']): boolean {
  // Matches AG-038's current write contract; processing is read-only.
  return status === 'pending_review' || status === 'completed'
}
