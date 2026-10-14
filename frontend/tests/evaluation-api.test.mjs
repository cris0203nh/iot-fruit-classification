import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ApiConnectionError, ApiDataError, ApiResponseError,
  createEvaluation,
} from '../src/services/agroscanApi.ts'
import { isValidPieceId } from '../src/features/evaluation/pieceValidation.ts'

const previousFetch = globalThis.fetch
const evaluation = {
  id: 'E-000001', lotId: 'LOTE-001', pieceId: 'P.001', product: 'mango',
  registeredAt: '2026-10-13T23:12:00+00:00', status: 'processing', weightGrams: null,
  imageCount: 0, evidence: [], visualCategory: null, reviewNote: null, failureReason: null,
}
const res = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

test('la validación de pieza coincide con el esquema de Pydantic (1-64 caracteres)', () => {
  assert.equal(isValidPieceId('P.001'), true)
  assert.equal(isValidPieceId('a'), true)
  assert.equal(isValidPieceId('A_3-1'), true)
  assert.equal(isValidPieceId(`A${'1'.repeat(63)}`), true)
  assert.equal(isValidPieceId(''), false)
  assert.equal(isValidPieceId('-INICIO'), false)
  assert.equal(isValidPieceId('P 01'), false)
  assert.equal(isValidPieceId('P/01'), false)
  assert.equal(isValidPieceId(`A${'1'.repeat(64)}`), false)
})

test('crear evaluación envía lotId y pieceId y exige confirmación del backend', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/api/evaluations'))
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), { lotId: 'LOTE-001', pieceId: 'P.001' })
    return res(evaluation, 201)
  }
  assert.deepEqual(await createEvaluation({ lotId: ' LOTE-001 ', pieceId: ' P.001 ' }), evaluation)
})

test('404 lote inexistente y 409 lote cerrado se mantienen como errores distintos', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  for (const [status, detail] of [[404, 'El lote indicado no existe.'], [409, 'El lote está cerrado.']]) {
    globalThis.fetch = async () => res({ detail }, status)
    await assert.rejects(createEvaluation({ lotId: 'LOTE-001', pieceId: 'P-001' }), (error) =>
      error instanceof ApiResponseError && error.status === status && error.message === detail)
  }
})

test('422 valida campos; no se considera un problema de red', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => res({ detail: [{ msg: 'Value error, identificador inválido' }] }, 422)
  await assert.rejects(createEvaluation({ lotId: 'LOTE-001', pieceId: 'P 001' }), (error) =>
    error instanceof ApiResponseError && error.status === 422)
})

test('red desconectada o timeout no se presenta como evaluación creada', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(createEvaluation({ lotId: 'LOTE-001', pieceId: 'P-001' }), ApiConnectionError)
})

test('respuestas incompletas, alteradas o con estado incorrecto no se aceptan como registro confirmado', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  for (const invalid of [
    { ...evaluation, id: 'INVALID' },
    { ...evaluation, lotId: 'OTRO-LOTE' },
    { ...evaluation, pieceId: 'OTRA-PIEZA' },
    { ...evaluation, status: 'completed' },
    { ...evaluation, evidence: 'falsos' },
  ]) {
    globalThis.fetch = async () => res(invalid, 201)
    await assert.rejects(createEvaluation({ lotId: 'LOTE-001', pieceId: 'P.001' }), ApiDataError)
  }
})
