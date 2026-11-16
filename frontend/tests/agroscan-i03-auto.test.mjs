import assert from 'node:assert/strict'
import test from 'node:test'
import { runAutoApproxA4 } from '../src/features/geometry/autoApproxA4Runner.ts'

const evaluation = 'E-000020'
const items = [{ id: 'I-000017', view: 'vista-1' }, { id: 'I-000018', view: 'vista-2' }]
function board(imageId, status = 'pixel_scale_estimate') {
  return { id: 1, evaluationId: evaluation, imageId,
    boardVersion: 'ag054-board-a4-v1', rulesVersion: 'ag054-board-plane-v4-a4-marker-pixels',
    status, reason: status === 'needs_review' ? 'board_markers_insufficient' : 'approximate_nominal_30mm_unverified_no_3d',
    markerIds: status === 'needs_review' ? [] : [0,1,2,3],
    measurements: status === 'needs_review' ? null : { majorAxisCm: 9.12, minorAxisCm: 8.54, widthCm: 9.12, heightCm: 8.54 },
    physicalDimensionsValidated: false, fruitHeightCorrected: false,
    cameraIntrinsicsCalibrated: false, classificationE0E1E2Produced: false,
    unit: 'cm_reference_plane' }
}
function deps({ stored = [], geometry = 'measured', fail = false } = {}) {
  let posted = []
  let inferred = []
  const calls = { posted, inferred }
  return { calls,
    getBoards: async (_ev, image) => stored.filter(x => x.imageId === image),
    getGeometries: async () => [],
    analyzeGeometry: async (_ev, image) => { inferred.push(image); return { evaluationId: evaluation, imageId: image, status: geometry } },
    estimate: async (_ev, image) => { posted.push(image); if (fail) throw new Error('API error'); return board(image) },
  }
}
test('Dos vistas nuevas se estiman automáticamente sin click ni verificación física falsa', async () => {
  const d = deps()
  const rows = await runAutoApproxA4(evaluation,items,true,d)
  assert.deepEqual(d.calls.posted, items.map(x => x.id))
  assert.equal(rows.every(x => x.status === 'estimated'), true)
})
test('Reutiliza estimaciones guardadas sin repetir POST', async () => {
  const d = deps({stored: items.map(x => board(x.id))})
  const rows = await runAutoApproxA4(evaluation,items,true,d)
  assert.equal(rows.every(x => x.status === 'estimated'), true)
  assert.equal(d.calls.posted.length,0)
})
test('Una sola vista nunca dispara POST', async () => {
  const d = deps()
  await runAutoApproxA4(evaluation,items.slice(0,1),true,d)
  assert.equal(d.calls.posted.length,0)
})
test('Sin permisos no ejecuta análisis nuevo', async () => {
  const d = deps()
  await runAutoApproxA4(evaluation,items,false,d)
  assert.equal(d.calls.posted.length,0)
})
test('Geometría sin medición no produce centímetros', async () => {
  const d = deps({ geometry: 'needs_review' })
  const rows = await runAutoApproxA4(evaluation,items,true,d)
  assert.equal(rows.every(x => x.status === 'needs_review'),true)
  assert.equal(d.calls.posted.length,0)
})
test('Errores de la API no fabrican valores', async () => {
  const d = deps({fail:true})
  const rows = await runAutoApproxA4(evaluation,items,true,d)
  assert.equal(rows.every(x => x.status === 'error'),true)
})
test('No reintenta rechazos ya guardados', async () => {
  const d = deps({stored:items.map(x => board(x.id,'needs_review'))})
  const rows = await runAutoApproxA4(evaluation,items,true,d)
  assert.equal(rows.every(x => x.status === 'needs_review'),true)
  assert.equal(d.calls.posted.length,0)
})
test('Las dos ejecuciones simultáneas comparten una solicitud', async () => {
  const d = deps()
  const [first,second] = await Promise.all([runAutoApproxA4(evaluation,items,true,d),runAutoApproxA4(evaluation,items,true,d)])
  assert.deepEqual(first,second)
  assert.equal(d.calls.posted.length,2)
})
