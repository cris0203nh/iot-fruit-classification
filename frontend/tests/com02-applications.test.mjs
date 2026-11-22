import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { tsxUrl } from './support/load-tsx.mjs'
import { ApiDataError, ApiResponseError, clearOperatorSession, loginAgroscan } from '../src/services/agroscanApi.ts'
import { APPLICATION_MESSAGE, submitApplication, listApplications } from '../src/features/commercial/applicationsApi.ts'

const plan = { id: 1, code: 'qa', version: 1, name: 'Referencia DEMO', description: 'Ensayo', amountCents: 19900,
  currency: 'PEN', period: 'monthly', benefits: [], limits: {}, isActive: true, recommended: true, demo: true }
const input = { companyName: 'Empresa sintética', contactName: 'Contacto sintético', contactEmail: 'qa@example.test',
  requestedPlanId: 1, requestedPeriod: 'monthly', idempotencyKey: 'synthetic-idempotency-com02' }
const receipt = { id: 'application-synthetic', status: 'pending', message: APPLICATION_MESSAGE }
const application = { ...input, id: receipt.id, status: 'pending', plan, source: 'public_web', createdAt: '2026-11-19T00:00:00Z' }
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })
function isolate(t) {
  const previous = globalThis.fetch
  clearOperatorSession()
  t.after(() => { globalThis.fetch = previous; clearOperatorSession() })
}

test('COM02: visitante envía plan/periodo y reintenta con la misma referencia sin precios ni privilegios', async t => {
  isolate(t)
  let calls = 0
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/commercial/applications')
    assert.equal(options.method, 'POST')
    assert.equal(new Headers(options.headers).has('Authorization'), false)
    assert.deepEqual(JSON.parse(options.body), input)
    calls++
    return response(receipt, calls === 1 ? 201 : 200)
  }
  assert.deepEqual(await submitApplication(input), receipt)
  assert.deepEqual(await submitApplication(input), receipt)
  assert.equal(calls, 2)
  assert.equal(Object.hasOwn(receipt, 'contactEmail'), false)
})

test('COM02: errores de validación, duplicado, límite y persistencia nunca muestran confirmación', async t => {
  isolate(t)
  for (const status of [404, 409, 413, 422, 429, 503]) {
    globalThis.fetch = async () => response({ detail: 'No se registró la solicitud' }, status)
    await assert.rejects(submitApplication(input), e => e instanceof ApiResponseError && e.status === status)
  }
  globalThis.fetch = async () => { throw new TypeError('offline') }
  await assert.rejects(submitApplication(input))
})

test('COM02: rechaza confirmaciones que confunden solicitud y contratación aprobada', async t => {
  isolate(t)
  for (const invalid of [{ status: 'approved' }, { message: 'Pago realizado' }, { id: 1 }]) {
    globalThis.fetch = async () => response({ ...receipt, ...invalid })
    await assert.rejects(submitApplication(input), ApiDataError)
  }
})

test('COM02: propietario consulta detalles paginados con JWT; filtros no envían contactos a URLs', async t => {
  isolate(t)
  globalThis.fetch = async url => url.endsWith('/api/auth/login')
    ? response({ access_token: 'synthetic-only', token_type: 'bearer', is_superadmin: true })
    : response({ id: 9, username: 'owner', fullName: 'QA', isSuperadmin: true })
  assert.equal(await loginAgroscan('owner', 'synthetic-password-only'), 'superadmin')
  globalThis.fetch = async (url, options) => {
    const query = new URL(url, 'http://qa.invalid')
    assert.equal(query.pathname, '/api/platform/commercial/applications')
    assert.deepEqual(Object.fromEntries(query.searchParams), { limit: '20', offset: '20', status: 'pending', plan_id: '1' })
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer synthetic-only')
    assert.doesNotMatch(url, /example|contact|email/)
    return response({ items: [application], total: 21, offset: 20, limit: 20 })
  }
  const data = await listApplications({ status: 'pending', planId: 1, offset: 20 })
  assert.equal(data.items[0].contactEmail, input.contactEmail)
  assert.equal(data.items[0].plan.version, 1)
})

test('COM02: consulta privada conserva denegaciones de autorización y valida respuestas', async t => {
  isolate(t)
  for (const status of [401, 403]) {
    globalThis.fetch = async () => response({ detail: 'Acceso denegado' }, status)
    await assert.rejects(listApplications(), e => e instanceof ApiResponseError && e.status === status)
  }
  for (const invalid of [{ status: 'paid' }, { status: 'toString' }, { contactEmail: null }, { plan: { ...plan, amountCents: -1 } }]) {
    globalThis.fetch = async () => response({ items: [{ ...application, ...invalid }], total: 1, limit: 20, offset: 0 })
    await assert.rejects(listApplications(), ApiDataError)
  }
})

test('COM02: formulario público accesible sin sesión; carga y enlace de comparación reales', async () => {
  const { CommercialApplicationPage } = await import(tsxUrl(new URL('../src/features/commercial/Applications.tsx', import.meta.url)))
  const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/solicitar?plan=1'] }, createElement(CommercialApplicationPage)))
  assert.match(html, /No necesitas iniciar sesión/)
  assert.match(html, /href="\/planes\?plan=1"/)
  assert.match(html, /role="status"/)
  assert.doesNotMatch(html, /Contraseña|Cerrar sesión|Pago aprobado/)
})

test('COM02: sección del propietario tiene navegación independiente y filtros etiquetados', async () => {
  const { OwnerWorkspace } = await import(tsxUrl(new URL('../src/pages/OwnerWorkspace.tsx', import.meta.url)))
  const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/plataforma/solicitudes'] }, createElement(OwnerWorkspace, { onLogout() {} })))
  assert.equal((html.match(/<h1\b/g) ?? []).length, 1)
  assert.match(html, /<h1>Solicitudes comerciales<\/h1>/)
  assert.match(html, /aria-current="page"/)
  assert.match(html, /<label>Estado<select/)
  assert.match(html, /<label>Plan solicitado<select/)
  assert.doesNotMatch(html, /id="commercial-heading"|id="platform-company-name"/)
})

test('COM02: formulario limita datos, conserva referencia en reintentos y mueve foco al confirmar', () => {
  const source = readFileSync(new URL('../src/features/commercial/Applications.tsx', import.meta.url), 'utf8')
  assert.match(source, /maxLength=\{254\}/)
  assert.match(source, /fieldset disabled=\{busy\}/)
  assert.match(source, /idempotency\.current\.payload !== payload/)
  assert.match(source, /confirmation\.current\?\.focus\(\)/)
  assert.match(source, /detailOpener\.current\?\.focus\(\)/)
  assert.doesNotMatch(source, /localStorage|sessionStorage|console\./)
})
