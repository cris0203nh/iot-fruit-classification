import assert from 'node:assert/strict'
import test from 'node:test'
import { captureFileError, MAX_CAPTURE_BYTES } from '../src/features/capture/captureValidation.ts'
import { nextCaptureView } from '../src/features/capture/captureViews.ts'
import { ApiDataError, ApiResponseError, uploadEvaluationPhoto } from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
const ok = (body, status = 201) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const image = { id: 'I-000014', view: 'vista-1', imageUrl: '/api/images/I-000014' }

test('AGROP-26: solo JPG/PNG no vacíos hasta 5 MB', () => {
  assert.equal(captureFileError({ type: 'image/jpeg', size: 4 }), null)
  assert.equal(captureFileError({ type: 'image/png', size: MAX_CAPTURE_BYTES }), null)
  assert.match(captureFileError({ type: 'image/heic', size: 100 }), /JPG o PNG/)
  assert.match(captureFileError({ type: 'image/png', size: 0 }), /vacía/)
  assert.match(captureFileError({ type: 'image/png', size: MAX_CAPTURE_BYTES + 1 }), /5 MB/)
})

test('AGROP-26: envía multipart y recibe id real de imagen vinculada', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/api/evaluations/E-000003/images'))
    assert.equal(options.method, 'POST')
    assert.equal(options.body.get('view'), 'vista-1')
    assert.equal(options.body.get('file').name, 'DEMO-tomate.png')
    assert.equal(options.headers, undefined) // el navegador define el boundary de FormData
    return ok(image)
  }
  const file = new File(['RGB'], 'DEMO-tomate.png', { type: 'image/png' })
  assert.deepEqual(await uploadEvaluationPhoto('E-000003', file), image)
})

test('AGROP-26: rechaza id inválido o respuesta que no corresponde al contrato', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const file = new File(['RGB'], 'DEMO.png', { type: 'image/png' })
  await assert.rejects(uploadEvaluationPhoto('../otro', file), ApiDataError)
  for (const bad of [
    { ...image, id: 'otro' }, { ...image, view: 'vista-2' },
    { ...image, imageUrl: 'https://example.com/x.png' },
  ]) {
    globalThis.fetch = async () => ok(bad)
    await assert.rejects(uploadEvaluationPhoto('E-000003', file), ApiDataError)
  }
})

test('AGROP-26: errores HTTP explícitos no se confunden con éxito', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  globalThis.fetch = async () => ok({ detail: 'Evaluación no encontrada.' }, 404)
  await assert.rejects(uploadEvaluationPhoto('E-000003', new File(['x'], 'a.png', { type: 'image/png' })), ApiResponseError)
})

test('AGROP-27: etiqueta consecutiva según vistas persistidas', () => {
  assert.equal(nextCaptureView([]), 'vista-1')
  assert.equal(nextCaptureView(['vista-1']), 'vista-2')
  assert.equal(nextCaptureView(['vista-1', 'vista-3', 'frontal']), 'vista-4')
})

test('AGROP-27: segunda vista usa el mismo ID de evaluación, sin crear otra', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const view2 = { id: 'I-000015', view: 'vista-2', imageUrl: '/api/images/I-000015' }
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/api/evaluations/E-000003/images'))
    assert.equal(options.method, 'POST')
    assert.equal(options.body.get('view'), 'vista-2')
    return ok(view2)
  }
  const file = new File(['RGB'], 'lateral.png', { type: 'image/png' })
  assert.deepEqual(await uploadEvaluationPhoto('E-000003', file, 'vista-2'), view2)
})

test('AGROP-27: rechaza etiquetas o respuestas de vistas inconsistentes', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch })
  const file = new File(['RGB'], 'lateral.png', { type: 'image/png' })
  await assert.rejects(uploadEvaluationPhoto('E-000003', file, '../vista'), ApiDataError)
  globalThis.fetch = async () => ok({ ...image, id: 'I-000015' })
  await assert.rejects(uploadEvaluationPhoto('E-000003', file, 'vista-2'), ApiDataError)
})
