import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiDataError, ApiResponseError, clearOperatorSession, getReviewQueue, loginAgroscan } from '../src/services/agroscanApi.ts'

const row = {
  evaluationId: 'E-000001', lotId: 'LOTE-01', pieceId: 'P-001', product: 'mango',
  status: 'pending_review', registeredAt: '2026-11-13T20:00:00+00:00', imageCount: 2,
  imageIds: ['I-000002'], priority: 'high', reasons: [{ code: 'uncertain_detection', priority: 'high', imageId: 'I-000002', source: 'ag037-assessment:2' }],
  ruleVersion: 'ag056-review-selection-v1',
}
const response = { items: [row], total: 1, limit: 20, offset: 0, hasMore: false,
  counts: { high: 1, normal: 0, all: 1 }, ruleVersion: 'ag056-review-selection-v1' }

async function session(role, t) {
  const previous = globalThis.fetch
  t.after(() => { globalThis.fetch = previous; clearOperatorSession() })
  globalThis.fetch = async url => ({ ok: true, status: 200, json: async () =>
    String(url).endsWith('/auth/me') ? { roles: [role] } : { access_token: 'ag056-token', token_type: 'bearer' } })
  assert.equal(await loginAgroscan('ag056', 'fixture'), role)
}

test('AG056 I03: revisor usa Bearer y obtiene paginación y filtros del servidor', async t => {
  await session('revisor', t)
  globalThis.fetch = async (url, options) => {
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer ag056-token')
    const parsed = new URL(String(url), 'http://local.example')
    assert.equal(parsed.pathname, '/api/reviews/queue')
    assert.equal(parsed.searchParams.get('product'), 'mango')
    assert.equal(parsed.searchParams.get('limit'), '20')
    assert.equal(parsed.searchParams.get('offset'), '0')
    return { ok: true, status: 200, json: async () => response }
  }
  const result = await getReviewQueue({ product: 'mango' })
  assert.equal(result.items[0].evaluationId, 'E-000001')
})

test('AG056 I03: operador no puede consultar ni aun con sesión', async t => {
  await session('operador', t)
  globalThis.fetch = async () => { throw Error('NO solicitar la cola como operador') }
  await assert.rejects(getReviewQueue(), e => e instanceof ApiResponseError && e.status === 403)
})

test('AG056 I03: respuesta HTTP válida pero con estructura inválida es rechazada', async t => {
  await session('administrador', t)
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ ...response, items: [{ ...row, priority: 'normal' }] }) })
  await assert.rejects(getReviewQueue(), ApiDataError)
})
