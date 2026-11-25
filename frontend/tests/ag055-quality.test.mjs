import assert from 'node:assert/strict'
import test from 'node:test'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { exploratoryViews } from '../src/features/quality/exploratoryPolicy.ts'
import { pilotViews } from '../src/features/quality/pilotPolicy.ts'
import { v2Views, v2Reason, v2ReviewMessage } from '../src/features/quality/v2Policy.ts'
import { analyzeStoredV2, summarizeCaptureV2 } from '../src/features/quality/autoV2Preview.ts'
import { getExploratoryQualityStatus, analyzeExploratoryQuality, ApiDataError,
  loginOperator, clearOperatorSession, getQualityReviewQueue, getV2QualityStatus, analyzeV2Quality } from '../src/services/agroscanApi.ts'
const api=readFileSync(new URL('../src/services/agroscanApi.ts',import.meta.url),'utf8')
const panel=readFileSync(new URL('../src/features/quality/QualityProposalPanel.tsx',import.meta.url),'utf8')

test('AG055: segmentation failures describe each reason and never claim disagreeing grades', () => {
  const views = ['I-000041','I-000042'].map(imageId => ({imageId, evaluable:false, reason:'insufficient_fruit_area_in_frame'}))
  const message = v2ReviewMessage(views)
  assert.match(message,/I-000041/); assert.match(message,/I-000042/)
  assert.match(message,/menos área/); assert.doesNotMatch(message,/discrepan/)
  assert.match(v2ReviewMessage([{...views[0],evaluable:true,reason:null},views[1]]),/menos área/)
  assert.match(v2ReviewMessage(views.map((view,index)=>({...view,evaluable:true,reason:null,label:index?'E2':'E0'}))),/discrepan/)
  assert.doesNotMatch(v2ReviewMessage(views.map(view=>({...view,evaluable:true,reason:null,label:'E0'}))),/discrepan/)
  for (const reason of ['fruit_not_detected','image_decode_failed','incompatible_features','partial_fruit_coverage','unsupported_image_size']) assert.ok(v2Reason(reason).length>20)
})

test('AG055: new inference policy refreshes cache without erasing historical snapshots', async () => {
  const evidence=[{id:'I-000041',view:'front'},{id:'I-000042',view:'back'}]
  const perView=evidence.map(item=>({imageId:item.id,modelVersion:'v2',experimental:true,proposedGrade:null,
    confidenceCalibrated:false,independentPerformanceEvaluated:false,sampleUse:'unseen_photo_independence_unverified',
    roi:[0,0,160,160],evaluable:false,label:null,confidence:null,status:'no_evaluable',
    reason:'insufficient_fruit_area_in_frame',scoresUncalibrated:{}}))
  const original={id:1,status:'experimental_e0e1e2_v2',modelSha256:'same-model',modelVersion:'v2',proposedGrade:null,automaticallyFinalized:false,
    details:{sources:evidence.map(item=>({imageId:item.id})),labelSpace:'pilot_declared_e0e1e2_v2',perView}}
  const current={...original,id:2,details:{...original.details,inferencePolicyVersion:'current-policy'}}
  let calls=0
  const result=await analyzeStoredV2('E-000041',evidence,{
    getV2QualityStatus:async()=>({models:[{task:'PILOT117_V2',modelSha256:'same-model',modelVersion:'v2',inferencePolicyVersion:'current-policy'}]}),
    getQualityProposals:async()=>[original],analyzeV2Quality:async()=>{calls++;return [current]},
  })
  assert.equal(calls,1);assert.equal(result.grade,null)
  assert.doesNotMatch(result.message,/discrepan/)
  assert.equal(original.details.inferencePolicyVersion,undefined)
  assert.equal(summarizeCaptureV2([original],evidence,'same-model','current-policy'),null)
  assert.ok(summarizeCaptureV2([original],evidence,'same-model')) // History remains readable.
})

test('AG055 V2: mask rejection has no fabricated grade or confidence and stays reviewable', () => {
  const view={imageId:'I-000001',roi:[0,0,160,160],modelVersion:'ag055-v2-masked-svc-v1',experimental:true,
    proposedGrade:null,confidenceCalibrated:false,independentPerformanceEvaluated:false,sampleUse:'training_photo',
    evaluable:false,label:null,confidence:null,status:'no_evaluable',reason:'fruit_not_separated',scoresUncalibrated:{}}
  const details={labelSpace:'pilot_declared_e0e1e2_v2',perView:[view]}
  assert.equal(v2Views(details).length,1)
  for(const changes of [{label:'E0'},{confidence:.9},{scoresUncalibrated:{E0:1}},{proposedGrade:'E0'},{confidenceCalibrated:true}]){
    assert.deepEqual(v2Views({...details,perView:[{...view,...changes}]}),[])
  }
  assert.deepEqual(pilotViews(details),[])
  assert.deepEqual(v2Views({...details,labelSpace:'pilot_declared_e0e1e2'}),[])
})

test('AG055 V2: evaluable proposal rejects malformed scores and keeps label-space separation', () => {
  const view={imageId:'I-000001',roi:[1,2,100,120],modelVersion:'ag055-v2-masked-svc-v1',experimental:true,
    proposedGrade:null,confidenceCalibrated:false,independentPerformanceEvaluated:false,sampleUse:'training_photo',
    evaluable:true,label:'E1',confidence:.7,reason:null,scoresUncalibrated:{E0:.1,E1:.7,E2:.2}}
  const details={labelSpace:'pilot_declared_e0e1e2_v2',perView:[view]}
  assert.equal(v2Views(details).length,1)
  assert.deepEqual(v2Views({...details,perView:[{...view,scoresUncalibrated:{E0:NaN,E1:.7,E2:.3}}]}),[])
})

test('AG055 V2: authenticated endpoint cannot accept automatic final grades', async t => {
  const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})
  globalThis.fetch=async url=>({ok:true,status:200,json:async()=>url.endsWith('/auth/me')?{roles:['operador']}:{access_token:'test-token',token_type:'bearer'}})
  await loginOperator('test','fixture')
  globalThis.fetch=async(url,options)=>{
    assert.equal(new Headers(options.headers).get('Authorization'),'Bearer test-token')
    return {ok:true,status:200,json:async()=>url.endsWith('/status')?
      {evaluationId:'E-000001',experimental:true,independentTestMetrics:null,reason:'experimental',models:[]}:
      [{...exploratoryRow,status:'experimental_e0e1e2_v2',proposedGrade:'E0'}]}
  }
  assert.equal((await getV2QualityStatus('E-000001')).models.length,0)
  await assert.rejects(analyzeV2Quality('E-000001'),ApiDataError)
})
const trace=readFileSync(new URL('../src/pages/TraceabilityPage.tsx',import.meta.url),'utf8')
const capture=readFileSync(new URL('../src/features/capture/EvaluationImageCapture.tsx',import.meta.url),'utf8')

test('AG055: no confunde propuesta E0/E1/E2 con grado confirmado',()=>{
  assert.match(panel,/Revisión humana obligatoria/)
  assert.match(panel,/NO confirmada/)
  assert.doesNotMatch(panel, /updateEvaluationGrade|confirmQualityAutomatically|visualCategory\s*=/)
})
test('AG055: consultar y analizar usa endpoints autenticados existentes',()=>{
  assert.match(api,/vision\/quality\/status/)
  assert.match(api,/vision\/quality\/proposals/)
  assert.match(api,/vision\/quality\/analyze/)
  assert.match(api,/isOperatorAuthenticated/)
})
test('AG055: accesible durante captura y trazabilidad',()=>{
  assert.match(capture,/QualityProposalPanel/)
  assert.match(trace,/QualityProposalPanel/)
})

const exploratoryRow = {
  id: 1, evaluationId: 'E-000001', product: 'tomate', status: 'exploratory_original_labels',
  reason: 'original_labels_not_e0_e1_e2', proposedGrade: null, modelVersion: 'ag055-original-labels-v1',
  modelSha256: 'a'.repeat(64), sourceFingerprint: 'b'.repeat(64), humanReviewRequired: true,
  automaticallyFinalized: false, createdAt: '2026-11-12T21:30:00Z',
  details: { labelSpace: 'original_source_labels', perView: [{ imageId: 'I-000001', label: 'Fresh',
    confidence: .85, modelVersion: 'ag055-original-labels-v1', experimental: true,
    proposedGrade: null, confidenceCalibrated: false }] },
}

test('AG055 I03: authenticated exploratory HTTP flow rejects grade contamination', async t => {
  const previousFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  globalThis.fetch = async url => ({ ok: true, status: 200, json: async () => url.endsWith('/auth/me')
    ? { roles: ['operador'] } : { access_token: 'test-token', token_type: 'bearer' } })
  await loginOperator('test', 'fixture')
  globalThis.fetch = async (url, options) => {
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer test-token')
    if (url.endsWith('/status')) return { ok: true, status: 200, json: async () => ({
      evaluationId: 'E-000001', experimental: true, reason: 'original labels', models: [{
        task: 'TQ', labels: ['Fresh','Rotten'], modelVersion: 'v1', modelSha256: 'a'.repeat(64),
      }],
    }) }
    assert.equal(options.method, 'POST')
    return { ok: true, status: 200, json: async () => [exploratoryRow] }
  }
  assert.equal((await getExploratoryQualityStatus('E-000001')).models[0].task, 'TQ')
  assert.equal((await analyzeExploratoryQuality('E-000001'))[0].proposedGrade, null)
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => [{ ...exploratoryRow, proposedGrade: 'E0' }] })
  await assert.rejects(analyzeExploratoryQuality('E-000001'), ApiDataError)
})

test('AG055 I03: malformed, calibrated or E0 outputs never become exploratory views', () => {
  assert.equal(exploratoryViews(exploratoryRow.details).length, 1)
  for (const change of [{ label: 'E0' }, { confidence: NaN }, { confidence: 2 },
    { confidenceCalibrated: true }, { proposedGrade: 'E2' }]) {
    assert.deepEqual(exploratoryViews({ ...exploratoryRow.details,
      perView: [{ ...exploratoryRow.details.perView[0], ...change }] }), [])
  }
})

test('AG055 I04: uncertainty scores reject fabricated calibration and malformed margins', () => {
  const view=exploratoryRow.details.perView[0]
  for (const extra of [{ scoresUncalibrated: { E0: .9 } }, { scoresUncalibrated: { Fresh: 'certain' } },
    { uncertainty: { margin: NaN, priority: 'priority', reasons: [], thresholdSource: 'validation_only' } }]) {
    assert.deepEqual(exploratoryViews({ ...exploratoryRow.details, perView: [{...view,...extra}] }),[])
  }
})

test('AG055 I04: review queue refuses automatically accredited labels', async t => {
  const previous=globalThis.fetch
  t.after(()=>{globalThis.fetch=previous})
  globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({evaluationId:'E-000001',accreditationVerified:true,images:[]})})
  await assert.rejects(getQualityReviewQueue('E-000001'),ApiDataError)
})

test('AG055 pilot117: original labels and pilot E0/E1/E2 have disjoint contracts', () => {
  const v={...exploratoryRow.details.perView[0],label:'E1',scoresUncalibrated:{E0:.1,E1:.8,E2:.1},
    sampleUse:'training_photo',independentPerformanceEvaluated:false}
  const details={labelSpace:'pilot_declared_e0e1e2',perView:[v]}
  assert.equal(pilotViews(details).length,1)
  assert.deepEqual(exploratoryViews(details),[])
  assert.deepEqual(pilotViews({...details,labelSpace:'original_source_labels'}),[])
  assert.deepEqual(pilotViews({...details,perView:[{...v,independentPerformanceEvaluated:true}]}),[])
})

test('AG055 pilot117: human declarations retain null reviewer and review date', async t => {
  const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous})
  const queue={evaluationId:'E-000001',accreditationVerified:false,images:[{imageId:'I-000001',
    imageUrl:'/api/images/I-000001',imageSha256:'a'.repeat(64),status:'declared_pending_metadata',history:[{
      eventId:'imported',grade:'E1',reviewer:null,reviewedAt:null,evidence:null,rubricVersion:null,
      annotationPurpose:'human_label_declaration_import',importedAt:'2026-11-13T12:00:00Z',accreditationVerified:false,
    }]}]}
  globalThis.fetch=async()=>({ok:true,status:200,json:async()=>queue})
  const result=await getQualityReviewQueue('E-000001')
  assert.equal(result.images[0].history[0].reviewer,null)
  assert.equal(result.images[0].history[0].reviewedAt,null)
})

test('AG055 I03: actual React rendering separates original label, confidence and model version', async () => {
  const source = readFileSync(new URL('../src/features/quality/ExploratoryPanel.tsx',import.meta.url),'utf8')
  let code = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  } }).outputText
  for (const [name, url] of [
    ['react', import.meta.resolve('react')], ['react/jsx-runtime', import.meta.resolve('react/jsx-runtime')],
    ['../../services/agroscanApi', new URL('../src/services/agroscanApi.ts',import.meta.url).href],
    ['./exploratoryPolicy', new URL('../src/features/quality/exploratoryPolicy.ts',import.meta.url).href],
    ['./HumanReviewPanel', 'data:text/javascript,export function HumanReviewPanel(){return null}'],
  ]) code = code.replaceAll(`from "${name}"`, `from ${JSON.stringify(url)}`).replaceAll(`from '${name}'`, `from ${JSON.stringify(url)}`)
  const { ExploratoryResults } = await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))
  const html = renderToStaticMarkup(createElement(ExploratoryResults,{ rows: [exploratoryRow] }))
  assert.match(html, /Fresh/); assert.match(html, /85\.0/)
  assert.match(html, /no calibrada/); assert.match(html, /ag055-original-labels-v1/)
  assert.match(html, /No asigna E0\/E1\/E2/)
  assert.doesNotMatch(renderToStaticMarkup(createElement(ExploratoryResults,{ rows: [{...exploratoryRow,status:'experimental_proposal'}] })), /Fresh/)
  if (process.env.AG055_REAL_RUN) {
    const root = process.env.AG055_REAL_RUN
    const referencePath = `${root}/react_real_evidence.html`
    const referenceBefore = existsSync(referencePath) ? readFileSync(referencePath) : null
    const realRows = JSON.parse(readFileSync(`${root}/fastapi_real_evidence.json`, 'utf8'))
    const realHtml = renderToStaticMarkup(createElement(ExploratoryResults, { rows: realRows }))
    for (const row of realRows) for (const view of exploratoryViews(row.details)) {
      assert.ok(realHtml.includes(view.label))
      assert.ok(realHtml.includes((view.confidence * 100).toFixed(1)))
    }
    assert.match(realHtml, /ag055-original-labels-v1/)
    if (process.env.AG055_RENDER_EVIDENCE_OUTPUT) {
      writeFileSync(process.env.AG055_RENDER_EVIDENCE_OUTPUT, '<!doctype html><html lang="es"><meta charset="utf-8"><title>AgroScan · evidencia React real</title><body><h1>Resultados exploratorios de fotografías reales</h1>'+realHtml+'</body></html>', { flag: 'wx' })
    }
    if (referenceBefore) assert.deepEqual(readFileSync(referencePath), referenceBefore, 'Reference evidence must remain unchanged')
  }
})
