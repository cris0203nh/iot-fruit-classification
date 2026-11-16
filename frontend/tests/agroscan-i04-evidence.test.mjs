import assert from 'node:assert/strict'
import test from 'node:test'
import { summarizeEvidenceI04 } from '../src/features/history/evaluationEvidenceSnapshot.ts'

const evaluation = 'E-000021'
const evidence = [{id:'I-000021',view:'vista-1'},{id:'I-000022',view:'vista-2'}]
const sample = (id, grade='E0') => ({
  imageId:id, experimental:true, proposedGrade:null, confidenceCalibrated:false,
  independentPerformanceEvaluated:false, sampleUse:'independencia_no_verificada',
  roi:[1,2,40,40],modelVersion:'v2',evaluable:true,status:'experimental_proposal',
  label:grade, reason:null, confidence:0.6, scoresUncalibrated:{E0:0.6,E1:0.3,E2:0.1},
})
const proposal = (ids=evidence.map(x=>x.id), grades=['E0','E0'], overrides={}) => ({
  id:3,evaluationId:evaluation, product:'tomate', status:'experimental_e0e1e2_v2',
  reason:'v2_no_external_evaluation',proposedGrade:null, modelSha256:'sha', modelVersion:'v2',
  sourceFingerprint:'fingerprint', humanReviewRequired:true,automaticallyFinalized:false,
  createdAt:'2026-11-15T20:00:00Z',
  details:{labelSpace:'pilot_declared_e0e1e2_v2', sources:ids.map(imageId=>({imageId,sha256:'hash'})),
    perView:ids.map((id,i)=>sample(id,grades[i]))}, ...overrides,
})
const board = (imageId, major=9.1, minor=8.4, overrides={}) => ({
  id:1, evaluationId:evaluation,imageId,boardVersion:'ag054-board-a4-v1',
  rulesVersion:'ag054-board-plane-v4-a4-marker-pixels',status:'pixel_scale_estimate',
  reason:'approximate_nominal_30mm_unverified_no_3d', markerIds:[0,1,2,3],
  measurements:{majorAxisCm:major,minorAxisCm:minor,widthCm:major,heightCm:minor,
    projectedAreaCm2:45,projectedPerimeterCm:20,markerScaleVariationPct:22},
  physicalDimensionsValidated:false,fruitHeightCorrected:false,cameraIntrinsicsCalibrated:false,
  classificationE0E1E2Produced:false,unit:'cm_reference_plane', ...overrides,
})
const groups = () => [[board('I-000021')], [board('I-000022',10.0,7.3)]]

test('I04 integra dos resultados existentes sin promediar y mantiene propuesta experimental', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[proposal()],groups())
  assert.deepEqual([r.quality.status,r.quality.grade],['suggested','E0'])
  assert.deepEqual(r.dimensions.map(v => v.record.measurements.majorAxisCm),[9.1,10.0])
})
test('I04 exige correspondencia con la evaluación actual', () => {
  const p = proposal(undefined,undefined,{evaluationId:'E-000019'})
  const r = summarizeEvidenceI04(evaluation,evidence,[p],groups())
  assert.equal(r.quality,null)
})
test('I04 no admite predicciones de fotos anteriores', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[proposal(['I-000001','I-000002'])],groups())
  assert.equal(r.quality,null)
})
test('I04 conserva revisión cuando las vistas discrepan', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[proposal(undefined,['E0','E2'])],groups())
  assert.deepEqual([r.quality.status,r.quality.grade],['needs_review',null])
})
test('I04 no utiliza grados automáticos finales ni de modelos antiguos', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[proposal(undefined,undefined,{automaticallyFinalized:true}),
    proposal(undefined,undefined,{status:'experimental_e0e1e2_pilot'})],groups())
  assert.equal(r.quality,null)
})
test('I04 rechaza duplicados de identidad de imagen o vista', () => {
  const bad = [{id:'I-000021',view:'vista-1'},{id:'I-000022',view:'vista-1'}]
  const r = summarizeEvidenceI04(evaluation,bad,[proposal()],groups())
  assert.equal(r.quality,null)
})
test('I04 no convierte un rechazo dimensional en centímetros', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[proposal()],[[board('I-000021',9,8,{status:'needs_review',measurements:null})],[]])
  assert.deepEqual(r.dimensions.map(x=>x.status),['needs_review','pending'])
})
test('I04 no mezcla estimación histórica de homografía A4 con escala nominal', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[],[[board('I-000021',9,8,{status:'reference_plane_estimate',rulesVersion:'ag054-board-plane-v3-a4-global-fit'})],[]])
  assert.equal(r.dimensions[0].status,'pending')
})
test('I04 no presenta medidas provenientes de otra evaluación', () => {
  const r = summarizeEvidenceI04(evaluation,evidence,[],[[board('I-000021',9,8,{evaluationId:'E-000020'})],[]])
  assert.equal(r.dimensions[0].status,'pending')
})
test('I04 utiliza propuesta completa más reciente, no una versión obsoleta', () => {
  const past=proposal(undefined,['E1','E1'],{id:1})
  const newest=proposal(undefined,['E0','E0'],{id:9})
  const r=summarizeEvidenceI04(evaluation,evidence,[past,newest],groups())
  assert.equal(r.quality.grade,'E0')
})
