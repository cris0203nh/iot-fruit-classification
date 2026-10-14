import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildTraceabilityTimeline,
  validateEvaluationId,
} from '../src/features/traceability/traceabilityService.ts'

test('valida identificadores de FastAPI y elimina espacios externos', () => {
  assert.equal(validateEvaluationId('  E-000001  '), 'E-000001')
  assert.equal(validateEvaluationId('E-2'), 'E-2')
  assert.equal(validateEvaluationId(''), null)
  assert.equal(validateEvaluationId('  '), null)
  assert.equal(validateEvaluationId('lote/2026'), null)
  assert.equal(validateEvaluationId(' ID CON ESPACIOS '), null)
  assert.equal(validateEvaluationId('E-1234567890'), null)
})

test('el historial conserva primero el registro original y ordena revisiones sin mutar la fuente', () => {
  const record = {
    evaluation: {
      id: 'E-000001', lotId: 'LOTE-01', pieceId: 'P-01', product: 'mango',
      registeredAt: '2026-10-01T10:00:00Z', status: 'pending_review', weightGrams: 200,
      imageCount: 0, evidence: [], visualCategory: 'Observada', reviewNote: null,
    },
    calibrationReference: null, modelVersion: null, rulesVersion: null,
    reviews: [
      { id: 'R2', performedAt: '2026-10-03T10:00:00Z', actorId: 'rev2', type: 'cancellation', reason: 'Anulado por revisión', previousValue: 'A', updatedValue: 'B' },
      { id: 'R1', performedAt: '2026-10-02T10:00:00Z', actorId: 'rev1', type: 'review', reason: 'Duda resuelta', previousValue: 'Observada', updatedValue: 'A' },
    ],
  }
  const timeline = buildTraceabilityTimeline(record)
  assert.deepEqual(timeline.map((entry) => entry.id), ['original:E-000001', 'R1', 'R2'])
  assert.equal(timeline[0].updatedValue, 'Observada')
  assert.equal(timeline[1].previousValue, 'Observada')
  assert.equal(record.reviews[0].id, 'R2')
})
