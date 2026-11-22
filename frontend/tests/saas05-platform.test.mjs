import assert from 'node:assert/strict'
import test from 'node:test'
import { tsxUrl } from './support/load-tsx.mjs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ApiDataError, ApiResponseError, clearOperatorSession, createPlatformAdministrator,
  createPlatformOrganization, designatePlatformAdministrator, getSessionRole, isAgroscanAuthenticated,
  isOperatorAuthenticated, isPlatformOwner, listPlatformAdministrators, loadPlatformOverview,
  loginAgroscan, removePlatformAdministrator, setPlatformOrganizationStatus } from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
const json = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const metrics = { organizations: 2, activeOrganizations: 1, users: 5, activeUsers: 4, evaluations: 7 }
const organizations = [{ id: 1, name: 'Company A', isActive: true, userCount: 3, evaluationCount: 7 }]
const users = [{ id: 4, username: 'company-admin', fullName: 'Company Admin', isActive: true }]

async function ownerLogin(t) {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/api/auth/login')) return json({ access_token: 'synthetic-owner', token_type: 'bearer', is_superadmin: true })
    assert.equal(url, '/api/platform/me')
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer synthetic-owner')
    return json({ id: 9, username: 'private-owner', fullName: 'Private Owner', isSuperadmin: true })
  }
  assert.equal(await loginAgroscan('private-owner', 'synthetic-password'), 'superadmin')
}

test('SaaS-05: propietario sin membresía inicia en plataforma sin convertirse en administrador empresarial', async (t) => {
  await ownerLogin(t)
  assert.equal(isPlatformOwner(), true)
  assert.equal(isAgroscanAuthenticated(), true)
  assert.equal(getSessionRole(), null)
  assert.equal(isOperatorAuthenticated(), false)
  clearOperatorSession()
  assert.equal(isPlatformOwner(), false)
})

test('SaaS-05: el cliente requiere validación real del propietario, no solo el indicador del login', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  globalThis.fetch = async (url) => url.endsWith('/api/auth/login')
    ? json({ access_token: 'not-owner', token_type: 'bearer', is_superadmin: true })
    : json({ detail: 'No autorizado' }, 403)
  await assert.rejects(loginAgroscan('fake-owner','synthetic-password'), ApiResponseError)
  assert.equal(isPlatformOwner(), false)
  assert.equal(isAgroscanAuthenticated(), false)
})

test('SaaS-05: administrador empresarial no obtiene el panel aunque el perfil incluya un indicador', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  globalThis.fetch = async (url) => url.endsWith('/api/auth/login')
    ? json({ access_token: 'company-admin', token_type: 'bearer', is_superadmin: false })
    : json({ roles:['administrador'], organizationId:1, isSuperadmin:true })
  await loginAgroscan('company-admin','synthetic-password')
  assert.equal(isPlatformOwner(), false)
  globalThis.fetch = async () => { assert.fail('No debe consultar endpoints globales') }
  await assert.rejects(loadPlatformOverview(), (error) => error instanceof ApiResponseError && error.status===403)
})

test('SaaS-05: resumen usa métricas del servidor y rechaza conteos inválidos', async (t) => {
  await ownerLogin(t)
  let invalid = false
  globalThis.fetch = async (url, options) => {
    assert.equal(new Headers(options.headers).get('Authorization'),'Bearer synthetic-owner')
    assert.equal(new Headers(options.headers).has('X-Organization-ID'),false)
    if(url.endsWith('/metrics')) return json(invalid ? {...metrics,evaluations:-1} : metrics)
    if(url.endsWith('/organizations')) return json(organizations)
    if(url.endsWith('/users')) return json(users)
    throw new Error('Unexpected endpoint')
  }
  assert.deepEqual(await loadPlatformOverview(),{metrics,organizations,users})
  invalid=true
  await assert.rejects(loadPlatformOverview(),ApiDataError)
})

test('SaaS-05: registro, suspensión y designación usan contratos limitados y retirada maneja 204', async (t) => {
  await ownerLogin(t)
  const calls=[]
  globalThis.fetch=async(url,options)=>{
    calls.push({url,method:options.method,body:options.body ? JSON.parse(options.body) : undefined})
    if(url==='/api/platform/organizations') return json({...organizations[0],id:3,name:'New Company',userCount:0,evaluationCount:0},201)
    if(url.endsWith('/status')) return json({id:3,name:'New Company',isActive:false})
    if(options.method==='PUT') return json({organizationId:3,userId:4,role:'administrador',isActive:true})
    if(options.method==='DELETE') return {ok:true,status:204,json:()=>{assert.fail('204 no contiene JSON')}}
    return json(users)
  }
  assert.equal((await createPlatformOrganization(' New Company ')).id,3)
  await setPlatformOrganizationStatus(3,false)
  await designatePlatformAdministrator(3,4)
  assert.deepEqual(await listPlatformAdministrators(3),users)
  await removePlatformAdministrator(3,4)
  assert.deepEqual(calls.map(c=>c.method),['POST','PATCH','PUT',undefined,'DELETE'])
  assert.deepEqual(calls[0].body,{name:'New Company'})
  assert.deepEqual(calls[1].body,{isActive:false})
  assert.equal(calls[2].body,undefined)
})

test('SaaS-05: cuenta nueva recibe solo administrador empresarial y no autoridad de plataforma', async (t) => {
  await ownerLogin(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/platform/organizations/1/administrators')
    assert.equal(options.method,'POST')
    const body=JSON.parse(options.body)
    assert.equal(body.role,'administrador')
    assert.equal(body.password,'Synthetic-Password-Only!')
    assert.equal('isSuperadmin' in body,false)
    return json(users[0],201)
  }
  assert.deepEqual(await createPlatformAdministrator(1,{username:'company-admin',fullName:'Company Admin',password:'Synthetic-Password-Only!'}),users[0])
})

test('SaaS-05: resumen React presenta los conteos proporcionados por el servidor', async () => {
  const {PlatformSummary}=await import(tsxUrl(new URL('../src/pages/PlatformDashboard.tsx',import.meta.url)))
  const html=renderToStaticMarkup(createElement(PlatformSummary,{metrics}))
  assert.match(html,/<strong>2<\/strong>/)
  assert.match(html,/<strong>5<\/strong>/)
  assert.match(html,/<strong>7<\/strong>/)
  assert.match(html,/Empresas · 1 activas/)
  assert.match(html,/Usuarios · 4 activos/)
  assert.doesNotMatch(html,/JWT|SQLite|password|token/)
})
