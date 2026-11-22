import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { tsxUrl } from './support/load-tsx.mjs'
import { ApiDataError, ApiResponseError, clearOperatorSession } from '../src/services/agroscanApi.ts'
import { manageInitialInvitation, listApplications } from '../src/features/commercial/applicationsApi.ts'
import { invitationLink } from '../src/features/auth/googleGis.ts'

const token='A'.repeat(43)
const invitation={id:1,email:'contact@example.test',role:'administrador',source:'platform_owner',status:'pending',expiresAt:'2026-12-01T00:00:00Z',createdAt:'2026-11-29T00:00:00Z',acceptedAt:null,acceptedBy:null,revokedAt:null,revokedBy:null}
const command={action:'issue',idempotencyKey:'synthetic-initial-admin-key'}
const plan={id:1,code:'qa',version:1,name:'Plan DEMO',description:'Ensayo',amountCents:9900,currency:'PEN',period:'monthly',benefits:[],limits:{},isActive:true,recommended:false,demo:true}
const application={id:'synthetic',companyName:'Empresa QA',contactName:'Contacto QA',contactEmail:invitation.email,requestedPlanId:1,requestedPeriod:'monthly',createdAt:invitation.createdAt,source:'public_web',status:'approved',plan,organizationId:3,provisioningState:'awaiting_admin',initialInvitation:null}
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body})
function isolate(t){const previous=globalThis.fetch;clearOperatorSession();t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})}

test('COM04: emisión y reintento usan la solicitud sin destinatario, rol o empresa manipulables',async t=>{
  isolate(t);let n=0
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/platform/commercial/applications/synthetic/administrator-invitation')
    assert.equal(options.method,'POST');assert.deepEqual(JSON.parse(options.body),command)
    return response({invitation,...(++n===1?{token}:{})},n===1?201:200)
  }
  assert.equal((await manageInitialInvitation('synthetic',command)).token,token)
  assert.equal((await manageInitialInvitation('synthetic',command)).token,undefined)
  const link=new URL(invitationLink('http://127.0.0.1:5188',token))
  assert.equal(link.search,'');assert.equal(link.hash,'#invitation='+token)
})

test('COM04: revocación/reemisión conservan estados y rechazan respuestas con privilegios o secretos incoherentes',async t=>{
  isolate(t)
  for(const action of ['revoke','reissue']){
    globalThis.fetch=async()=>response({invitation:{...invitation,status:action==='revoke'?'revoked':'pending'}})
    assert.equal((await manageInitialInvitation('synthetic',{...command,action})).token,undefined)
  }
  for(const invalid of [{role:'superadmin'},{source:'organization_admin'},{status:'active'}]){
    globalThis.fetch=async()=>response({invitation:{...invitation,...invalid},token})
    await assert.rejects(manageInitialInvitation('synthetic',command),ApiDataError)
  }
  globalThis.fetch=async()=>response({invitation,token})
  await assert.rejects(manageInitialInvitation('synthetic',{...command,action:'revoke'}),ApiDataError)
})

test('COM04: autorización, expiración, conflicto y error no simulan una emisión exitosa',async t=>{
  isolate(t)
  for(const status of [401,403,404,409,410,422,503]){
    globalThis.fetch=async()=>response({detail:'Invitación no disponible'},status)
    await assert.rejects(manageInitialInvitation('synthetic',command),e=>e instanceof ApiResponseError&&e.status===status)
  }
})

test('COM04: lectura privada reconoce administrador incorporado sin declarar suscripción activa',async t=>{
  isolate(t)
  globalThis.fetch=async()=>response({items:[{...application,provisioningState:'awaiting_demo_order',administratorActive:true,initialInvitation:{...invitation,status:'accepted',acceptedBy:8,acceptedAt:invitation.createdAt}}],total:1,limit:20,offset:0})
  const saved=(await listApplications()).items[0]
  assert.equal(saved.administratorActive,true);assert.equal(saved.provisioningState,'awaiting_demo_order')
})

test('COM04: panel ofrece acciones según estado y confirma la incorporación',async()=>{
  const {InitialAdministratorInvitation}=await import(tsxUrl(new URL('../src/features/commercial/InitialAdministratorInvitation.tsx',import.meta.url)))
  function render(value){return renderToStaticMarkup(createElement(InitialAdministratorInvitation,{application:value}))}
  assert.match(render(application),/Generar invitación inicial/)
  for(const status of ['pending','expired','revoked']){
    const html=render({...application,initialInvitation:{...invitation,status}})
    assert.match(html,/Reemitir enlace/)
    assert.equal(html.includes('Revocar invitación'),status==='pending')
    assert.doesNotMatch(html,/#invitation=/)
  }
  const accepted=render({...application,provisioningState:'awaiting_demo_order',administratorActive:true,initialInvitation:{...invitation,status:'accepted'}})
  assert.match(accepted,/Administrador incorporado.*y activo/)
  assert.doesNotMatch(accepted,/Reemitir enlace|Generar invitación inicial/)
})

test('COM04: aceptación reutiliza pantalla existente accesible y carga sin exponer token',async()=>{
  const {InvitationAcceptance}=await import(tsxUrl(new URL('../src/features/auth/InvitationAcceptance.tsx',import.meta.url)))
  const html=renderToStaticMarkup(createElement(InvitationAcceptance,{token,authenticated:false,onSuccess(){},onExisting(){},onCancel(){}}))
  assert.match(html,/Invitación empresarial/);assert.match(html,/role="status"/);assert.doesNotMatch(html,new RegExp(token))
})

test('COM04: contrato de UI incluye confirmación, recuperación de foco y limpieza de contraseña',()=>{
  const owner=readFileSync(new URL('../src/features/commercial/InitialAdministratorInvitation.tsx',import.meta.url),'utf8')
  assert.match(owner,/onCancel=.*inFlight\.current.*preventDefault/)
  assert.match(owner,/heading\.current\?\.focus/)
  assert.match(owner,/navigator\.clipboard\.writeText/)
  assert.doesNotMatch(owner,/localStorage|sessionStorage|console\./)
  const accept=readFileSync(new URL('../src/features/auth/InvitationAcceptance.tsx',import.meta.url),'utf8')
  assert.match(accept,/Acceso empresarial activado/)
  assert.match(accept,/Ir al panel de AgroScan/)
  assert.match(accept,/setPassword\(''\); setAcceptedRole/)
  assert.match(accept,/enlace venció, ya fue utilizado o fue revocado/)
  assert.match(accept,/inFlight\.current/)
})
