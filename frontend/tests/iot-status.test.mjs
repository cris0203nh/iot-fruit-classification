import assert from 'node:assert/strict'
import test from 'node:test'
import { getIotStatus, ApiConnectionError, ApiDataError } from '../src/services/agroscanApi.ts'
import { deriveWeightView, weightConnectionError } from '../src/features/iot/weightReading.ts'

const originalFetch = globalThis.fetch
const response = (body) => ({ ok: true, status: 200, json: async () => body })
const fresh = { online: true, deviceId: 'station-001', weightG: 250, stable: true,
  receivedAt: '2026-10-29T23:00:00+00:00', ageSeconds: 1 }

test('consulta contrato real de FastAPI con timestamp, peso y estabilidad', async (t) => {
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async (url) => { assert.ok(url.endsWith('/api/iot/status')); return response(fresh) }
  assert.deepEqual(await getIotStatus(), fresh)
  assert.equal(deriveWeightView(await getIotStatus()).state, 'stable')
})

test('inestabilidad: conserva estado informativo pero impide considerar el peso registrable', () => {
  const view = deriveWeightView({ ...fresh, stable: false })
  assert.equal(view.state, 'unstable')
  assert.equal(view.weightG, 250)
  assert.match(view.description, /no debe registrarse/i)
})

test('desconexión y lectura vencida nunca reutilizan el peso anterior', () => {
  const offline = { ...fresh, online: false, weightG: null, stable: null, ageSeconds: 11 }
  const view = deriveWeightView(offline)
  assert.equal(view.state, 'stale')
  assert.equal(view.weightG, null)
  assert.equal(view.deviceId, null)
  assert.equal(deriveWeightView(null).weightG, null)
  assert.equal(deriveWeightView({ ...fresh, ageSeconds: 8.5 }, 1500).weightG, null)
  assert.equal(deriveWeightView({ ...fresh, ageSeconds: 1 }, 8000).state, 'stable')
  assert.equal(deriveWeightView({ ...fresh, ageSeconds: 1 }, 9000).state, 'stale')
})

test('sin registros y fallo de comunicación muestran estados separados', () => {
  assert.equal(deriveWeightView({ online: false, deviceId: null, weightG: null, stable: null,
    receivedAt: null, ageSeconds: null }).state, 'offline')
  assert.equal(weightConnectionError().weightG, null)
  assert.equal(weightConnectionError().state, 'error')
})

test('contrato alterado es rechazado; no aparecen mediciones inventadas', async (t) => {
  t.after(() => { globalThis.fetch = originalFetch })
  for (const bad of [
    { ...fresh, weightG: '250' }, { ...fresh, weightG: Infinity }, { ...fresh, stable: null },
    { ...fresh, receivedAt: 'ayer' }, { ...fresh, ageSeconds: -1 },
    { ...fresh, online: false },
    { ...fresh, deviceId: '' },
  ]) {
    globalThis.fetch = async () => response(bad)
    await assert.rejects(getIotStatus(), ApiDataError)
  }
})

test('pérdida de conexión a FastAPI se diferencia de respuesta con estado desconectado', async (t) => {
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => { throw new Error('Failed to fetch') }
  await assert.rejects(getIotStatus(), ApiConnectionError)
})
