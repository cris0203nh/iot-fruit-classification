/** Real Chromium + React + FastAPI + real photos. Only the dedicated isolated fixture. */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const root=process.env.AG055_I04_EVIDENCE
if (!root || !process.env.AG055_PLAYWRIGHT_ROOT || !process.env.AG055_TEST_PASSWORD) throw Error('Missing isolated E2E environment')
const { chromium }=createRequire(path.join(process.env.AG055_PLAYWRIGHT_ROOT,'probe.cjs'))('playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.AG055_CHROMIUM_PATH})
const context=await browser.newContext({viewport:{width:1366,height:1000}})
const page=await context.newPage()
const evidence=path.join(root,'browser'); mkdirSync(evidence,{recursive:true})
const responses=[], steps=[], errors=[]
const network=[], consoleLog=[], pendingReads=[]
let token=null
page.on('console',m=>consoleLog.push({type:m.type(),text:m.text()}))
page.on('pageerror',e=>errors.push(e.message))
page.on('requestfailed',r=>network.push({path:new URL(r.url()).pathname,method:r.method(),failure:r.failure()?.errorText}))
page.on('response',r=>{
  network.push({path:new URL(r.url()).pathname,method:r.request().method(),status:r.status()})
  if (r.url().endsWith('/api/auth/login') && r.ok()) {
    pendingReads.push(r.json().then(v=>{token=v.access_token}))
  }
  if (r.url().includes('/vision/quality/') && !r.url().includes('/images/')) {
    pendingReads.push((async()=>{try {responses.push({path:new URL(r.url()).pathname,status:r.status(),body:await r.json()})} catch { /* aborted requests recorded by step */ }})())
  }
})
const panel=page.getByRole('region',{name:'Resultados exploratorios de etiquetas originales'})
const shot=async name=>{await panel.screenshot({path:path.join(evidence,name+'.png')});steps.push(name)}
try {
  const identity=await context.request.get('http://127.0.0.1:18004/_ag055_test_instance')
  assert.equal(identity.status(),200,'Refuse to submit test annotations outside the isolated fixture')
  assert.equal((await identity.json()).instanceType,'isolated_ag055_e2e')
  await page.goto('http://127.0.0.1:5174/trazabilidad/E-000001')
  await page.locator('#agroscan-login-user').fill('i04_operador')
  await page.locator('#agroscan-login-pass').fill(process.env.AG055_TEST_PASSWORD)
  await page.locator('button[type=submit]').click()
  await panel.getByRole('button',{name:'Explorar fotografías persistidas'}).waitFor()
  steps.push('operator_authenticated_existing_evaluation_selected')
  const inference=page.waitForResponse(r=>r.url().endsWith('/exploratory/analyze') && r.request().method()==='POST')
  await panel.getByRole('button',{name:'Explorar fotografías persistidas'}).click()
  const first=await (await inference).json()
  assert.ok(first.length>=1); assert.ok(first.every(r=>r.proposedGrade===null))
  const tq=first.find(r=>r.details.task==='TQ')
  if (process.env.AG055_I05_AUDIT==='1') {
    assert.ok(token)
    const headers={Authorization:`Bearer ${token}`}
    const missing=await context.request.post('http://127.0.0.1:18004/api/evaluations/E-000002/vision/quality/exploratory/analyze',{headers})
    assert.equal(missing.status(),409)
    const unauthorized=await context.request.get('http://127.0.0.1:18004/api/evaluations/E-000001/vision/quality/reviews')
    assert.equal(unauthorized.status(),401)
    const revisor=await context.request.post('http://127.0.0.1:18004/api/auth/login',{form:{username:'i04_revisor',password:process.env.AG055_TEST_PASSWORD}})
    const reviewerToken=(await revisor.json()).access_token
    const denied=await context.request.post('http://127.0.0.1:18004/api/evaluations/E-000001/vision/quality/reviews',{
      headers:{Authorization:`Bearer ${reviewerToken}`},data:{imageId:'I-000001',predictionId:tq.id,grade:'E1',
        roi:tq.details.perView[0].roi,roiConfirmed:true,humanConfirmed:true,rubricVersion:'tomato-ext-test',
        evidence:'R03 automated permissions check; not human evidence',expectedLastEventId:null}})
    assert.equal(denied.status(),403)
    writeFileSync(path.join(evidence,'real-http-permissions.json'),JSON.stringify({missingPhotoStatus:missing.status(),
      anonymousStatus:unauthorized.status(),readOnlyReviewerPostStatus:denied.status()},null,2))
    steps.push('real_http_no_photo_409_anonymous_401_reviewer_403')
  }
  assert.equal(tq.details.perView[0].label,'Fresh') // Real original Rotten, known false negative
  assert.ok(tq.details.perView[0].uncertainty.reasons.includes('potential_rotten_prioritize_review'))
  await panel.getByText('Confianza no calibrada',{exact:false}).first().waitFor()
  await shot('01-real-inference-uncertainty')
  const repeat=page.waitForResponse(r=>r.url().endsWith('/exploratory/analyze'))
  await panel.getByRole('button',{name:'Explorar fotografías persistidas'}).click()
  assert.deepEqual((await (await repeat).json()).map(r=>r.id),first.map(r=>r.id))
  steps.push('repeat_inference_idempotent')
  await panel.getByRole('button',{name:`Revisar I-000001 · inferencia ${tq.id}`,exact:true}).click()
  const review=panel.getByRole('region',{name:'Revisión humana I-000001'})
  await review.locator('img').waitFor()
  await page.waitForFunction(()=>document.querySelector('.quality-review canvas')?.width>0)
  const initialEvents=await review.locator('ol>li').count()
  await review.getByLabel('Grado de revisión',{exact:true}).selectOption('E1')
  await review.getByLabel('Versión de rúbrica',{exact:true}).fill('tomato-ext-i04-test-only')
  await review.getByLabel('Justificación y evidencia',{exact:true}).fill('R03 prueba automatizada funcional; superficie visible en ROI central. NO etiqueta humana real.')
  await review.getByLabel('He observado y confirmado la ROI').check()
  await review.getByLabel('Declaro que esta revisión es humana').check() // Explicitly marked automated_test in server; never training ground truth
  if (process.env.AG055_I05_AUDIT==='1') {
    await page.route('**/vision/quality/reviews',route=>route.request().method()==='POST'
      ? route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'No se pudo persistir la revisión; reintentar'})})
      : route.continue())
    await review.getByRole('button',{name:/Guardar (revisión humana|corrección como nuevo evento)/}).click()
    await review.getByText('No se pudo persistir la revisión; reintentar',{exact:true}).waitFor()
    assert.equal(await review.locator('ol>li').count(),initialEvents)
    await shot('02a-storage-failure-no-false-success')
    await page.unroute('**/vision/quality/reviews')
  }
  await review.getByRole('button',{name:/Guardar (revisión humana|corrección como nuevo evento)/}).click()
  await review.getByText('Revisión guardada como nuevo evento.',{exact:false}).waitFor()
  assert.equal(await review.locator('ol>li').count(),initialEvents+1)
  await shot('02-review-event-test-only')
  await review.getByLabel('Grado de revisión',{exact:true}).selectOption('no_evaluable')
  await review.getByLabel('Justificación y evidencia',{exact:true}).fill('Corrección de prueba automatizada: no evaluable en este ensayo funcional; NO anotación agronómica.')
  await review.getByLabel('He observado y confirmado la ROI').check()
  await review.getByLabel('Declaro que esta revisión es humana').check()
  const corrected=page.waitForResponse(r=>r.url().endsWith('/quality/reviews')&&r.request().method()==='POST')
  await review.getByRole('button',{name:'Guardar corrección como nuevo evento'}).click()
  assert.equal((await (await corrected).json()).grade,'no_evaluable')
  await page.waitForFunction(n=>document.querySelectorAll('.quality-review ol>li').length===n,initialEvents+2)
  await shot('03-correction-preserves-history')
  // Full reload requires reauthentication by design (session token is memory-only).
  await page.reload()
  await page.locator('#agroscan-login-user').fill('i04_operador')
  await page.locator('#agroscan-login-pass').fill(process.env.AG055_TEST_PASSWORD)
  await page.locator('button[type=submit]').click()
  await panel.getByRole('button',{name:`Revisar I-000001 · inferencia ${tq.id}`,exact:true}).click()
  await panel.getByText('Revisado',{exact:false}).first().waitFor()
  assert.equal(await panel.locator('.quality-review ol>li').count(),initialEvents+2)
  steps.push('history_recovered_after_reauthentication_no_duplicate_events')
  await page.setViewportSize({width:390,height:844})
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=1)
  await shot('04-mobile-review')
  await panel.locator('.quality-review').scrollIntoViewIfNeeded()
  await page.screenshot({path:path.join(evidence,'04-mobile-viewport.png')})
  const mobile=await panel.locator('.quality-review').evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth}))
  assert.ok(mobile.scroll<=mobile.width+1,JSON.stringify(mobile))
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Page must fit mobile viewport')
  // Fault injection covers UI fallbacks; successful inference above uses real backend/models.
  await page.route('**/exploratory/analyze',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Se requiere una fotografía persistida'})}))
  await panel.getByRole('button',{name:'Explorar fotografías persistidas'}).click()
  await panel.getByRole('alert').filter({hasText:'Se requiere una fotografía persistida'}).waitFor()
  await shot('05-http-no-photo-error');await page.unroute('**/exploratory/analyze')
  await page.route('**/exploratory/analyze',route=>route.abort('connectionfailed'))
  await panel.getByRole('button',{name:'Explorar fotografías persistidas'}).click()
  await panel.getByRole('alert').filter({hasText:'No se pudo contactar'}).waitFor()
  await shot('06-disconnection');await page.unroute('**/exploratory/analyze')
  await page.route('**/exploratory/status',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({evaluationId:'E-000001',experimental:true,models:[],reason:'no installed model'})}))
  await page.reload()
  await page.locator('#agroscan-login-user').fill('i04_operador')
  await page.locator('#agroscan-login-pass').fill(process.env.AG055_TEST_PASSWORD)
  await page.locator('button[type=submit]').click()
  await panel.getByText('Sin modelo exploratorio instalado para este producto.',{exact:true}).waitFor()
  await shot('07-no-model');await page.unroute('**/exploratory/status')
  assert.deepEqual(errors,[])
  writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,steps,pageErrors:errors,
    realInference:true,faultInjection:['HTTP no photo','network abort','no model status',
      ...(process.env.AG055_I05_AUDIT==='1' ? ['review storage 503 UI simulation'] : [])],
    annotationPurpose:'automated_test_not_human_ground_truth'},null,2))
} catch(e) {
  await page.screenshot({path:path.join(evidence,'failure.png'),fullPage:true})
  writeFileSync(path.join(evidence,'failure.txt'),String(e.stack))
  throw e
} finally {
  await Promise.allSettled(pendingReads)
  writeFileSync(path.join(evidence,'sanitized-quality-responses.json'),JSON.stringify(responses,null,2))
  writeFileSync(path.join(evidence,'network.json'),JSON.stringify(network,null,2))
  writeFileSync(path.join(evidence,'console.json'),JSON.stringify(consoleLog,null,2))
  writeFileSync(path.join(evidence,'browser-runtime.json'),JSON.stringify({browser:browser.version(),
    playwright:createRequire(path.join(process.env.AG055_PLAYWRIGHT_ROOT,'probe.cjs'))('playwright/package.json').version},null,2))
  await browser.close()
}
console.log('AG055 I04 browser E2E passed:',steps)
