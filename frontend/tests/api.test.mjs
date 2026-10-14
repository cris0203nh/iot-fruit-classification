import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ApiConnectionError, ApiResponseError, createLot, getBackendHealth, listLots,
} from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

test('health y listado consultan endpoints reales, sin inventar registros', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const paths = []
  globalThis.fetch = async (url) => {
    paths.push(url)
    return response(url.endsWith('/api/health') ? { status: 'ok' } : [])
  }
  await getBackendHealth()
  assert.deepEqual(await listLots(), [])
  assert.ok(paths[0].endsWith('/api/health'))
  assert.ok(paths[1].endsWith('/api/lots'))
})

test('crear lote envía la estructura que espera FastAPI y devuelve un ID persistente', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const lot = { id: 15, code: 'LOTE-001', product: 'mango', status: 'open', responsible: '', created_at: '2026-10-01T12:00:00Z' }
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/api/lots'))
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), { code: 'LOTE-001', product: 'mango', responsible: '' })
    return response(lot, 201)
  }
  assert.deepEqual(await createLot({ code: 'LOTE-001', product: 'mango' }), lot)
})

test('errores 409 no se confunden con problemas de red', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => response({ detail: 'Ya existe un lote con esa referencia.' }, 409)
  await assert.rejects(createLot({ code: 'LOTE-001', product: 'mango' }), (error) =>
    error instanceof ApiResponseError && error.status === 409 && error.message.includes('Ya existe'))
})

test('desconexión no se interpreta como una lista vacía', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(listLots(), ApiConnectionError)
})
