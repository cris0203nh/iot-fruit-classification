import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { tsxUrl } from './support/load-tsx.mjs'
import { clearOperatorSession, loginAgroscan } from '../src/services/agroscanApi.ts'
import { getCatalog, money } from '../src/features/commercial/commercialApi.ts'
import { forgetInvitation } from '../src/features/auth/googleGis.ts'

const source = name => readFileSync(new URL('../'+name,import.meta.url),'utf8')
const json = body => ({ok:true,status:200,json:async()=>body})
const plan={id:47,code:'qa',version:3,name:'Plan sintético desde API',description:'Descripción de catálogo',amountCents:12345,currency:'PEN',period:'annual',benefits:['Beneficio publicado'],limits:{evaluaciones:15},isActive:true,recommended:true,demo:true}
const {CommercialLanding,PublicPlanCards}=await import(tsxUrl(new URL('../src/pages/CommercialLanding.tsx',import.meta.url)))
const {AgroScanRoutes}=await import(tsxUrl(new URL('../src/App.tsx',import.meta.url)))
function render(Component,path='/',props={}){return renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:[path]},createElement(Component,props)))}
function isolate(t){const previous=globalThis.fetch;clearOperatorSession();forgetInvitation();t.after(()=>{globalThis.fetch=previous;clearOperatorSession();forgetInvitation()})}

test('COM05: landing pública semántica con proceso real, FAQ y acceso visible sin autenticación',()=>{
  const html=render(CommercialLanding)
  assert.equal((html.match(/<h1\b/g)??[]).length,1)
  for(const id of ['landing-content','beneficios','como-funciona','planes','preguntas'])assert.match(html,new RegExp(`id="${id}"`))
  assert.match(html,/href="#planes"[^>]*>Explorar planes DEMO/);assert.match(html,/href="\/acceso"/)
  assert.match(html,/<img[^>]+src="file:[^"]+agroscan-fruit-inspection\.webp"[^>]+alt="[^"]+"/)
  assert.match(html,/clasificación es asistida/);assert.match(html,/No hay registro público con privilegios/)
  assert.match(html,/no acredita resultados comerciales ni de hardware/)
  assert.match(html,/role="status"/);assert.match(html,/<details><summary>/)
  assert.match(html,/Sin cobros ni resultados certificados/)
  assert.doesNotMatch(html.replace('Sin cobros ni resultados certificados.', ''),
    /testimonios|certificad[oa]s|% de precisión|clientes satisfechos/i)
})

test('COM05: catálogo API real conserva importe, moneda, periodo, beneficios, versión y plan seleccionado',async t=>{
  isolate(t)
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,'/api/commercial/plans');assert.equal(new Headers(options.headers).has('Authorization'),false)
    return json({plans:[plan],simulatorEnabled:false,notice:'Pago simulado — No se realizó ningún cobro'})
  }
  const data=await getCatalog()
  const html=render(PublicPlanCards,'/',{plans:data.plans})
  assert.match(html,/<h3>Plan sintético desde API<\/h3>/)
  assert.ok(html.includes(money(12345)));assert.match(html,/año/);assert.match(html,/Beneficio publicado/)
  assert.match(html,/v3/);assert.match(html,/Recomendado/);assert.match(html,/href="\/solicitar\?plan=47"/)
  assert.doesNotMatch(html,/href="\/suscripcion/)
})

test('COM05: catálogo vacío o planes inactivos no inventan ofertas ni enlaces de contratación',()=>{
  for(const plans of [[],[{...plan,isActive:false}]]){
    const html=render(PublicPlanCards,'/',{plans})
    assert.match(html,/preparando el catálogo/);assert.doesNotMatch(html,/\/solicitar\?plan|Plan sintético/)
  }
})

test('COM05: rutas públicas reales muestran landing, catálogo y solicitud sin sesión',t=>{
  isolate(t)
  assert.match(render(AgroScanRoutes,'/'),/<h1 id="landing-title">/)
  for (const path of ['/planes', '/planes?plan=3']) assert.match(render(AgroScanRoutes,path),/id="plans-content"/)
  const form=render(AgroScanRoutes,'/solicitar?plan=47')
  assert.match(form,/Cuéntanos sobre tu empresa/);assert.match(form,/No necesitas iniciar sesión/)
  assert.doesNotMatch(form,/agroscan-login__submit/)
})

test('COM05: acceso y deep links privados mantienen AuthGate sin exponer paneles al visitante',t=>{
  isolate(t)
  for(const path of ['/acceso','/app','/historial/E-000001','/evaluacion','/suscripcion?plan=47','/plataforma/solicitudes']){
    const html=render(AgroScanRoutes,path)
    assert.match(html,/agroscan-login__submit/)
    assert.match(html,/Tu sesión se conserva al recargar mientras siga vigente/)
    assert.doesNotMatch(html,/vive solo en esta pestaña|se cierra al recargar/)
    assert.doesNotMatch(html,/id="landing-title"|Primer administrador empresarial|Datos de contacto de acceso exclusivo/)
  }
  for(const file of ['src/pages/ReviewQueuePage.tsx','src/pages/SectionPage.tsx']) {
    assert.match(source(file),/to="\/app"/)
    assert.doesNotMatch(source(file),/to="\/"/)
  }
})

test('COM05: usuarios autenticados conservan su inicio operativo y la landing sigue siendo pública',async t=>{
  isolate(t)
  for(const role of ['administrador','operador','revisor','superadmin']){
    clearOperatorSession()
    globalThis.fetch=async url=>url.endsWith('/api/auth/login')?json({access_token:'synthetic',token_type:'bearer',is_superadmin:role==='superadmin'})
      :role==='superadmin'?json({id:1,username:'owner',fullName:'QA',isSuperadmin:true})
        :json({id:2,username:role,roles:[role],organizationId:1,organizations:[{id:1,name:'QA',roles:[role]}]})
    await loginAgroscan(role,'synthetic-test-only')
    assert.match(render(AgroScanRoutes,'/'),/<h1 id="landing-title">/)
    const html=render(AgroScanRoutes,role==='superadmin'?'/plataforma/solicitudes':'/app')
    assert.match(html,/app-shell/);assert.doesNotMatch(html,/id="landing-title"|agroscan-login__submit/)
    if(role==='superadmin')assert.match(html,/<h1>Solicitudes comerciales<\/h1>/)
    else assert.match(html,/href="\/app"/)
  }
})

test('COM05: invitación antigua en fragmento llega a aceptación sin token en URL de acceso ni HTML',t=>{
  isolate(t)
  const previous=globalThis.window;const token='Z'.repeat(43);let stripped=false
  globalThis.window={location:{pathname:'/',search:'',hash:'#invitation='+token},history:{replaceState(_state,_title,path){assert.equal(path,'/');stripped=true;globalThis.window.location.hash=''}}}
  t.after(()=>{globalThis.window=previous;forgetInvitation()})
  const bridge=render(AgroScanRoutes,'/#invitation='+token)
  assert.equal(stripped,true);assert.doesNotMatch(bridge,new RegExp(token))
  const acceptance=render(AgroScanRoutes,'/acceso')
  assert.match(acceptance,/Invitación empresarial/);assert.match(acceptance,/Verificando invitación/)
  assert.doesNotMatch(acceptance,new RegExp(token))
  assert.match(source('src/features/commercial/PublicEntry.tsx'),/<Navigate to="\/acceso" replace/)
})

test('COM05: responsive, menú accesible, foco y contraste de texto principales',()=>{
  const css=source('src/pages/CommercialLanding.css'),header=source('src/components/layout/PublicHeader.tsx')
  assert.match(css,/@media \(max-width: 620px\)/);assert.match(css,/@media \(max-width: 850px\)/)
  assert.match(css,/grid-template-columns: 1fr/)
  assert.match(css,/min-height: 56px/);assert.match(css,/\.skip-link:focus/)
  assert.match(header,/aria-label="Abrir o cerrar menú comercial"/);assert.match(header,/event.key === 'Escape'/);assert.match(header,/summary'\)\?\.focus/)
  const linear=n=>{const v=n/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}
  const lum=hex=>{const rgb=hex.match(/../g).map(h=>linear(parseInt(h,16)));return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722}
  const variable = name => css.match(new RegExp(`--${name}: #([0-9a-f]{6});`))[1]
  for(const name of ['landing-ink','landing-muted'])assert.ok((lum(variable('landing-paper'))+.05)/(lum(variable(name))+.05)>=4.5)
})

test('COM05: SEO en HTML sin servicios externos ni importes duplicados en landing',()=>{
  const html=source('index.html'),landing=source('src/pages/CommercialLanding.tsx')
  assert.match(html,/<html lang="es">/);assert.match(html,/<title>AgroScan \| Clasificación asistida/)
  assert.match(html,/name="description"/);assert.match(html,/property="og:title"/);assert.match(html,/property="og:locale" content="es_PE"/)
  assert.match(landing,/getCatalog\(\)/);assert.match(landing,/No se mostrarán precios sin confirmar/)
  assert.doesNotMatch(landing,/amountCents:\s*\d|S\/\s*\d|https?:\/\//)
})
