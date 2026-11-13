import assert from 'node:assert/strict'
import test from 'node:test'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { exploratoryViews } from '../src/features/quality/exploratoryPolicy.ts'
import { pilotViews } from '../src/features/quality/pilotPolicy.ts'
import { v2Views } from '../src/features/quality/v2Policy.ts'
import { getExploratoryQualityStatus, analyzeExploratoryQuality, ApiDataError,
  loginOperator, clearOperatorSession, getQualityReviewQueue, getV2QualityStatus, analyzeV2Quality } from '../src/services/agroscanApi.ts'
const api=readFileSync(new URL('../src/services/agroscanApi.ts',import.meta.url),'utf8')
const panel=readFileSync(new URL('../src/features/quality/QualityProposalPanel.tsx',import.meta.url),'utf8')

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
