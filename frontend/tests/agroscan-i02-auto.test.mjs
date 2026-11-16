import assert from 'node:assert/strict'
import test from 'node:test'
import { analyzeStoredV2, summarizeCaptureV2 } from '../src/features/quality/autoV2Preview.ts'
const evidence=[{id:'I-000009',view:'vista-1'},{id:'I-000010',view:'vista-2'}]
const makeView=(id,label='E0',more={})=>({imageId:id,experimental:true,proposedGrade:null,confidenceCalibrated:false,
  independentPerformanceEvaluated:false,sampleUse:'unseen_photo_independence_unverified',roi:[1,2,45,46],
  modelVersion:'ag055-v2-masked-svc-v1',evaluable:true,status:'experimental_proposal',label,reason:null,
  confidence:.7,scoresUncalibrated:{E0:.7,E1:.2,E2:.1},...more})
const makeRow=(labels=['E0','E0'],sourceIds=evidence.map(x=>x.id))=>({id:1,evaluationId:'E-000016',product:'tomate',
  status:'experimental_e0e1e2_v2',reason:'v2_no_external_evaluation',proposedGrade:null,
  modelVersion:'ag055-v2-masked-svc-v1',modelSha256:'valid-sha',sourceFingerprint:'s1',
  humanReviewRequired:true,automaticallyFinalized:false,createdAt:'2026-11-16T00:00:00Z',
  details:{labelSpace:'pilot_declared_e0e1e2_v2',sources:sourceIds.map(imageId=>({imageId,sha256:'x'})),
    perView:sourceIds.map((id,i)=>makeView(id,labels[i]))}})
function gateway(rows=[],models=[{task:'PILOT117_V2',modelSha256:'valid-sha',modelVersion:'v2'}]){
  const calls={analyze:0,list:0}
  return {calls,getV2QualityStatus:async()=>({models}),getQualityProposals:async()=>{calls.list++;return rows},
    analyzeV2Quality:async()=>{calls.analyze++;return [makeRow()]}}
}
test('Inicia automáticamente V2 con dos fotos persistidas, aun sin peso',async()=>{
  const g=gateway();const r=await analyzeStoredV2('E-000016',evidence,g)
  assert.equal(g.calls.analyze,1);assert.deepEqual([r.status,r.grade],['suggested','E0'])
})
test('Reutiliza la predicción ya guardada y no repite POST',async()=>{
  const g=gateway([makeRow()]);const r=await analyzeStoredV2('E-000016',evidence,g)
  assert.equal(g.calls.analyze,0);assert.equal(r.grade,'E0')
})
test('Vistas E0 y E2 no producen grado consolidado',()=>{
  const r=summarizeCaptureV2([makeRow(['E0','E2'])],evidence,'valid-sha')
  assert.equal(r.status,'needs_review');assert.equal(r.grade,null)
})
test('Falla de segmentación en una vista exige revisión',()=>{
  const row=makeRow();row.details.perView[1]=makeView('I-000010',null,{evaluable:false,status:'no_evaluable',reason:'fruit_not_separated',confidence:null,scoresUncalibrated:{}})
  const r=summarizeCaptureV2([row],evidence,'valid-sha')
  assert.equal(r.status,'needs_review');assert.equal(r.grade,null)
})
test('No admite grados de modelos o fotografías ajenos',()=>{
  assert.equal(summarizeCaptureV2([makeRow()],evidence,'another-sha'),null)
  assert.equal(summarizeCaptureV2([makeRow()],[{id:'I-000009',view:'vista-1'},{id:'I-000011',view:'vista-2'}],'valid-sha'),null)
})
test('Sin modelo, no invoca análisis ni inventa grado',async()=>{
  const g=gateway([],[]);const r=await analyzeStoredV2('E-000016',evidence,g)
  assert.equal(g.calls.analyze,0);assert.deepEqual([r.status,r.grade],['no_model',null])
})
test('Una sola vista o etiqueta vista duplicada no genera solicitud',async()=>{
  const g=gateway();const one=await analyzeStoredV2('E-000016',evidence.slice(0,1),g)
  const duplicate=await analyzeStoredV2('E-000016',[evidence[0],{...evidence[1],view:'vista-1'}],g)
  assert.equal(g.calls.analyze,0);assert.equal(one.grade,null);assert.equal(duplicate.grade,null)
})
test('Snapshot incompleto no autoriza grado',()=>{
  const row=makeRow();row.details.perView.pop()
  const r=summarizeCaptureV2([row],evidence,'valid-sha')
  assert.deepEqual([r.status,r.grade],['needs_review',null])
})
test('Una tercera fotografía discrepante impide la consolidación',()=>{
  const three=[...evidence,{id:'I-000011',view:'vista-3'}]
  const r=summarizeCaptureV2([makeRow(['E0','E0','E1'],three.map(x=>x.id))],three,'valid-sha')
  assert.equal(r.status,'needs_review');assert.equal(r.grade,null)
})
test('Una predicción histórica de otra imagen obliga a nueva solicitud V2',async()=>{
  const g=gateway([makeRow(['E0','E0'],['I-000001','I-000002'])])
  const r=await analyzeStoredV2('E-000016',evidence,g)
  assert.equal(g.calls.analyze,1);assert.equal(r.grade,'E0')
})
test('Fallo de la API se propaga sin simular una clasificación',async()=>{
  const g=gateway()
  g.analyzeV2Quality=async()=>{throw new Error('API temporalmente no disponible')}
  await assert.rejects(analyzeStoredV2('E-000016',evidence,g),/API temporalmente no disponible/)
})
