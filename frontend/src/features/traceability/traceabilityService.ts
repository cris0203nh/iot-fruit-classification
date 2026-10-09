import type { EvaluationDetail } from '../history/historyService'

/**
 * Contrato provisional para consulta de trazabilidad, pendiente de acordar
 * con Backend. No representa endpoints existentes ni datos persistidos.
 */
export type ReviewEvent = {
  id: string
  performedAt: string // ISO-8601
  actorId: string
  type: 'review' | 'cancellation'
  reason: string
  previousValue: string | null
  updatedValue: string | null
}

export type TraceabilityRecord = {
  evaluation: EvaluationDetail
  calibrationReference: string | null
  modelVersion: string | null
  rulesVersion: string | null
  reviews: ReviewEvent[]
}

export type TimelineEntry = {
  id: string
  at: string
  kind: 'original' | ReviewEvent['type']
  title: string
  actorId: string | null
  reason: string | null
  previousValue: string | null
  updatedValue: string | null
}

export class TraceabilityNotConnectedError extends Error {
  constructor() {
    super('No hay una API de trazabilidad conectada.')
    this.name = 'TraceabilityNotConnectedError'
  }
}

export interface TraceabilityService {
  getByEvaluationId(evaluationId: string): Promise<TraceabilityRecord | null>
}

export const traceabilityService: TraceabilityService = {
  async getByEvaluationId() {
    throw new TraceabilityNotConnectedError()
  },
}

/** Solo referencias opacas sin separadores de ruta ni espacios. */
export function validateEvaluationId(input: string): string | null {
  const id = input.trim()
  return /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(id) ? id : null
}

/**
 * La primera entrada corresponde siempre al registro original.
 * Las revisiones se agregan sin alterar los datos originales.
 */
export function buildTraceabilityTimeline(record: TraceabilityRecord): TimelineEntry[] {
  const original: TimelineEntry = {
    id: `original:${record.evaluation.id}`,
    at: record.evaluation.registeredAt,
    kind: 'original',
    title: 'Registro original',
    actorId: null,
    reason: null,
    previousValue: null,
    updatedValue: record.evaluation.visualCategory,
  }
  const reviews: TimelineEntry[] = record.reviews
    .map((event) => ({
      id: event.id,
      at: event.performedAt,
      kind: event.type,
      title: event.type === 'review' ? 'Revisión registrada' : 'Anulación registrada',
      actorId: event.actorId,
      reason: event.reason,
      previousValue: event.previousValue,
      updatedValue: event.updatedValue,
    }))
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
  return [original, ...reviews]
}
