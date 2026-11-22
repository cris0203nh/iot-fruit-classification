import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadConfigFromFile } from 'vite'
import {
  ApiDataError, ApiResponseError, clearOperatorSession, getEvaluationById,
  getSessionRole, isAgroscanAuthenticated, isOperatorAuthenticated, loadProtectedEvidence, loginAgroscan, loginOperator, uploadEvaluationPhoto,
  restoreAgroscanSession, logoutAgroscan, selectOrganization, getSessionOrganizationId, request,
} from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
const fakeMe = { id: 1, username: 'operador', roles: ['operador'] }

test('DEV03: npm dev carga el proxy autorizado sin cabeceras secretas en el navegador', async t => {
  const root = mkdtempSync(join(tmpdir(),'agroscan-dev03-'))
  const keys = ['HOME','USERPROFILE','AGROSCAN_DEV_ROOT']
  const previous = Object.fromEntries(keys.map(key=>[key,process.env[key]]))
  t.after(()=>{
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key]
      else process.env[key] = previous[key]
    }
    assert.ok(resolve(root).startsWith(resolve(tmpdir())+sep))
    rmSync(root,{recursive:true})
  })
  process.env.HOME=root;process.env.USERPROFILE=root;delete process.env.AGROSCAN_DEV_ROOT
  assert.equal(homedir(),root)
  const dev=join(root,'Documents','AgroScan-Dev');mkdirSync(dev,{recursive:true})
  writeFileSync(join(dev,'manifest.json'),JSON.stringify({ready:true,instance:'synthetic-development-identity'}))
  const pkg=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8'))
  assert.equal(pkg.scripts.dev,'vite --config vite.dev.config.ts')
  const loaded=await loadConfigFromFile({command:'serve',mode:'development'},fileURLToPath(new URL('../vite.dev.config.ts',import.meta.url)))
  assert.ok(loaded)
  const proxy=loaded.config.server.proxy['/api']
  assert.equal(proxy.target,'http://127.0.0.1:8000')
  assert.equal(proxy.headers['X-AgroScan-Dev'],'synthetic-development-identity')
  assert.equal(proxy.changeOrigin,true)
  assert.equal(loaded.config.server.host,'localhost')
  const plugin=loaded.config.plugins.find(item=>item.name==='agroscan-development-connection-guard')
  assert.throws(()=>plugin.configResolved({env:{VITE_API_BASE_URL:'https://untrusted.example'}}),/API relativa/)
})

test('AUTH01: recarga y reapertura restauran permisos y empresa desde cookie, sin JWT persistente', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  const csrf = 'a'.repeat(64)
  let selected = 1
  let stored = false
  let restores = 0
  const organizations = [{id:1,name:'QA A',roles:['operador']},{id:2,name:'QA B',roles:['revisor']}]
  globalThis.fetch = async (url, options) => {
    assert.equal(options.credentials, 'include')
    assert.equal(options.cache, 'no-store')
    const headers = new Headers(options.headers)
    if (url.endsWith('/api/auth/login')) {
      assert.equal(headers.get('X-AgroScan-Session'), 'browser')
      stored = true
      return {ok:true,status:200,json:async()=>({access_token:'synthetic-only',token_type:'bearer',csrf_token:csrf,organization_id:selected})}
    }
    assert.equal(headers.has('Authorization'), false)
    if (url.endsWith('/api/auth/session/organization')) {
      assert.equal(headers.get('X-CSRF-Token'), csrf)
      selected = Number(headers.get('X-Organization-ID'))
      return {ok:true,status:200,json:async()=>({organizationId:selected})}
    }
    if (url.endsWith('/api/auth/session')) {
      restores++
      assert.equal(stored,true)
      return {ok:true,status:200,json:async()=>({access_token:'restored-synthetic',token_type:'bearer',csrf_token:csrf,organization_id:selected})}
    }
    assert.ok(url.endsWith('/api/auth/me'))
    const id = Number(headers.get('X-Organization-ID') ?? selected)
    return {ok:true,status:200,json:async()=>({id:1,username:'shared',roles:organizations[id-1].roles,organizationId:id,organizations})}
  }
  await loginAgroscan('shared','synthetic-password-only')
  await selectOrganization(2)
  clearOperatorSession() // Simula la perdida de memoria de F5; la cookie vive en el transporte.
  assert.deepEqual(await Promise.all([restoreAgroscanSession(),restoreAgroscanSession()]), ['revisor','revisor'])
  assert.equal(restores,1)
  assert.equal(getSessionOrganizationId(),2)
  assert.equal(getSessionRole(),'revisor')
})

test('AUTH01: expiracion y revocacion no conservan identidad ni contexto privado', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  for (const status of [401,403]) {
    clearOperatorSession()
    globalThis.fetch = async url => url.endsWith('/api/auth/session')
      ? {ok:true,status:200,json:async()=>({access_token:'synthetic',token_type:'bearer',csrf_token:'a'.repeat(64)})}
      : {ok:false,status,json:async()=>({detail:'Sesion o membresia revocada'})}
    assert.equal(await restoreAgroscanSession(),null)
    assert.equal(isAgroscanAuthenticated(),false)
    assert.equal(getSessionOrganizationId(),null)
  }
  globalThis.fetch = async()=>({ok:false,status:401,json:async()=>({detail:'Sesion vencida'})})
  assert.equal(await restoreAgroscanSession(),null)
})

test('AUTH01: renovar la misma sesion no interrumpe consultas operativas en curso', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  let release
  globalThis.fetch = async url => {
    if (url.endsWith('/api/slow')) return new Promise(resolve => { release = () => resolve({ok:true,status:200,json:async()=>({synthetic:true})}) })
    return {ok:true,status:200,json:async()=>url.endsWith('/api/auth/me') ? fakeMe
      : {access_token:'synthetic-only',token_type:'bearer',csrf_token:'d'.repeat(64)}}
  }
  await restoreAgroscanSession()
  const pending = request('/api/slow')
  await restoreAgroscanSession(true)
  release()
  assert.deepEqual(await pending,{synthetic:true})
  assert.equal(getSessionRole(),'operador')
})

test('AUTH01: propietario restaurado revalida la autoridad global en FastAPI', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  const paths = []
  globalThis.fetch = async url => {
    paths.push(url)
    return {ok:true,status:200,json:async()=>url.endsWith('/api/platform/me')
      ? {id:3,username:'synthetic-owner',isSuperadmin:true}
      : {access_token:'synthetic-only',token_type:'bearer',csrf_token:'e'.repeat(64),is_superadmin:true}}
  }
  assert.equal(await restoreAgroscanSession(),'superadmin')
  assert.deepEqual(paths,['/api/auth/session','/api/platform/me'])
  assert.equal(isAgroscanAuthenticated(),true)
  assert.equal(getSessionRole(),null)
})

test('AUTH01: renovacion y logout usan CSRF; cerrar sesion impide restauracion posterior', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  let revoked = false
  const csrf = 'b'.repeat(64)
  const calls = []
  globalThis.fetch = async (url,options) => {
    calls.push(url)
    if (url.endsWith('/api/auth/me')) return {ok:true,status:200,json:async()=>fakeMe}
    if (url.endsWith('/api/auth/session/refresh') || url.endsWith('/api/auth/logout')) {
      assert.equal(options.method,'POST')
      assert.equal(new Headers(options.headers).get('X-CSRF-Token'),csrf)
      assert.equal(options.credentials,'include')
    }
    if (url.endsWith('/api/auth/logout')) {revoked=true;return {ok:true,status:204}}
    return revoked ? {ok:false,status:401,json:async()=>({detail:'Revocada'})}
      : {ok:true,status:200,json:async()=>({access_token:'synthetic-only',token_type:'bearer',csrf_token:csrf})}
  }
  await restoreAgroscanSession()
  assert.equal(await restoreAgroscanSession(true),'operador')
  await logoutAgroscan()
  assert.equal(isAgroscanAuthenticated(),false)
  assert.equal(await restoreAgroscanSession(),null)
  assert.equal(calls.filter(url=>url.endsWith('/api/auth/logout')).length,1)
})

test('AUTH01: 401 durante navegacion o descarga invalida la sesion; logout fallido no finge cierre', async t => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  for (const [status, operation] of [[401,()=>request('/api/lots')], [401,()=>loadProtectedEvidence('/api/images/I-000003')],
    [403,()=>request('/api/lots')]]) {
    clearOperatorSession()
    globalThis.fetch = async url => ({ok:true,status:200,json:async()=>url.endsWith('/api/auth/me')
      ? fakeMe : {access_token:'synthetic-only',token_type:'bearer',csrf_token:'c'.repeat(64)}})
    await restoreAgroscanSession()
    globalThis.fetch = async()=>({ok:false,status:500,json:async()=>({detail:'Transporte no disponible'})})
    await assert.rejects(logoutAgroscan(),error=>error.status===500)
    assert.equal(isAgroscanAuthenticated(),true)
    globalThis.fetch = async()=>({ok:false,status,headers:new Headers({'X-AgroScan-Session-Invalid':'1'}),json:async()=>({detail:'Revocada'})})
    await assert.rejects(operation(),error=>error.status===status)
    assert.equal(isAgroscanAuthenticated(),false)
  }
})

test('AGROP-27/47: inicia sesión, verifica operador y autoriza evaluaciones y fotos', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  let calls = 0
  globalThis.fetch = async (url, options) => {
    calls += 1
    if (url.endsWith('/api/auth/login')) {
      assert.equal(options.method, 'POST')
      assert.equal(new URLSearchParams(options.body).get('username'), 'operador')
      return { ok: true, status: 200, json: async () => ({ access_token: 'token-de-prueba', token_type: 'bearer' }) }
    }
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer token-de-prueba')
    if (url.endsWith('/api/auth/me')) return { ok: true, status: 200, json: async () => fakeMe }
    if (url.endsWith('/api/evaluations/E-000008')) return { ok: true, status: 200, json: async () => ({
      id: 'E-000008', lotId: 'LOTE-1', pieceId: 'PIEZA-1', product: 'mango', registeredAt: new Date().toISOString(), status: 'processing', weightGrams: null, imageCount: 0, evidence: [], visualCategory: null, reviewNote: null, failureReason: null,
    }) }
    if (url.endsWith('/api/evaluations/E-000008/images')) {
      assert.equal(options.body.get('view'), 'vista-2')
      return { ok: true, status: 201, json: async () => ({ id: 'I-000008', view: 'vista-2', imageUrl: '/api/images/I-000008' }) }
    }
    throw new Error(`Endpoint inesperado: ${url}`)
  }
  await loginOperator('operador', 'clave-de-prueba')
  assert.equal(isOperatorAuthenticated(), true)
  assert.equal((await getEvaluationById('E-000008')).id, 'E-000008')
  const file = new File(['RGB'], 'vista2.png', { type: 'image/png' })
  assert.equal((await uploadEvaluationPhoto('E-000008', file, 'vista-2')).view, 'vista-2')
  assert.equal(calls, 4)
  clearOperatorSession()
  assert.equal(isOperatorAuthenticated(), false)
})

test('AGROP-47: un revisor no puede habilitar el flujo de captura', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => url.endsWith('/auth/me') ? { roles: ['revisor'] } : { access_token: 'token', token_type: 'bearer' } })
  await assert.rejects(loginOperator('revisor', 'clave'), (error) => error instanceof ApiResponseError && error.status === 403)
  assert.equal(isOperatorAuthenticated(), false)
})

test('AGROP-47: obtiene JPG protegido por cabecera, nunca por URL de token', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => url.endsWith('/auth/me') ? fakeMe : { access_token: 'token-de-prueba', token_type: 'bearer' } })
  await loginOperator('operador', 'clave')
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/images/I-000003')
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer token-de-prueba')
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'image/jpeg' }), blob: async () => new Blob(['jpeg'], { type: 'image/jpeg' }) }
  }
  assert.equal((await loadProtectedEvidence('/api/images/I-000003')).type, 'image/jpeg')
  await assert.rejects(loadProtectedEvidence('https://evil.example/images/I-000003'), ApiDataError)
  clearOperatorSession()
  await assert.rejects(loadProtectedEvidence('/api/images/I-000003'), (error) => error instanceof ApiResponseError && error.status === 401)
})

test('AGROP-35: revisor autenticado consulta historial y detalle, sin permiso de operador', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  const record = { id: 'E-000010', lotId: 'LOTE-R1', pieceId: 'P-001', product: 'mango', registeredAt: '2026-11-03T10:00:00+00:00', status: 'processing', weightGrams: null, imageCount: 1 }
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/api/auth/login')) return { ok: true, status: 200, json: async () => ({ access_token: 'token-revisor', token_type: 'bearer' }) }
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer token-revisor')
    if (url.endsWith('/api/auth/me')) return { ok: true, status: 200, json: async () => ({ id: 2, username: 'revisor', roles: ['revisor'] }) }
    if (url.endsWith('/api/evaluations')) return { ok: true, status: 200, json: async () => [record] }
    if (url.endsWith('/api/evaluations/E-000010')) return { ok: true, status: 200, json: async () => ({ ...record, evidence: [{ id: 'I-000004', view: 'vista-1', imageUrl: '/api/images/I-000004' }], visualCategory: null, reviewNote: null, failureReason: null }) }
    throw new Error('Endpoint inesperado')
  }
  assert.equal(await loginAgroscan('revisor', 'clave'), 'revisor')
  assert.equal(isAgroscanAuthenticated(), true)
  assert.equal(getSessionRole(), 'revisor')
  assert.equal(isOperatorAuthenticated(), false)
  assert.equal((await getEvaluationById('E-000010'))?.evidence.length, 1)
  clearOperatorSession()
  assert.equal(isAgroscanAuthenticated(), false)
  assert.equal(getSessionRole(), null)
})
