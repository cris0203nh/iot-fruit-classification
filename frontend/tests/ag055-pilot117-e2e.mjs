/** Real pilot model/photo inference; declaration copies plus explicitly automated corrections. */
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {mkdirSync,writeFileSync} from 'node:fs'
import path from 'node:path'

const root=process.env.AG055_I04_EVIDENCE
if (!root || !process.env.AG055_PILOT117_RUN) throw Error('Audited pilot fixture required')
const require=createRequire(path.join(process.env.AG055_PLAYWRIGHT_ROOT,'probe.cjs'))
const browser=await require('playwright').chromium.launch({headless:true,executablePath:process.env.AG055_CHROMIUM_PATH})
const context=await browser.newContext({viewport:{width:1366,height:1000}})
const page=await context.newPage();const directory=path.join(root,'browser');mkdirSync(directory)
const steps=[],responses=[],network=[],consoleLog=[],errors=[],pending=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('console',m=>consoleLog.push({type:m.type(),text:m.text()}))
page.on('response',r=>{
  network.push({path:new URL(r.url()).pathname,status:r.status(),method:r.request().method()})
  if(r.url().includes('/vision/quality/'))pending.push(r.json().then(body=>responses.push({path:new URL(r.url()).pathname,status:r.status(),body})).catch(()=>{}))
})
try{
  const identity=await context.request.get('http://127.0.0.1:18004/_ag055_test_instance')
  assert.equal((await identity.json()).instanceType,'isolated_ag055_e2e')
  for(const [eid,product] of [['E-000001','tomate'],['E-000003','mango']]){
    await page.goto('http://127.0.0.1:5174/trazabilidad/'+eid)
    await page.locator('#agroscan-login-user').fill('i04_operador')
    await page.locator('#agroscan-login-pass').fill(process.env.AG055_TEST_PASSWORD)
    await page.locator('button[type=submit]').click()
    const panel=page.getByRole('region',{name:'Piloto E0 E1 E2 experimental'})
    await panel.getByRole('button',{name:'Analizar piloto E0/E1/E2',exact:true}).waitFor()
    const response=page.waitForResponse(r=>r.url().endsWith('/pilot/analyze'))
    await panel.getByRole('button',{name:'Analizar piloto E0/E1/E2',exact:true}).click()
    const result=await(await response).json();assert.equal(result.length,1)
    assert.equal(result[0].status,'experimental_e0e1e2_pilot');assert.equal(result[0].proposedGrade,null)
    assert.equal(result[0].details.perView[0].sampleUse,'training_photo')
    await panel.getByText('Fotografía utilizada para entrenar:',{exact:false}).waitFor()
    await panel.screenshot({path:path.join(directory,product+'-pilot.png')})
    const repeat=page.waitForResponse(r=>r.url().endsWith('/pilot/analyze'))
    await panel.getByRole('button',{name:'Analizar piloto E0/E1/E2',exact:true}).click()
    assert.equal((await(await repeat).json())[0].id,result[0].id)
    await panel.getByRole('button',{name:/Revisar piloto/}).click()
    const review=panel.getByRole('region',{name:/Revisión humana I-/})
    await review.getByText('Revisor no declarado',{exact:false}).waitFor()
    await review.getByText('Fecha de revisión no declarada',{exact:false}).waitFor()
    assert.equal(await review.locator('ol>li').count(),1)
    await review.getByLabel('Grado de revisión',{exact:true}).selectOption('no_evaluable')
    await review.getByLabel('Versión de rúbrica',{exact:true}).fill(product==='mango'?'mango-ext-pilot-test':'tomato-ext-pilot-test')
    await review.getByLabel('Justificación y evidencia',{exact:true}).fill('Ensayo automatizado de corrección; NO revisión humana auténtica ni ground truth.')
    await review.getByLabel('He observado y confirmado la ROI').check()
    await review.getByLabel('Declaro que esta revisión es humana').check()
    await review.getByRole('button',{name:'Guardar corrección como nuevo evento'}).click()
    await review.getByText('Revisión guardada como nuevo evento.',{exact:false}).waitFor()
    assert.equal(await review.locator('ol>li').count(),2)
    await panel.screenshot({path:path.join(directory,product+'-declaration-and-correction.png')})
    const old=page.getByRole('region',{name:'Resultados exploratorios de etiquetas originales'})
    await old.getByRole('button',{name:'Explorar fotografías persistidas'}).click()
    await old.getByText('Confianza no calibrada',{exact:false}).first().waitFor()
    steps.push(product+'_pilot_real_inference_idempotent_declaration_correction_and_original_models_coexist')
    if(product==='mango'){
      await page.setViewportSize({width:390,height:844})
      await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=1)
      await panel.screenshot({path:path.join(directory,'mobile-pilot.png')})
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1))
    }
  }
  assert.deepEqual(errors,[])
  writeFileSync(path.join(directory,'result.json'),JSON.stringify({passed:true,steps,pageErrors:errors,
    realInference:true,allPhotosFromTraining:true,independentPerformanceEvaluated:false,
    annotationPurpose:'automated_test_not_human_ground_truth'},null,2))
}catch(e){await page.screenshot({path:path.join(directory,'failure.png'),fullPage:true});throw e}
finally{
  await Promise.allSettled(pending)
  for(const [name,value] of [['sanitized-quality-responses',responses],['network',network],['console',consoleLog]])writeFileSync(path.join(directory,name+'.json'),JSON.stringify(value,null,2))
  writeFileSync(path.join(directory,'browser-runtime.json'),JSON.stringify({browser:browser.version(),playwright:require('playwright/package.json').version},null,2))
  await browser.close()
}
console.log('Real pilot117 browser acceptance passed',steps)
