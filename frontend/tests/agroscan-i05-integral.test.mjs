/** I05: regresión integrada I01-I04. Datos sintéticos, sin tocar FastAPI/SQLite. */
import assert from 'node:assert/strict'
import test from 'node:test'
import { acquisitionOutcome, hasConfirmedImages } from '../src/features/evaluation/evaluationFlow.ts'
import { analyzeStoredV2 } from '../src/features/quality/autoV2Preview.ts'
import { runAutoApproxA4 } from '../src/features/geometry/autoApproxA4Runner.ts'
import { summarizeEvidenceI04 } from '../src/features/history/evaluationEvidenceSnapshot.ts'

const EVAL = 'E-000091'
const EVIDENCE = [{ id: 'I-000091', view: 'vista-1' }, { id: 'I-000092', view: 'vista-2' }]
const MODEL = 'i05-sha-v2'

function view(id, grade='E0') {
  return {
    imageId: id, experimental: true, proposedGrade: null, confidenceCalibrated: false,
    independentPerformanceEvaluated: false, sampleUse: 'independencia_no_verificada',
    roi: [5, 8, 60, 66], modelVersion: 'i05-v2',
    evaluable: true, status: 'experimental_proposal', label: grade,
    reason: null, confidence: 0.65, scoresUncalibrated: { E0: 0.65, E1: 0.25, E2: 0.10 },
  }
}
function proposal(grades=['E0','E0'], evaluationId=EVAL, images=EVIDENCE) {
  return {
    id: 8, evaluationId, product: 'tomate', status: 'experimental_e0e1e2_v2',
    reason: 'v2_no_external_evaluation', proposedGrade: null, modelSha256: MODEL,
    modelVersion: 'i05-v2', sourceFingerprint: 'fingerprint',
    humanReviewRequired: true, automaticallyFinalized: false,
    createdAt: '2026-11-15T20:00:00Z',
    details: {
      labelSpace: 'pilot_declared_e0e1e2_v2',
      sources: images.map(item => ({ imageId: item.id, sha256: 'imagehash' })),
      perView: images.map((item, index) => view(item.id, grades[index])),
    },
  }
}
function estimate(imageId, major, minor, evaluationId=EVAL, overrides={}) {
  return {
    id: imageId === EVIDENCE[0].id ? 4 : 5,
    evaluationId, imageId, boardVersion: 'ag054-board-a4-v1',
    rulesVersion: 'ag054-board-plane-v4-a4-marker-pixels',
    status: 'pixel_scale_estimate', reason: 'approximate_nominal_30mm_unverified_no_3d',
    markerIds: [0,1,2,3], measurements: {
      majorAxisCm: major, minorAxisCm: minor, widthCm: major, heightCm: minor,
      projectedAreaCm2: 70, projectedPerimeterCm: 31, markerScaleVariationPct: 19,
    },
    physicalDimensionsValidated: false, fruitHeightCorrected: false,
    cameraIntrinsicsCalibrated: false, classificationE0E1E2Produced: false,
    unit: 'cm_reference_plane', ...overrides,
  }
}
const boards = () => [[estimate(EVIDENCE[0].id, 9.12, 8.54)], [estimate(EVIDENCE[1].id, 10.08, 7.28)]]
function qualityGateway(rows=[proposal()], models=[{task:'PILOT117_V2',modelSha256:MODEL,modelVersion:'i05-v2'}]) {
  const calls = { analyses: 0 }
  return {
    calls,
    getV2QualityStatus: async () => ({ models }),
    getQualityProposals: async () => rows,
    analyzeV2Quality: async () => { calls.analyses++; return rows },
  }
}
function dimensionGateway(groups=boards()) {
  const calls = { estimated: 0, geometry: 0 }
  return {
    calls,
    getBoards: async (_eval, id) => groups[EVIDENCE.findIndex(x => x.id === id)] ?? [],
    getGeometries: async () => { calls.geometry++; return [] },
    analyzeGeometry: async (evaluationId, imageId) => ({ evaluationId, imageId, status: 'measured' }),
    estimate: async (_evaluationId, imageId) => {
      calls.estimated++
      return imageId === EVIDENCE[0].id ? boards()[0][0] : boards()[1][0]
    },
  }
}

test('I05: dos fotografías, sin sensor: calidad y cm disponibles, adquisición PARCIAL', async () => {
  const savedProposal = proposal()
  const gateway = qualityGateway([savedProposal])
  const q = await analyzeStoredV2(EVAL, EVIDENCE, gateway)
  const dim = await runAutoApproxA4(EVAL, EVIDENCE, true, dimensionGateway())
  const history = summarizeEvidenceI04(EVAL, EVIDENCE, [proposal()], boards())
  assert.equal(acquisitionOutcome({imageCount:2,initialWeightConfirmed:false,finalWeightConfirmed:false}), 'partial')
  assert.equal(q.status,'suggested')
  assert.equal(q.grade,'E0')
  assert.equal(savedProposal.automaticallyFinalized, false)
  assert.equal(savedProposal.proposedGrade, null)
  assert.deepEqual(dim.map(x => x.status), ['estimated','estimated'])
  assert.deepEqual(history.dimensions.map(x => x.record.measurements.majorAxisCm), [9.12,10.08])
  assert.equal(history.quality.grade, 'E0')
  assert.equal(gateway.calls.analyses, 0)
})

test('I05: dos fotos + dos pesos solo satisfacen precondiciones, no sustituyen confirmación backend', () => {
  assert.equal(hasConfirmedImages(2), true)
  assert.equal(acquisitionOutcome({imageCount:2,initialWeightConfirmed:true,finalWeightConfirmed:true}), 'confirmed')
  // El predicado NO equivale a un POST de confirmación ni a una prueba del hardware.
})

test('I05: una imagen impide estimar y no lanza V2', async () => {
  const one = EVIDENCE.slice(0,1)
  const q = qualityGateway()
  const d = dimensionGateway([[]])
  assert.equal((await analyzeStoredV2(EVAL,one,q)).grade, null)
  assert.deepEqual((await runAutoApproxA4(EVAL,one,true,d)).map(x=>x.status), ['pending'])
  assert.equal(q.calls.analyses,0)
  assert.equal(d.calls.estimated,0)
})

test('I05: propuestas V2 discrepantes requieren revisión aunque haya dimensiones', async () => {
  const p = proposal(['E0','E2'])
  const q = await analyzeStoredV2(EVAL,EVIDENCE,qualityGateway([p]))
  assert.deepEqual([q.status,q.grade], ['needs_review',null])
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[p],boards())
  assert.equal(summary.quality.grade,null)
  assert.deepEqual(summary.dimensions.map(x=>x.status),['estimated','estimated'])
})

test('I05: sin modelo V2, no se inventa E0/E1/E2 y los cm permanecen independientes', async () => {
  const q = await analyzeStoredV2(EVAL,EVIDENCE,qualityGateway([],[]))
  assert.deepEqual([q.status,q.grade],['no_model',null])
  assert.deepEqual(summarizeEvidenceI04(EVAL,EVIDENCE,[],boards()).dimensions.map(x=>x.status),['estimated','estimated'])
})

test('I05: no evaluable geométrico no anula propuesta V2 ni fabrica centímetros', () => {
  const b = boards();b[0][0] = estimate(EVIDENCE[0].id,9,8,EVAL,{status:'needs_review',measurements:null})
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[proposal()],b)
  assert.equal(summary.quality.grade,'E0')
  assert.deepEqual(summary.dimensions.map(x=>x.status),['needs_review','estimated'])
})

test('I05: historial excluye instantáneas de evaluaciones ajenas', () => {
  const b = boards();b[0][0] = estimate(EVIDENCE[0].id,9,8,'E-000090')
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[proposal(['E0','E0'],'E-000090')],b)
  assert.equal(summary.quality,null)
  assert.deepEqual(summary.dimensions.map(x=>x.status),['pending','estimated'])
})

test('I05: una fotografía de otra evaluación impide consolidación V2', () => {
  const p = proposal(['E0','E0'],EVAL,[EVIDENCE[0],{id:'I-000999',view:'vista-2'}])
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[p],boards())
  assert.equal(summary.quality,null)
})

test('I05: sin autorización, no se lanzan inferencias dimensionales nuevas', async () => {
  const d = dimensionGateway([[],[]])
  const rows = await runAutoApproxA4(EVAL,EVIDENCE,false,d)
  assert.deepEqual(rows.map(r=>r.status),['pending','pending'])
  assert.deepEqual(d.calls,{estimated:0,geometry:0})
})

test('I05: errores de API V2 no devuelven grado de éxito inventado', async () => {
  const g = qualityGateway([])
  g.analyzeV2Quality = async () => { throw new Error('503 backend sin modelo') }
  await assert.rejects(analyzeStoredV2(EVAL,EVIDENCE,g), /503 backend sin modelo/)
})

test('I05: una medida de homografía no se confunde con estimación nominal', () => {
  const old = estimate(EVIDENCE[0].id,9,8,EVAL,{status:'reference_plane_estimate',rulesVersion:'ag054-board-plane-v3-a4-global-fit'})
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[proposal()],[[old],[]])
  assert.deepEqual(summary.dimensions.map(x=>x.status),['pending','pending'])
})

test('I05: V2 y dimensiones no se promedian ni se convierten en precisión acreditada', () => {
  const summary = summarizeEvidenceI04(EVAL,EVIDENCE,[proposal()],boards())
  assert.notEqual(summary.dimensions[0].record.measurements.majorAxisCm,summary.dimensions[1].record.measurements.majorAxisCm)
  assert.equal(summary.dimensions[0].record.physicalDimensionsValidated,false)
  assert.equal(summary.dimensions[1].record.physicalDimensionsValidated,false)
  assert.equal(summary.quality.status,'suggested')
})
