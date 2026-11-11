
import type { EvaluationDetail } from '../history/historyService'
import {
  createEvaluationReview,
  getEvaluationTraceability,
  type EvaluationReviewInput,
} from '../../services/agroscanApi'


export type ReviewEvent = {
  id: string
  performedAt: string
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
  addReview(
    evaluationId: string,
    input: EvaluationReviewInput,
  ): Promise<ReviewEvent>
}


export const traceabilityService: TraceabilityService = {
  getByEvaluationId: getEvaluationTraceability,
  addReview: createEvaluationReview,
}


export function validateEvaluationId(input: string): string | null {
  const id = input.trim()
  return /^E-\d{1,9}$/.test(id) ? id : null
}

export function buildTraceabilityTimeline(
  record: TraceabilityRecord,
): TimelineEntry[] {
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
      title: event.type === 'review'
        ? 'Revisión registrada'
        : 'Anulación registrada',
      actorId: event.actorId,
      reason: event.reason,
      previousValue: event.previousValue,
      updatedValue: event.updatedValue,
    }))
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))

  return [original, ...reviews]
}
