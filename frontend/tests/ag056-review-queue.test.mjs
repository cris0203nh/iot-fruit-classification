import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { buildReviewQueueQuery, describeReviewReason, mayRecordReview, parseReviewQueue } from '../src/features/reviews/reviewQueuePolicy.ts'

const row = {
  evaluationId: 'E-000001', lotId: 'LOTE-01', pieceId: 'P-001', product: 'mango',
  status: 'pending_review', registeredAt: '2026-11-13T20:00:00+00:00', imageCount: 2,
  imageIds: ['I-000002'], priority: 'high', reasons: [{ code: 'uncertain_detection', priority: 'high', imageId: 'I-000002', source: 'ag037-assessment:2' }],
  ruleVersion: 'ag056-review-selection-v1',
}
const response = { items: [row], total: 1, limit: 20, offset: 0, hasMore: false,
  counts: { high: 1, normal: 0, all: 1 }, ruleVersion: 'ag056-review-selection-v1' }
const parse = v => parseReviewQueue(v, { limit: 20, offset: 0 })

test('AG056 I03: respuesta real del backend con prioridad y evidencia asociada', () => {
  assert.equal(parse(response).items[0].imageIds[0], 'I-000002')
  assert.match(describeReviewReason('quality_possible_e2'), /experimental/)
  assert.match(describeReviewReason('quality_proposal_unconfirmed'), /sin confirmación humana/)
})
test('AG056 I03: rechaza datos falsos, duplicados y conteos incoherentes', () => {
  const bad = [
    { ...response, total: 2 }, { ...response, counts: { high: 0, normal: 0, all: 0 } },
    { ...response, ruleVersion: 'v2' }, { ...response, items: [row, row], total: 2, counts: { high: 2, normal: 0, all: 2 } },
    { ...response, items: [{ ...row, priority: 'normal' }] },
    { ...response, items: [{ ...row, imageIds: ['I-000002', 'I-000002'] }] },
    { ...response, items: [{ ...row, registeredAt: 'bad' }] },
    { ...response, items: [{ ...row, reasons: [] }] },
  ]
  bad.forEach(value => assert.throws(() => parse(value)))
})
test('AG056 I03: los parámetros se codifican y limitan sin concatenar URLs arbitrarias', () => {
  const params = new URLSearchParams(buildReviewQueueQuery({ lot: ' LOTE & 1 ', product: 'tomate', priority: 'high', limit: 10, offset: 20 }))
  assert.equal(params.get('lot'), 'LOTE & 1')
  assert.equal(params.get('product'), 'tomate')
  assert.equal(params.get('priority'), 'high')
  assert.equal(params.get('offset'), '20')
  assert.throws(() => buildReviewQueueQuery({ limit: 0 }))
  assert.throws(() => buildReviewQueueQuery({ offset: -1 }))
  assert.throws(() => buildReviewQueueQuery({ lot: 'x'.repeat(33) }))
})
test('AG056 I03: no ofrece escritura para evaluaciones en procesamiento', () => {
  assert.equal(mayRecordReview('processing'), false)
  assert.equal(mayRecordReview('pending_review'), true)
  assert.equal(mayRecordReview('completed'), true)
})
test('AG056 I03: la interfaz no utiliza aprobaciones automáticas ni modifica la evidencia', () => {
  const page = readFileSync(new URL('../src/pages/ReviewQueuePage.tsx', import.meta.url), 'utf8')
  assert.match(page, /ReviewDecisionPanel/)
  assert.match(page, /ProtectedEvidenceImage/)
  assert.match(page, /getReviewQueue/)
  assert.doesNotMatch(page, /approveAutomatically|finalizeQuality|updateVisualCategory/)
})
