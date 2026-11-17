import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { ApiResponseError, acceptInvitation, clearOperatorSession, createInvitation, getSessionOrganizationId,
  getSessionRole, googleChallenge, googleConfiguration, isAgroscanAuthenticated, linkGoogle, listInvitations,
  loginAgroscan, loginGoogle, previewInvitation, registerInvitation, revokeInvitation } from '../src/services/agroscanApi.ts'
import { forgetInvitation, invitationFromLocation, invitationLink, loadGoogleSdk } from '../src/features/auth/googleGis.ts'

const previousFetch=globalThis.fetch
const token='I'.repeat(43)
const nonce='N'.repeat(43)
const credential='SYNTHETIC-ID-TOKEN'
const json=(value,status=200)=>({ok:status>=200&&status<300,status,json:async()=>value})
const company={id:2,name:'Company B',roles:['revisor']}
const profile={roles:['revisor'],organizationId:2,organizations:[company]}
const invitation={id:1,email:'recipient@example.test',role:'revisor',expiresAt:'2026-12-01T00:00:00Z',status:'pending'}

function cleanup(t){t.after(()=>{globalThis.fetch=previousFetch;clearOperatorSession()});clearOperatorSession()}

test('SaaS-06: configuración ausente conserva acceso tradicional; desafío pide cookie sin exponerla',async t=>{
  cleanup(t)
  globalThis.fetch=async()=>json({enabled:false,clientId:null})
  assert.deepEqual(await googleConfiguration(),{enabled:false,clientId:null})
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/auth/google/challenge')
    assert.equal(options.credentials,'include')
    assert.equal(new Headers(options.headers).get('X-AgroScan-Intent'),'google')
    return json({nonce})
  }
  assert.equal(await googleChallenge(),nonce)
})

test('SaaS-06: Google entrega ID token por cuerpo y conserva verificación local de roles',async t=>{
  cleanup(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url.includes(credential),false)
    if(url==='/api/auth/google/login'){
      assert.deepEqual(JSON.parse(options.body),{credential})
      assert.equal(options.credentials,'include')
      return json({access_token:'local-jwt',token_type:'bearer',is_superadmin:false})
    }
    assert.equal(url,'/api/auth/me')
    assert.equal(new Headers(options.headers).get('Authorization'),'Bearer local-jwt')
    return json(profile)
  }
  assert.equal(await loginGoogle(credential),'revisor')
  assert.equal(getSessionOrganizationId(),2)
  assert.equal(isAgroscanAuthenticated(),true)
})

test('SaaS-06: credencial Google rechazada no deja sesión activa',async t=>{
  cleanup(t)
  globalThis.fetch=async()=>json({detail:'Credencial no válida'},401)
  await assert.rejects(loginGoogle(credential),error=>error instanceof ApiResponseError&&error.status===401)
  assert.equal(isAgroscanAuthenticated(),false)
})

test('SaaS-06: vínculo exige JWT local y contraseña explícita sin modificar rol',async t=>{
  cleanup(t)
  globalThis.fetch=async url=>url==='/api/auth/login'?json({access_token:'local-jwt',token_type:'bearer'}):json(profile)
  await loginAgroscan('existing','synthetic-password')
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/auth/google/link')
    assert.equal(new Headers(options.headers).get('Authorization'),'Bearer local-jwt')
    assert.deepEqual(JSON.parse(options.body),{credential,password:'synthetic-password'})
    assert.equal(options.credentials,'include')
    return json({linked:true})
  }
  await linkGoogle(credential,'synthetic-password')
  assert.equal(getSessionRole(),'revisor')
})

test('SaaS-06: invitación manual solo usa fragmento y se retira antes de cargar servicios externos',()=>{
  assert.equal(invitationLink('https://agroscan.example',token),`https://agroscan.example/#invitation=${token}`)
  assert.throws(()=>invitationLink('https://agroscan.example','bad'))
  const previous=globalThis.window
  try{
    let replaced
    globalThis.window={location:{hash:`#invitation=${token}`,pathname:'/',search:''},history:{replaceState:(_s,_t,url)=>{replaced=url;globalThis.window.location.hash=''}}}
    assert.equal(invitationFromLocation(),token)
    assert.equal(replaced,'/')
    assert.equal(invitationFromLocation(),token)
    const next='J'.repeat(43)
    globalThis.window.location.hash=`#invitation=${next}`
    assert.equal(invitationFromLocation(),next)
    forgetInvitation()
    assert.equal(invitationFromLocation(),null)
  }finally{globalThis.window=previous;forgetInvitation()}
})

test('SaaS-06: SDK procede del origen fijo de Google, sin dependencias de terceros',async()=>{
  const previousWindow=globalThis.window,previousDocument=globalThis.document
  try{
    const sdk={accounts:{id:{initialize(){},renderButton(){},cancel(){}}}}
    globalThis.window={}
    globalThis.document={createElement:()=>({remove(){}}),head:{append(script){
      assert.equal(script.src,'https://accounts.google.com/gsi/client?hl=es')
      globalThis.window.google=sdk;script.onload()
    }}}
    assert.equal(await loadGoogleSdk(),sdk)
  }finally{globalThis.window=previousWindow;globalThis.document=previousDocument}
})

test('SaaS-06: registro invitado solo concede el rol devuelto por backend y selecciona su empresa',async t=>{
  cleanup(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url.includes(token),false)
    if(url==='/api/auth/invitations/register'){
      const body=JSON.parse(options.body)
      assert.equal(body.token,token)
      assert.equal('role'in body,false)
      assert.equal('organization_id'in body,false)
      return json({access_token:'invited-jwt',token_type:'bearer',is_superadmin:false,organization_id:2},201)
    }
    assert.equal(new Headers(options.headers).get('X-Organization-ID'),'2')
    return json(profile)
  }
  assert.equal(await registerInvitation(token,{username:'new-user',fullName:'New User',password:'synthetic-password'}),'revisor')
  assert.equal(getSessionOrganizationId(),2)
})

test('SaaS-06: listado no requiere enlaces; creación, vista previa y revocación usan cuerpos seguros',async t=>{
  cleanup(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url.includes(token),false)
    if(url==='/api/invitations'&&options.method==='POST')return json({...invitation,token},201)
    if(url==='/api/invitations')return json([invitation])
    if(url==='/api/auth/invitations/preview'){
      assert.deepEqual(JSON.parse(options.body),{token})
      return json({...invitation,organizationName:'Company B'})
    }
    assert.equal(options.method,'DELETE')
    return {ok:true,status:204}
  }
  assert.equal((await createInvitation('recipient@example.test','revisor')).token,token)
  assert.equal((await listInvitations()).length,1)
  assert.equal((await previewInvitation(token)).organizationName,'Company B')
  await revokeInvitation(1)
})

test('SaaS-06: cuenta existente acepta expresamente con contraseña y JWT vigente',async t=>{
  cleanup(t)
  globalThis.fetch=async url=>url==='/api/auth/login'?json({access_token:'old-jwt',token_type:'bearer'}):json({...profile,organizationId:1})
  await loginAgroscan('existing','synthetic-password')
  globalThis.fetch=async(url,options)=>{
    if(url==='/api/auth/invitations/accept'){
      assert.equal(new Headers(options.headers).get('Authorization'),'Bearer old-jwt')
      assert.deepEqual(JSON.parse(options.body),{token,password:'synthetic-password'})
      return json({access_token:'new-jwt',token_type:'bearer',organization_id:2})
    }
    assert.equal(new Headers(options.headers).get('Authorization'),'Bearer new-jwt')
    assert.equal(new Headers(options.headers).get('X-Organization-ID'),'2')
    return json(profile)
  }
  assert.equal(await acceptInvitation(token,'synthetic-password'),'revisor')
})

test('SaaS-06: Google invitado transmite ambos comprobantes solo por POST',async t=>{
  cleanup(t)
  globalThis.fetch=async(url,options)=>{
    if(url==='/api/auth/google/accept-invitation'){
      assert.deepEqual(JSON.parse(options.body),{credential,token})
      assert.equal(options.credentials,'include')
      return json({access_token:'google-invite-jwt',token_type:'bearer',organization_id:2})
    }
    return json(profile)
  }
  assert.equal(await loginGoogle(credential,token),'revisor')
})

test('SaaS-06: botón React incluye Continuar con Google sin rediseñar el acceso',async()=>{
  const source=readFileSync(new URL('../src/features/auth/GoogleAccess.tsx',import.meta.url),'utf8')
  let code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
  for(const [name,url]of[['react',import.meta.resolve('react')],['react/jsx-runtime',import.meta.resolve('react/jsx-runtime')],
    ['../../services/agroscanApi',new URL('../src/services/agroscanApi.ts',import.meta.url).href],
    ['./googleGis',new URL('../src/features/auth/googleGis.ts',import.meta.url).href]]){
    code=code.replaceAll(`from "${name}"`,`from ${JSON.stringify(url)}`).replaceAll(`from '${name}'`,`from ${JSON.stringify(url)}`)
  }
  const{GoogleAccessButton}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))
  const html=renderToStaticMarkup(createElement(GoogleAccessButton,{onCredential:async()=>{}}))
  assert.match(html,/Continuar con Google/)
  assert.match(html,/disabled/)
})
