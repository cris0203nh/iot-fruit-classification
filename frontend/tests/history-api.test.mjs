import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ApiConnectionError, ApiDataError, ApiResponseError,
  getEvaluationById, getEvaluationTraceability, listEvaluations, resolveEvidenceUrl,
} from '../src/services/agroscanApi.ts'
import { historyService, filterHistory, HISTORY_STATUS_LABELS } from '../src/features/history/historyService.ts'
import { traceabilityService, buildTraceabilityTimeline, validateEvaluationId } from '../src/features/traceability/traceabilityService.ts'

const previousFetch = globalThis.fetch
const evaluation = {
  id: 'E-000001', lotId: 'TEST-MANGO-20261013-01', pieceId: 'P-001',
  product: 'mango', registeredAt: '2026-10-13T20:30:00+00:00', status: 'processing',
  weightGrams: null, imageCount: 0,
}
const detail = { ...evaluation, evidence: [], visualCategory: null, reviewNote: null, failureReason: null }
const trace = { evaluation: detail, calibrationReference: null, modelVersion: null, rulesVersion: null, reviews: [] }
const res = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

test('historial consulta la lista real y acepta el estado processing sin peso', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async (url) => {
    assert.ok(url.endsWith('/api/evaluations'))
    return res([evaluation])
  }
  assert.deepEqual(await historyService.list(), [evaluation])
  assert.equal(HISTORY_STATUS_LABELS.processing, 'En proceso')
  assert.deepEqual(filterHistory([evaluation], { query: 'P-001', product: 'mango', status: 'processing' }), [evaluation])
})

test('detalle y trazabilidad consultan rutas reales sin modificar registros', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const urls = []
  globalThis.fetch = async (url, options) => {
    urls.push(url)
    assert.equal(options.method, undefined)
    return res(url.endsWith('/traceability') ? trace : detail)
  }
  assert.deepEqual(await historyService.getById('E-000001'), detail)
  assert.deepEqual(await traceabilityService.getByEvaluationId('E-000001'), trace)
  assert.ok(urls[0].endsWith('/api/evaluations/E-000001'))
  assert.ok(urls[1].endsWith('/api/evaluations/E-000001/traceability'))
  assert.equal(buildTraceabilityTimeline(trace)[0].id, 'original:E-000001')
})

test('404 se interpreta como no encontrado, no como desconexión', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => res({ detail: 'Evaluación no encontrada.' }, 404)
  assert.equal(await getEvaluationById('E-000008'), null)
  assert.equal(await getEvaluationTraceability('E-000008'), null)
  assert.equal(await getEvaluationById('lote-123'), null)
})

test('403 mantiene el estado de denegación, no se convierte en 404', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => res({ detail: 'Sin autorización' }, 403)
  await assert.rejects(getEvaluationTraceability('E-000001'), (error) => error instanceof ApiResponseError && error.status === 403)
})

test('un fallo de red no se interpreta como lista vacía', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(listEvaluations(), ApiConnectionError)
})

test('rechaza respuestas corruptas en vez de fabricar datos', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => res([{ ...evaluation, status: 'desconocido' }])
  await assert.rejects(listEvaluations(), ApiDataError)
  globalThis.fetch = async () => res({ ...detail, evidence: [{ id: 'I-000001', view: 'frontal', imageUrl: 'https://example.com/evil' }] })
  await assert.rejects(getEvaluationById('E-000001'), ApiDataError)
})

test('solo admite identificadores de FastAPI y rutas de imágenes del backend', () => {
  assert.equal(validateEvaluationId(' E-000001 '), 'E-000001')
  assert.equal(validateEvaluationId('EVAL-001'), null)
  assert.equal(validateEvaluationId('E-1234567890'), null)
  assert.ok(resolveEvidenceUrl('/api/images/I-000001')?.endsWith('/api/images/I-000001'))
  assert.equal(resolveEvidenceUrl('https://example.com/a.png'), null)
  assert.equal(resolveEvidenceUrl('/api/images/../../secret'), null)
})
