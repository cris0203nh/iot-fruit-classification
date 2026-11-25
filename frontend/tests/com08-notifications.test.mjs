import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { tsxUrl } from './support/load-tsx.mjs'
import { getNotifications, retryNotification, notificationRetryEligible } from '../src/features/commercial/notificationsApi.ts'
import { ApiDataError, ApiResponseError, clearOperatorSession, loginAgroscan } from '../src/services/agroscanApi.ts'

const row = { id:'synthetic-notice', organizationId:1, event:'subscription_activated', reference:'synthetic-order',
  recipient:'admin@example.test', subject:'AgroScan DEMO', status:'pending', attempts:0, createdAt:'2026-11-23T12:00:00Z',
  lastAttemptAt:null, nextAttemptAt:null, smtpAcceptedAt:null, errorCode:null }
const overview = { items:[row], total:1, statistics:{pending:1}, smtp:{enabled:false, configured:false, reason:'smtp_disabled'},
  maxAttempts:5, organizations:[{id:1, name:'Synthetic company'}] }
const json = (body, status=200) => ({ok:status < 400, status, json:async()=>body})
const render = (Component, props={}, path='/plataforma/notificaciones') => renderToStaticMarkup(
  createElement(MemoryRouter, {initialEntries:[path]}, createElement(Component, props)))

test('COM08: API usa filtros del propietario y reintenta sin destinatario ni contenido arbitrario', async t => {
  const previous = globalThis.fetch
  t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})
  clearOperatorSession()
  globalThis.fetch = async url => url.endsWith('/api/auth/login')
    ? json({access_token:'synthetic',token_type:'bearer',is_superadmin:true,csrf_token:'a'.repeat(64)})
    : json({id:9,username:'owner',fullName:'Owner',isSuperadmin:true})
  await loginAgroscan('owner','synthetic-password')
  const calls=[]
  globalThis.fetch=async(url,options)=>{calls.push([url,options]); return json(url.includes('/retry') ? {...row,status:'smtp_accepted',attempts:1} : overview)}
  assert.equal((await getNotifications(new URLSearchParams({organization_id:'1',status:'pending'}))).total,1)
  assert.equal((await retryNotification(row.id)).status,'smtp_accepted')
  assert.equal(calls[0][0],'/api/platform/notifications?organization_id=1&status=pending')
  assert.equal(calls[1][1].body,'{}')
  assert.equal(calls[1][1].credentials,'include')
  assert.equal(new Headers(calls[1][1].headers).get('X-CSRF-Token'),'a'.repeat(64))
})

test('COM08: autorización denegada y datos inválidos nunca se presentan como éxito', async t => {
  const previous=globalThis.fetch
  t.after(()=>{globalThis.fetch=previous;clearOperatorSession()})
  clearOperatorSession()
  globalThis.fetch=async()=>json({detail:'Acceso denegado'},403)
  await assert.rejects(getNotifications(new URLSearchParams()), error=>error instanceof ApiResponseError && error.status===403)
  globalThis.fetch=async()=>json({...overview,items:[{...row,status:'delivered'}]})
  await assert.rejects(getNotifications(new URLSearchParams()),ApiDataError)
})

test('COM08: elegibilidad respeta estado, espera, máximo y resultados inciertos',()=>{
  assert.equal(notificationRetryEligible(row,5),true)
  for(const status of ['processing','smtp_accepted','failed','omitted']) assert.equal(notificationRetryEligible({...row,status},5),false)
  assert.equal(notificationRetryEligible({...row,attempts:5},5),false)
  assert.equal(notificationRetryEligible({...row,nextAttemptAt:'2099-01-01T00:00:00Z'},5),false)
  assert.equal(notificationRetryEligible({...row,status:'retry_pending',nextAttemptAt:'2020-01-01T00:00:00Z'},5),true)
})

test('COM08: tabla real distingue aceptación SMTP, errores y estado vacío sin inventar entregas',async()=>{
  const {NotificationTable}=await import(tsxUrl(new URL('../src/features/commercial/Notifications.tsx',import.meta.url)))
  const html=render(NotificationTable,{data:{...overview,items:[{...row,status:'smtp_accepted',attempts:1}]},busy:null,onRetry(){}})
  assert.match(html,/Aceptada por SMTP/)
  assert.match(html,/no acredita entrega en buzón/)
  assert.match(html,/scope="col"/)
  assert.match(html,/tabindex="0"/)
  assert.match(html,/disabled=""/)
  const uncertain=render(NotificationTable,{data:{...overview,items:[{...row,status:'failed',errorCode:'delivery_uncertain'}]},busy:null,onRetry(){}})
  assert.match(uncertain,/Resultado incierto/)
  assert.match(render(NotificationTable,{data:{...overview,items:[],total:0},busy:null,onRetry(){}}),/No hay notificaciones para estos filtros/)
})

test('COM08: ruta del propietario reutiliza sidebar y estado de carga accesible',async()=>{
  const {OwnerWorkspace}=await import(tsxUrl(new URL('../src/pages/OwnerWorkspace.tsx',import.meta.url)))
  const html=render(OwnerWorkspace,{onLogout(){}})
  assert.match(html,/<h1[^>]*>Notificaciones comerciales<\/h1>/)
  assert.match(html,/href="\/plataforma\/notificaciones"[^>]*aria-current="page"|aria-current="page"[^>]*href="\/plataforma\/notificaciones"/)
  assert.match(html,/role="status"/)
  assert.doesNotMatch(html,/id="commercial-heading"|id="platform-company-name"/)
})
