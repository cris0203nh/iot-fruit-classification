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

const reportRow = (pieceCode, attemptIds = [], captureIds = []) => ({
  lotCode: 'L-001', pieceCode, identitySource: 'registered',
  attemptCount: attemptIds.length, captureCount: captureIds.length,
  automaticAssessmentCount: 0, reviewEventCount: 0,
  attemptIds, captureIds, assessmentIds: [], reviewIds: [],
  modelVersions: [], rulesVersions: [], qualityNotes: [],
})
const makeReport = rows => ({
  reportVersion: 'AG040-02-v1', generatedAt: '2026-11-09T21:00:00+00:00',
  lotCode: 'L-001', product: 'mango', csvEncoding: 'UTF-8', csv: 'datos\r\n',
  csvSha256: 'a'.repeat(64), integrity: { status: 'ok', issues: [] },
  counts: { pieceCount: rows.length, attemptCount: rows.reduce((n, r) => n + r.attemptCount, 0),
    captureCount: rows.reduce((n, r) => n + r.captureCount, 0),
    automaticAssessmentCount: 0, reviewEventCount: 0 }, rows,
})

test('AG040-02: dos intentos y tres fotos pertenecen a una sola pieza', async () => {
  const { validateLotTraceabilityReport } = await import('../src/features/history/pieceReportPolicy.ts')
  assert.equal(validateLotTraceabilityReport(makeReport([
    reportRow('P-001', ['E-000001', 'E-000002'], ['I-000001', 'I-000002', 'I-000003']),
  ]), 'L-001'), true)
})

test('AG040-02: rechaza conteos agregados inflados', async () => {
  const { validateLotTraceabilityReport } = await import('../src/features/history/pieceReportPolicy.ts')
  const data = makeReport([reportRow('P-001', ['E-000001'])])
  data.counts.pieceCount = 2
  assert.equal(validateLotTraceabilityReport(data, 'L-001'), false)
})

test('AG040-02: rechaza foto o intento contabilizado dos veces', async () => {
  const { validateLotTraceabilityReport } = await import('../src/features/history/pieceReportPolicy.ts')
  assert.equal(validateLotTraceabilityReport(makeReport([
    reportRow('P-001', ['E-000001'], ['I-000001']),
    reportRow('P-002', ['E-000002'], ['I-000001']),
  ]), 'L-001'), false)
})

test('AG040-02: no acepta estado ok con fallos de integridad', async () => {
  const { validateLotTraceabilityReport } = await import('../src/features/history/pieceReportPolicy.ts')
  const report = makeReport([reportRow('P-001')])
  report.integrity.issues.push({ severity: 'error', code: 'ERROR', pieceCode: 'P-001', message: 'dato inconsistente' })
  assert.equal(validateLotTraceabilityReport(report, 'L-001'), false)
})

test('AG040-02: acepta lote con pieza sin intentos', async () => {
  const { validateLotTraceabilityReport } = await import('../src/features/history/pieceReportPolicy.ts')
  assert.equal(validateLotTraceabilityReport(makeReport([reportRow('SIN-INTENTOS')]), 'L-001'), true)
})
