import type { EvaluationDetail } from '../history/historyService'
import { getEvaluationTraceability } from '../../services/agroscanApi.ts'

/** Contrato de lectura alineado con TraceabilityOut de FastAPI. */
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

export interface TraceabilityService {
  getByEvaluationId(evaluationId: string): Promise<TraceabilityRecord | null>
}

/** No habilita POST de revisiones ni anulaciones: requieren autorización real. */
export const traceabilityService: TraceabilityService = {
  getByEvaluationId: getEvaluationTraceability,
}

/** Identificador publicado por FastAPI (backend/app/routers/evaluations.py). */
export function validateEvaluationId(input: string): string | null {
  const id = input.trim()
  return /^E-\d{1,9}$/.test(id) ? id : null
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
