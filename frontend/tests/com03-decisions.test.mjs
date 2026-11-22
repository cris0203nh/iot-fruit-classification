import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { tsxUrl } from './support/load-tsx.mjs'
import { decideApplication, applicationOrganizations } from '../src/features/commercial/applicationsApi.ts'
import { ApiDataError, ApiResponseError, clearOperatorSession, loginAgroscan } from '../src/services/agroscanApi.ts'

const plan={id:1,code:'qa',version:1,name:'Plan DEMO',description:'Ensayo',amountCents:9900,currency:'PEN',period:'monthly',benefits:[],limits:{},isActive:true,recommended:true,demo:true}
const application={id:'synthetic',companyName:'Empresa sintética',contactName:'Contacto sintético',contactEmail:'qa@example.test',requestedPlanId:1,requestedPeriod:'monthly',createdAt:'2026-11-19T00:00:00Z',source:'public_web',status:'pending',plan,decisions:[],organizationId:null,provisioningState:'not_provisioned'}
const decision={action:'approve',reason:'Identidad verificada',identityConfirmed:true,approvedPlanId:1,idempotencyKey:'synthetic-com03-reference'}
const result=action=>({...application,status:{approve:'approved',reject:'rejected',review:'under_review'}[action],organizationId:action==='approve'?3:null,provisioningState:action==='approve'?'awaiting_admin':'not_provisioned',decisions:[{id:1,action,reason:'Identidad verificada',actorUserId:1,createdAt:'2026-11-19T00:00:00Z',organizationId:action==='approve'?3:null}]})
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body})
function isolate(t){const previous=globalThis.fetch;clearOperatorSession();t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})}

test('COM03: propietario confirma y reintenta la misma decisión con JWT y sin precio enviado',async t=>{
  isolate(t)
  globalThis.fetch=async url=>url.endsWith('/api/auth/login')?response({access_token:'synthetic',token_type:'bearer',is_superadmin:true}):response({id:1,username:'owner',fullName:'QA',isSuperadmin:true})
  await loginAgroscan('owner','synthetic-test-only')
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/platform/commercial/applications/synthetic/decision')
    assert.equal(options.method,'POST');assert.equal(new Headers(options.headers).get('Authorization'),'Bearer synthetic')
    assert.deepEqual(JSON.parse(options.body),decision);return response(result('approve'))
  }
  assert.deepEqual(await decideApplication('synthetic',decision),result('approve'))
  assert.deepEqual(await decideApplication('synthetic',decision),result('approve'))
})

test('COM03: rechazo y revisión conservan los estados decididos por servidor',async t=>{
  isolate(t)
  for(const action of ['reject','review']){
    globalThis.fetch=async()=>response(result(action))
    const value=await decideApplication('synthetic',{action,reason:'Motivo administrativo',idempotencyKey:'synthetic-other-reference'})
    assert.equal(value.organizationId,null);assert.equal(value.provisioningState,'not_provisioned')
  }
})

test('COM03: autorización, conflicto y error de persistencia no producen aprobación local',async t=>{
  isolate(t)
  for(const status of [401,403,404,409,422,503]){
    globalThis.fetch=async()=>response({detail:'Decisión no guardada'},status)
    await assert.rejects(decideApplication('synthetic',decision),e=>e instanceof ApiResponseError&&e.status===status)
  }
})

test('COM03: rechaza aprobación incoherente sin empresa, trazabilidad o estado de aprovisionamiento',async t=>{
  isolate(t)
  for(const invalid of [{organizationId:null},{provisioningState:'active'},{decisions:[]},{id:'another'},{status:'pending'},{decisions:[{action:'approve',actorUserId:'owner'}]}]){
    globalThis.fetch=async()=>response({...result('approve'),...invalid})
    await assert.rejects(decideApplication('synthetic',decision),ApiDataError)
  }
})

test('COM03: reutiliza consulta de empresas y conserva suspensiones para vinculación explícita',async t=>{
  isolate(t)
  const companies=[{id:1,name:'Empresa A',isActive:false}]
  globalThis.fetch=async url=>{assert.equal(url,'/api/platform/organizations');return response(companies)}
  assert.deepEqual(await applicationOrganizations(),companies)
  globalThis.fetch=async()=>response([{id:1,name:'A'}])
  await assert.rejects(applicationOrganizations(),ApiDataError)
})

test('COM03: acciones disponibles solo en solicitudes abiertas y diálogo accesible separado',async()=>{
  const {ApplicationDecisionPanel}=await import(tsxUrl(new URL('../src/features/commercial/ApplicationDecisionPanel.tsx',import.meta.url)))
  for(const status of ['pending','under_review','approved','rejected']){
    const html=renderToStaticMarkup(createElement(ApplicationDecisionPanel,{application:{...application,status},onSaved(){}}))
    assert.match(html,/aria-labelledby="application-decision-title"/)
    if(['pending','under_review'].includes(status)){
      assert.match(html,/>Aprobar<\/button>/);assert.match(html,/>Rechazar<\/button>/);assert.match(html,/aria-haspopup="dialog"/)
    }else assert.doesNotMatch(html,/>Aprobar<\/button>|>Rechazar<\/button>/)
  }
})

test('COM03: confirmación, bloqueo de doble clic, Escape y recuperación de foco explícitos',()=>{
  const code=readFileSync(new URL('../src/features/commercial/ApplicationDecisionPanel.tsx',import.meta.url),'utf8')
  assert.match(code,/if \(working\.current\) return/)
  assert.match(code,/retry\.current\.payload !== payload/)
  assert.match(code,/onCancel=.*working\.current.*preventDefault/)
  assert.match(code,/trigger\.current\.focus\(\)/)
  assert.match(code,/maxLength=\{1000\}/)
  assert.match(code,/type="checkbox" required/)
  assert.match(code,/no crea administradores, invitaciones ni suscripciones/)
  assert.doesNotMatch(code,/localStorage|console\.|password/)
})
