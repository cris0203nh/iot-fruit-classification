import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { tsxUrl } from './support/load-tsx.mjs'
import { clearOperatorSession, loginAgroscan, ApiDataError } from '../src/services/agroscanApi.ts'
import { submitApplication, APPLICATION_MESSAGE, NOTIFICATION_MESSAGES } from '../src/features/commercial/applicationsApi.ts'

const {PlanActions}=await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx',import.meta.url)))
const {PublicPlanCards}=await import(tsxUrl(new URL('../src/pages/CommercialLanding.tsx',import.meta.url)))
const {ApplicationPlanField}=await import(tsxUrl(new URL('../src/features/commercial/Applications.tsx',import.meta.url)))
const plan={id:37,code:'qa',version:1,name:'Plan sintético',description:'Descripción',amountCents:9900,currency:'PEN',period:'monthly',benefits:[],limits:{},isActive:true,recommended:true,demo:true}
const render=(C,props)=>renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:['/planes']},createElement(C,props)))
const json=(body,status=200)=>({ok:status<400,status,json:async()=>body})
function isolate(t){const previous=globalThis.fetch;clearOperatorSession();t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})}

test('COM05R1: ambos CTA públicos llevan al formulario con plan, nunca al checkout/login',t=>{
  isolate(t)
  for(const [Component,props] of [[PlanActions,{plan,enabled:true}],[PublicPlanCards,{plans:[plan]}]]){
    const html=render(Component,props)
    assert.match(html,/Solicitar plan/);assert.match(html,/href="\/solicitar\?plan=37"/)
    assert.doesNotMatch(html,/href="\/suscripcion|href="\/acceso/)
  }
})

test('COM05R1: checkout solo es acción adicional del administrador autenticado',async t=>{
  isolate(t)
  for(const role of ['administrador','operador','revisor']){
    clearOperatorSession()
    globalThis.fetch=async url=>url.endsWith('/api/auth/login')?json({access_token:'synthetic',token_type:'bearer'}):json({id:2,username:role,roles:[role],organizationId:1,organizations:[{id:1,name:'QA',roles:[role]}]})
    await loginAgroscan(role,'synthetic-test-only')
    const html=render(PlanActions,{plan,enabled:true})
    assert.match(html,/href="\/solicitar\?plan=37"/)
    assert.equal(html.includes('href="/suscripcion?plan=37"'),role==='administrador')
  }
})

test('COM05R1: select real preselecciona ID y responde a otro plan sin cambiar condiciones',()=>{
  const plans=[plan,{...plan,id:38,name:'Otro plan',period:'annual'}]
  for(const id of ['37','38']){
    const html=render(ApplicationPlanField,{plans,value:id,onChange(){}})
    assert.match(html,new RegExp(`<option value="${id}" selected=""`))
    assert.equal((html.match(/selected=""/g)??[]).length,1)
  }
  const code=readFileSync(new URL('../src/features/commercial/Applications.tsx',import.meta.url),'utf8')
  assert.match(code,/const planId = parameters.get\('plan'\)/)
  assert.match(code,/new URLSearchParams\(previous\)/)
  assert.doesNotMatch(code,/useState\(parameters.get\('plan'\)/)
  assert.match(code,/No necesitas iniciar sesión/)
})

test('COM05R1: envío anónimo guarda referencia y distingue aceptación SMTP, ausencia y fallo',async t=>{
  isolate(t)
  const input={companyName:'QA',contactName:'QA',contactEmail:'qa@example.test',requestedPlanId:37,requestedPeriod:'monthly',idempotencyKey:'synthetic-reference-only'}
  for(const ownerNotification of ['sent','disabled','failed','pending','sending','not_requested']){
    globalThis.fetch=async(url,options)=>{
      assert.equal(url,'/api/commercial/applications');assert.equal(new Headers(options.headers).has('Authorization'),false)
      assert.deepEqual(JSON.parse(options.body),input)
      return json({id:'synthetic',status:'pending',message:APPLICATION_MESSAGE,ownerNotification},201)
    }
    assert.equal((await submitApplication(input)).ownerNotification,ownerNotification)
  }
  assert.match(NOTIFICATION_MESSAGES.disabled,/deshabilitado.*guardada/)
  assert.match(NOTIFICATION_MESSAGES.sent,/servidor de correo aceptó.*no confirma/)
  assert.match(NOTIFICATION_MESSAGES.failed,/guardada.*no se pudo confirmar/)
  globalThis.fetch=async()=>json({id:'synthetic',status:'pending',message:APPLICATION_MESSAGE,ownerNotification:'guaranteed_delivery'})
  await assert.rejects(submitApplication(input),ApiDataError)
})

test('COM05R1: confirmación y estados de correo visibles con status, sin afirmación incondicional de envío',()=>{
  const code=readFileSync(new URL('../src/features/commercial/Applications.tsx',import.meta.url),'utf8')
  assert.match(code,/<h2 ref=\{confirmation\} tabIndex=\{-1\}>\{APPLICATION_MESSAGE\}/)
  assert.match(code,/role="status">\{NOTIFICATION_MESSAGES\[receipt.ownerNotification\]\}/)
  assert.doesNotMatch(code,/correo enviado|pago realizado|console\./i)
})
