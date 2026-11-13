/** Real V2 inference and rejected-photo review, isolated storage; automated annotations only. */
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {mkdirSync,writeFileSync} from 'node:fs'
import path from 'node:path'

const root=process.env.AG055_I04_EVIDENCE
if(!root || !process.env.AG055_V2_RUN)throw Error('Isolated V2 fixture required')
const require=createRequire(path.join(process.env.AG055_PLAYWRIGHT_ROOT,'probe.cjs'))
const browser=await require('playwright').chromium.launch({headless:true,executablePath:process.env.AG055_CHROMIUM_PATH})
const context=await browser.newContext({viewport:{width:1366,height:1000}})
const page=await context.newPage(),directory=path.join(root,'browser_v2');mkdirSync(directory)
const errors=[],responses=[],network=[],consoleLog=[],pending=[],steps=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('console',m=>consoleLog.push({type:m.type(),text:m.text()}))
page.on('response',r=>{
  network.push({path:new URL(r.url()).pathname,status:r.status(),method:r.request().method()})
  if(r.url().includes('/vision/quality/'))pending.push(r.json().then(body=>responses.push({path:new URL(r.url()).pathname,body})).catch(()=>{}))
})
try{
  assert.equal((await(await context.request.get('http://127.0.0.1:18004/_ag055_test_instance')).json()).instanceType,'isolated_ag055_e2e')
  for(const [eid,product,rejected] of [['E-000001','tomate',false],['E-000003','mango',false],['E-000004','rejected',true]]){
    await page.goto('http://127.0.0.1:5174/trazabilidad/'+eid)
    await page.locator('#agroscan-login-user').fill('i04_operador')
    await page.locator('#agroscan-login-pass').fill(process.env.AG055_TEST_PASSWORD)
    await page.locator('button[type=submit]').click()
    const panel=page.getByRole('region',{name:'V2 E0 E1 E2 experimental'})
    await panel.getByRole('button',{name:'Analizar V2 E0/E1/E2',exact:true}).waitFor()
    const call=page.waitForResponse(r=>r.url().endsWith('/v2/analyze'))
    await panel.getByRole('button',{name:'Analizar V2 E0/E1/E2',exact:true}).click()
    const response=await call;assert.equal(response.status(),200)
    const [row]=await response.json(),view=row.details.perView[0]
    assert.equal(row.status,'experimental_e0e1e2_v2');assert.equal(row.proposedGrade,null)
    assert.equal(view.evaluable,!rejected);assert.equal(view.independentPerformanceEvaluated,false)
    if(rejected){assert.equal(view.label,null);await panel.getByText('No evaluable · requiere revisión',{exact:true}).waitFor()}
    else {await panel.getByText(/Propuesta E[012] · NO confirmada/).waitFor();assert.equal(view.sampleUse,'training_photo')}
    await panel.screenshot({path:path.join(directory,product+'-inference.png')})
    const again=page.waitForResponse(r=>r.url().endsWith('/v2/analyze'))
    await panel.getByRole('button',{name:'Analizar V2 E0/E1/E2',exact:true}).click()
    assert.equal((await(await again).json())[0].id,row.id)
    await panel.getByRole('button',{name:/Revisar V2/}).click()
    const review=panel.getByRole('region',{name:/Revisión humana I-/})
    await review.getByLabel('Grado de revisión',{exact:true}).waitFor()
    await review.getByRole('img').first().waitFor()
    const before=await review.locator('ol>li').count()
    await review.getByLabel('Grado de revisión',{exact:true}).selectOption('no_evaluable')
    await review.getByLabel('Versión de rúbrica',{exact:true}).fill(row.product==='mango'?'mango-ext-v2-test':'tomato-ext-v2-test')
    await review.getByLabel('Justificación y evidencia',{exact:true}).fill('Ensayo AUTOMATIZADO V2; no revisión humana auténtica ni etiqueta agronómica.')
    await review.getByLabel('He observado y confirmado la ROI').check()
    await review.getByLabel('Declaro que esta revisión es humana').check()
    await review.getByRole('button',{name:'Guardar corrección como nuevo evento'}).click()
    await review.getByText('Revisión guardada como nuevo evento.',{exact:false}).waitFor()
    assert.equal(await review.locator('ol>li').count(),before+1)
    await panel.screenshot({path:path.join(directory,product+'-review.png')})
    assert.equal(await page.getByRole('region',{name:'Piloto E0 E1 E2 experimental'}).count(),1)
    steps.push({eid,product,rejected,modelVersion:row.modelVersion,inferenceId:row.id})
  }
  assert.deepEqual(errors,[])
  writeFileSync(path.join(directory,'result.json'),JSON.stringify({passed:true,steps,realInference:true,
    independentPerformanceEvaluated:false,annotationPurpose:'automated_test_not_human_ground_truth'},null,2))
}catch(e){await page.screenshot({path:path.join(directory,'failure.png'),fullPage:true});throw e}
finally{
  await Promise.allSettled(pending)
  for(const [name,data] of [['quality-responses',responses],['network',network],['console',consoleLog],['page-errors',errors]])writeFileSync(path.join(directory,name+'.json'),JSON.stringify(data,null,2))
  await browser.close()
}
console.log('V2 real-photo browser acceptance passed',steps)
