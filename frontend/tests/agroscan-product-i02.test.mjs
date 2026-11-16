import assert from 'node:assert/strict'
import test from 'node:test'
import { runAutomaticQuality, summarizeV2Proposals } from '../src/features/quality/automaticQuality.ts'

const views = ['I-000101', 'I-000102']
const makeView = (imageId, label = 'E1', extra = {}) => ({
  imageId, modelVersion: 'ag055-v2-masked-svc-v1', experimental: true,
  proposedGrade: null, confidenceCalibrated: false, independentPerformanceEvaluated: false,
  sampleUse: 'unseen_photo_independence_unverified', roi: [1, 2, 64, 80],
  evaluable: true, status: 'experimental_proposal', label, reason: null, confidence: .65,
  scoresUncalibrated: { E0: .2, E1: .65, E2: .15 }, ...extra,
})
const row = (...perView) => ({ status: 'experimental_e0e1e2_v2', details: { labelSpace: 'pilot_declared_e0e1e2_v2', perView } })
const records = (sameView = false) => ({ id: 'E-000005', status: 'pending_review', evidence: [
  { id: views[0], view: 'frontal' }, { id: views[1], view: sameView ? 'frontal' : 'posterior' },
] })
const fixture = (patch = {}) => ({
  getEvaluationById: async () => records(),
  getV2QualityStatus: async () => ({ models: [{}] }),
  analyzeV2Quality: async () => [row(makeView(views[0]), makeView(views[1]))],
  getQualityModelStatus: async () => ({ modelAvailable: false }),
  analyzeQualityProposal: async () => { throw new Error('No se ejecuta I01 cuando V2 existe') },
  ...patch,
})

test('I02: V2 propone E1 tras comprobar dos fotografías y no guarda un dictamen', async () => {
  const x = await runAutomaticQuality('E-000005', fixture())
  assert.deepEqual([x.status, x.grade, x.source], ['suggested', 'E1', 'v2'])
  assert.match(x.message, /revisión humana/)
})
test('I02: vistas discrepantes no generan clasificación', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({ analyzeV2Quality: async () => [row(makeView(views[0]), makeView(views[1], 'E2'))] }))
  assert.deepEqual([x.status, x.grade], ['needs_review', null])
})
test('I02: segmentación no evaluable no fuerza E0/E1/E2', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({ analyzeV2Quality: async () => [row(makeView(views[0]), makeView(views[1], null, { evaluable: false, status: 'no_evaluable', confidence: null, scoresUncalibrated: {}, reason: 'fruit_not_separated' }))] }))
  assert.deepEqual([x.status, x.grade], ['needs_review', null])
})
test('I02: evidencia inconsistente o fuente ajena bloquea grado', async () => {
  assert.equal(summarizeV2Proposals([row(makeView(views[0]), makeView('I-999999'))], views), null)
  assert.equal(summarizeV2Proposals([row(makeView(views[0]), makeView(views[0]))], views), null)
  assert.equal(summarizeV2Proposals([row(makeView(views[0]))], views), null)
})
test('I02: una vista con datos incompletos no se omite silenciosamente', async () => {
  assert.equal(summarizeV2Proposals([row(makeView(views[0]), { imageId: views[1], label: 'E1' })], views), null)
})
test('I02: mismo encuadre declarado no se acepta como dos vistas', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({getEvaluationById: async () => records(true)}))
  assert.deepEqual([x.status, x.grade], ['needs_review', null])
})
test('I02: sin modelo no se inventa una predicción', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({
    getV2QualityStatus: async () => ({ models: [] }),
  }))
  assert.deepEqual([x.status, x.grade, x.source], ['no_model', null, null])
})
test('I02: modelo AG055 I01 es el fallback explícito cuando V2 falta', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({
    getV2QualityStatus: async () => ({ models: [] }),
    getQualityModelStatus: async () => ({ modelAvailable: true }),
    analyzeQualityProposal: async () => ({ status: 'experimental_proposal', proposedGrade: 'E2', reason: 'two_views_agree_experimental_only' }),
  }))
  assert.deepEqual([x.status, x.grade, x.source], ['suggested', 'E2', 'quality_i01'])
})
test('I02: el fallback sin concordancia no devuelve grado', async () => {
  const x = await runAutomaticQuality('E-000005', fixture({
    getV2QualityStatus: async () => ({ models: [] }),
    getQualityModelStatus: async () => ({ modelAvailable: true }),
    analyzeQualityProposal: async () => ({ status: 'needs_review', proposedGrade: null, reason: 'vistas_discrepantes' }),
  }))
  assert.equal(x.grade, null)
})
test('I02: falta de evaluación y errores de red nunca se muestran como éxito', async () => {
  const absent = await runAutomaticQuality('E-000005', fixture({getEvaluationById: async () => null}))
  assert.equal(absent.status, 'error')
  const network = await runAutomaticQuality('E-000005', fixture({getV2QualityStatus: async () => { throw new Error('broken') }}))
  assert.equal(network.status, 'error')
})

import { summarizeEvaluation } from '../src/features/history/evaluationOutcomePolicy.ts'
const historical = (proposals, evidenceIds = views) => summarizeEvaluation({
  status: 'completed', ledger: null,
  qualityStatus: { modelAvailable: false }, proposals, evidenceIds,
})
test('I02: Historial sí muestra V2 experimental aunque el clasificador antiguo no esté instalado', () => {
  const result = historical([row(makeView(views[0]), makeView(views[1]))])
  assert.equal(result.ai, 'Sugerencia E1')
  assert.match(result.aiNote, /no es dictamen/i)
})
test('I02: Historial no presenta propuestas antiguas de otra fotografía como actuales', () => {
  const result = historical([row(makeView(views[0]), makeView(views[1]))], [views[0], 'I-000103'])
  assert.equal(result.ai, 'Clasificación requiere revisión')
})

test('I02: no analiza una evaluación sin confirmación de adquisición', async () => {
  const record = { ...records(), status: 'processing' }
  const x = await runAutomaticQuality('E-000005', fixture({ getEvaluationById: async () => record }))
  assert.equal(x.status, 'needs_review')
  assert.equal(x.grade, null)
})
