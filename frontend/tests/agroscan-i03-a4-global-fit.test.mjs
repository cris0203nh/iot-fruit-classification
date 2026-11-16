import assert from 'node:assert/strict'
import test from 'node:test'
import { boardToA4, measureA4, A4_RULES_VERSION, A4_BOARD_VERSION } from '../src/features/geometry/a4MeasurementFlow.ts'

const evaluationId = 'E-000018'
const evidence = [{ id: 'I-000013', view: 'vista-1' }, { id: 'I-000014', view: 'vista-2' }]
const dimensions = { majorAxisCm: 6.2, minorAxisCm: 5.5, widthCm: 6.3,
  heightCm: 5.7, projectedAreaCm2: 27.2, projectedPerimeterCm: 18.6 }
function board(id, status = 'needs_review', reason = 'board_inconsistent_markers', rulesVersion = 'ag054-board-plane-v2-a4') {
  return { id: 1, evaluationId, imageId: id, boardVersion: A4_BOARD_VERSION,
    rulesVersion, status, reason, measurements: status === 'reference_plane_estimate' ? dimensions : null,
    markerIds: status === 'reference_plane_estimate' ? [0,1,2,3] : [], modelVersion: 'yoloe',
    physicalDimensionsValidated: false, fruitHeightCorrected: false,
    cameraIntrinsicsCalibrated: false, classificationE0E1E2Produced: false,
    unit: 'cm_reference_plane' }
}
const geometry = (id) => ({ evaluationId, imageId: id, status: 'measured', measurements: { widthPx: 90 } })

test('Los rechazos antiguos v2 por homografia se recalculan; no son decisiones permanentes', () => {
  assert.equal(boardToA4(evidence[0], evaluationId, [board('I-000013')]), null)
  assert.equal(boardToA4(evidence[0], evaluationId, [board('I-000013', 'reference_plane_estimate')]).status, 'projected')
})

test('Los rechazos ajenos a RANSAC siguen conservados y v3 se reconoce', () => {
  assert.equal(boardToA4(evidence[0], evaluationId, [board('I-000013', 'needs_review', 'board_marker_cropped')]).status, 'needs_review')
  assert.equal(boardToA4(evidence[0], evaluationId, [board('I-000013'), board('I-000013', 'needs_review', 'board_inconsistent_markers', A4_RULES_VERSION)]).status, 'needs_review')
})

test('Dos vistas v2 rechazadas se reenvian una vez a algoritmo v3; despues se reutilizan', async () => {
  let posts = 0
  const stored = { 'I-000013':[board('I-000013')], 'I-000014':[board('I-000014')] }
  const gateway = {
    listFruitGeometries: async () => evidence.map(x => geometry(x.id)),
    analyzeFruitGeometry: async (_, id) => geometry(id),
    listBoardEstimates: async (_, id) => stored[id],
    createBoardEstimate: async (_, id) => { posts++
      const record = board(id, 'reference_plane_estimate', 'projection_only_not_3d', A4_RULES_VERSION)
      stored[id].push(record)
      return record
    },
  }
  const first = await measureA4(evaluationId, evidence, true, gateway)
  assert.deepEqual(first.map(row => row.status), ['projected','projected'])
  assert.equal(posts,2)
  await measureA4(evaluationId, evidence, true, gateway)
  assert.equal(posts,2)
})
