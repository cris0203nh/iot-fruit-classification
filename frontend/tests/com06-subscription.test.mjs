import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {MemoryRouter} from 'react-router-dom'
import {tsxUrl} from './support/load-tsx.mjs'
import {clearOperatorSession,loginAgroscan,ApiDataError} from '../src/services/agroscanApi.ts'
import {getCompanyCommerce,getCommercialOverview,createDemoOrder,DEMO_NOTICE} from '../src/features/commercial/commercialApi.ts'

const plan={id:1,code:'qa',version:1,name:'Plan DEMO',description:'Condiciones',amountCents:9900,currency:'PEN',period:'monthly',benefits:['Historial'],limits:{},isActive:true,recommended:false,demo:true}
const trace={applicationId:'synthetic-app',organizationId:3,stage:'awaiting_demo_order',approvedPlan:plan,approvedPlanAvailable:true,invitationId:7,orderId:null,subscriptionId:null}
const subscription={id:8,organizationId:3,plan,status:'expired',startsAt:'2026-10-01T00:00:00Z',endsAt:'2026-11-19T00:00:00Z',graceEndsAt:'2026-11-26T00:00:00Z',inGracePeriod:true,cancellationEffect:'immediate',notice:DEMO_NOTICE}
const order={id:'synthetic-order',organizationId:3,plan,amountCents:9900,status:'pending',action:'subscribe',createdAt:'2026-11-01T00:00:00Z',expiresAt:'2026-11-02T00:00:00Z',isExpired:true,notice:DEMO_NOTICE}
const json=body=>({ok:true,status:200,json:async()=>body})
function isolate(t){const previous=globalThis.fetch;clearOperatorSession();t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})}
const render=(C,props)=>renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:['/suscripcion']},createElement(C,props)))

test('COM06: consulta de empresa conserva propuesta aprobada y referencias completas de activación',async t=>{
  isolate(t)
  for(const onboarding of [trace,{...trace,stage:'completed',orderId:'first-order',subscriptionId:8}]){
    globalThis.fetch=async()=>json({subscription,orders:[order],transactions:[],simulatorEnabled:true,notice:DEMO_NOTICE,onboarding})
    const data=await getCompanyCommerce();assert.deepEqual(data.onboarding,onboarding);assert.equal(data.subscription.inGracePeriod,true)
  }
})

test('COM06: versiones retiradas requieren confirmación explícita sin enviar importe ni empresa',async t=>{
  isolate(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/commercial/orders')
    assert.deepEqual(JSON.parse(options.body),{planId:1,action:'subscribe',idempotencyKey:'synthetic-first-order-key',acceptUpdatedPlan:true})
    return json(order)
  }
  assert.equal((await createDemoOrder(1,'subscribe','synthetic-first-order-key',true)).amountCents,9900)
})

test('COM06: rechaza etapa completa sin referencia y gracia incoherente',async t=>{
  isolate(t)
  for(const changes of [{onboarding:{...trace,stage:'completed'}},{onboarding:{...trace,stage:'paid'}},{subscription:{...subscription,graceEndsAt:null}},{subscription:{...subscription,cancellationEffect:'delete_data'}}]){
    globalThis.fetch=async()=>json({subscription,orders:[],transactions:[],simulatorEnabled:true,notice:DEMO_NOTICE,onboarding:trace,...changes})
    await assert.rejects(getCompanyCommerce(),ApiDataError)
  }
})

test('COM06: propietario recibe incorporaciones verificadas junto a movimientos DEMO',async t=>{
  isolate(t)
  const completed={...trace,stage:'completed',orderId:'first-order',subscriptionId:8}
  globalThis.fetch=async()=>json({activeDemoSubscriptions:1,expiringSoon:0,activePlans:1,simulatedTotalCents:9900,subscriptions:[subscription],orders:[order],transactions:[],notice:DEMO_NOTICE,onboardings:[completed]})
  assert.deepEqual((await getCommercialOverview()).onboardings,[completed])
})

test('COM06: vigencia y cancelación explican efectos sin bloqueos ni pérdida de históricos',async()=>{
  const {SubscriptionLifecycle,OrderHistory}=await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx',import.meta.url)))
  const grace=render(SubscriptionLifecycle,{subscription})
  assert.match(grace,/Gracia informativa/);assert.match(grace,/no reactiva/);assert.match(grace,/No se borran históricos/)
  const cancelled=render(SubscriptionLifecycle,{subscription:{...subscription,status:'cancelled',inGracePeriod:false,graceEndsAt:null}})
  assert.match(cancelled,/Cancelación inmediata/);assert.match(cancelled,/Sin periodo de gracia/)
  const history=render(OrderHistory,{orders:[order],onResume(){}})
  assert.match(history,/Vencida para confirmación/);assert.match(history,/No se realizaron cobros/)
})

test('COM06: roles operativos no obtienen checkout y el administrador conserva carga protegida',async t=>{
  isolate(t)
  const {SubscriptionPage}=await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx',import.meta.url)))
  for(const role of ['operador','revisor','administrador']){
    clearOperatorSession();globalThis.fetch=async url=>url.endsWith('/api/auth/login')?json({access_token:'synthetic',token_type:'bearer'}):json({id:2,username:role,roles:[role],organizationId:3,organizations:[{id:3,name:'QA',roles:[role]}]})
    await loginAgroscan(role,'synthetic-test-only')
    const html=render(SubscriptionPage)
    if(role==='administrador')assert.match(html,/Consultando suscripción/)
    else assert.match(html,/Solo el administrador de tu empresa/)
  }
})

test('COM06: checkout conserva confirmación, doble clic protegido y cambios explícitos',()=>{
  const code=readFileSync(new URL('../src/features/commercial/Commercial.tsx',import.meta.url),'utf8')
  assert.match(code,/if \(inFlight.current\) return/)
  assert.match(code,/Confirmar simulación — sin cobro/)
  assert.match(code,/reinicia la vigencia sin prorrateos/)
  assert.match(code,/He revisado y confirmo las condiciones/)
  assert.match(code,/order.isExpired/)
})
