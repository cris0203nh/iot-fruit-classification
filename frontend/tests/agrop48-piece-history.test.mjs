import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validatePieceAggregates } from '../src/features/history/pieceHistoryPolicy.ts'

const item = (pieceCode, attemptCount, captureCount) => ({
  lotCode: 'L-001', pieceCode, attemptCount, captureCount,
  reviewEventCount: 3, automaticAssessmentCount: 2,
})

test('AG040: una pieza con tres intentos conserva un solo conteo fisico', () => {
  assert.equal(validatePieceAggregates([item('P-001', 3, 5)], {
    pieceCount: 1, attemptCount: 3, captureCount: 5,
  }), true)
})

test('AG040: distintas piezas son contadas por su clave de lote y codigo', () => {
  assert.equal(validatePieceAggregates([item('P-001', 3, 5), item('P-002', 1, 1)], {
    pieceCount: 2, attemptCount: 4, captureCount: 6,
  }), true)
})

test('AG040: si el backend retorna la misma identidad dos veces no se oculta el error', () => {
  assert.equal(validatePieceAggregates([item('P-001', 1, 2), item('P-001', 1, 2)], {
    pieceCount: 2, attemptCount: 2, captureCount: 4,
  }), false)
})

test('AG040: rechaza totales inconsistentes y negativos', () => {
  assert.equal(validatePieceAggregates([item('P-001', 3, 5)], {
    pieceCount: 1, attemptCount: 5, captureCount: 5,
  }), false)
  assert.equal(validatePieceAggregates([item('P-001', 3, -1)], {
    pieceCount: 1, attemptCount: 3, captureCount: -1,
  }), false)
})

test('AG040: una pieza registrada sin intentos sigue contando una vez', () => {
  assert.equal(validatePieceAggregates([item('P-001', 0, 0)], {
    pieceCount: 1, attemptCount: 0, captureCount: 0,
  }), true)
})
