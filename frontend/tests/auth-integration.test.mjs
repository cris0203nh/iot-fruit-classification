import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ApiDataError, ApiResponseError, clearOperatorSession, getEvaluationById,
  isOperatorAuthenticated, loadProtectedEvidence, loginOperator, uploadEvaluationPhoto,
} from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
const fakeMe = { id: 1, username: 'operador', roles: ['operador'] }

test('AGROP-27/47: inicia sesión, verifica operador y autoriza evaluaciones y fotos', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  let calls = 0
  globalThis.fetch = async (url, options) => {
    calls += 1
    if (url.endsWith('/api/auth/login')) {
      assert.equal(options.method, 'POST')
      assert.equal(new URLSearchParams(options.body).get('username'), 'operador')
      return { ok: true, status: 200, json: async () => ({ access_token: 'token-de-prueba', token_type: 'bearer' }) }
    }
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer token-de-prueba')
    if (url.endsWith('/api/auth/me')) return { ok: true, status: 200, json: async () => fakeMe }
    if (url.endsWith('/api/evaluations/E-000008')) return { ok: true, status: 200, json: async () => ({
      id: 'E-000008', lotId: 'LOTE-1', pieceId: 'PIEZA-1', product: 'mango', registeredAt: new Date().toISOString(), status: 'processing', weightGrams: null, imageCount: 0, evidence: [], visualCategory: null, reviewNote: null, failureReason: null,
    }) }
    if (url.endsWith('/api/evaluations/E-000008/images')) {
      assert.equal(options.body.get('view'), 'vista-2')
      return { ok: true, status: 201, json: async () => ({ id: 'I-000008', view: 'vista-2', imageUrl: '/api/images/I-000008' }) }
    }
    throw new Error(`Endpoint inesperado: ${url}`)
  }
  await loginOperator('operador', 'clave-de-prueba')
  assert.equal(isOperatorAuthenticated(), true)
  assert.equal((await getEvaluationById('E-000008')).id, 'E-000008')
  const file = new File(['RGB'], 'vista2.png', { type: 'image/png' })
  assert.equal((await uploadEvaluationPhoto('E-000008', file, 'vista-2')).view, 'vista-2')
  assert.equal(calls, 4)
  clearOperatorSession()
  assert.equal(isOperatorAuthenticated(), false)
})

test('AGROP-47: un revisor no puede habilitar el flujo de captura', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => url.endsWith('/auth/me') ? { roles: ['revisor'] } : { access_token: 'token', token_type: 'bearer' } })
  await assert.rejects(loginOperator('revisor', 'clave'), (error) => error instanceof ApiResponseError && error.status === 403)
  assert.equal(isOperatorAuthenticated(), false)
})

test('AGROP-47: obtiene JPG protegido por cabecera, nunca por URL de token', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => url.endsWith('/auth/me') ? fakeMe : { access_token: 'token-de-prueba', token_type: 'bearer' } })
  await loginOperator('operador', 'clave')
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/images/I-000003')
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer token-de-prueba')
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'image/jpeg' }), blob: async () => new Blob(['jpeg'], { type: 'image/jpeg' }) }
  }
  assert.equal((await loadProtectedEvidence('/api/images/I-000003')).type, 'image/jpeg')
  await assert.rejects(loadProtectedEvidence('https://evil.example/images/I-000003'), ApiDataError)
  clearOperatorSession()
  await assert.rejects(loadProtectedEvidence('/api/images/I-000003'), (error) => error instanceof ApiResponseError && error.status === 401)
})
