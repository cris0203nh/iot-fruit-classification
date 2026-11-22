import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { tsxUrl } from './support/load-tsx.mjs'
import { ApiDataError, ApiResponseError, clearOperatorSession, loginAgroscan, selectOrganization } from '../src/services/agroscanApi.ts'
import { DEMO_NOTICE, parsePlan, money, getCatalog, getCompanyCommerce, createDemoOrder, confirmDemoOrder,
  cancelDemoSubscription, listCommercialPlans, saveCommercialPlan, setCommercialPlanStatus, getCommercialOverview, getCommercialPlanVersions } from '../src/features/commercial/commercialApi.ts'

const plan = { id: 1, code: 'cosecha', version: 1, name: 'Cosecha DEMO', description: 'Ensayo', amountCents: 19900,
  currency: 'PEN', period: 'monthly', benefits: ['Trazabilidad'], limits: { evaluaciones: 1000 }, isActive: true, recommended: true, demo: true }
const order = { id: 'synthetic-order', organizationId: 1, plan, amountCents: 19900, status: 'pending', action: 'subscribe', createdAt: '2026-11-18T00:00:00Z', notice: DEMO_NOTICE }
const subscription = { id: 1, organizationId: 1, plan, status: 'active', startsAt: '2026-11-18T00:00:00Z', endsAt: '2026-12-18T00:00:00Z', notice: DEMO_NOTICE }
const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data })
function isolated(t) {
  const previous = globalThis.fetch
  clearOperatorSession()
  t.after(() => { globalThis.fetch = previous; clearOperatorSession() })
}
async function admin(t) {
  isolated(t)
  globalThis.fetch = async url => url.endsWith('/api/auth/login') ? json({ access_token: 'synthetic-only', token_type: 'bearer', organization_id: 1 })
    : json({ id: 4, username: 'admin-demo', roles: ['administrador'], organizationId: 1, organizations: [{ id: 1, name: 'A', roles: ['administrador'] }] })
  assert.equal(await loginAgroscan('admin-demo', 'test-password-only'), 'administrador')
}
test('Comercial: planes publicos renderizan iconos y conservan el enlace de solicitud del plan 3', async t => {
  isolated(t)
  const { PlansPage, PlanActions } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  for (const path of ['/planes', '/planes?plan=3']) {
    const render = (Component, props = {}) => renderToStaticMarkup(createElement(MemoryRouter,
      { initialEntries: [path] }, createElement(Component, props)))
    const html = render(PlansPage)
    assert.match(html, /id="plans-content"/)
    assert.match(html, /class="commerce-public__visual"/)
    assert.ok((html.match(/<svg\b/g) ?? []).length >= 4)
    assert.match(html, /role="status"/)
    const actions = render(PlanActions, { plan: { ...plan, id: 3 }, enabled: true })
    assert.match(actions, /href="\/solicitar\?plan=3"/)
    assert.doesNotMatch(actions, /href="\/(?:acceso|suscripcion)/)
  }
})
test('Comercial: catálogo público conserva precio, versión, beneficios y señal DEMO', async t => {
  isolated(t)
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/commercial/plans'); assert.equal(new Headers(options.headers).has('Authorization'), false)
    return json({ plans: [plan], simulatorEnabled: true, notice: DEMO_NOTICE })
  }
  assert.deepEqual((await getCatalog()).plans, [plan])
  assert.match(money(19900), /199/)
})
test('Comercial: no acepta catálogo con precios, moneda o versiones incoherentes', () => {
  for (const invalid of [{ amountCents: -1 }, { amountCents: 2.5 }, { currency: 'USD' }, { version: 0 }, { demo: false }, { benefits: [1] }, { limits: { x: -1 } }]) {
    assert.throws(() => parsePlan({ ...plan, ...invalid }), ApiDataError)
  }
})
test('Comercial: selección y reintentos envían solo plan, operación y referencia; nunca precio', async t => {
  await admin(t)
  const requests = []
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/commercial/orders'); requests.push(JSON.parse(options.body))
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer synthetic-only')
    assert.equal(new Headers(options.headers).get('X-Organization-ID'), '1')
    return json(order, 201)
  }
  const first = await createDemoOrder(1, 'subscribe', 'idempotency-synthetic')
  assert.deepEqual(await createDemoOrder(1, 'subscribe', 'idempotency-synthetic'), first)
  assert.deepEqual(requests, Array(2).fill({ planId: 1, action: 'subscribe', idempotencyKey: 'idempotency-synthetic' }))
})
test('Comercial: aprobación, rechazo y cancelación usan el resultado confirmado por backend', async t => {
  await admin(t)
  for (const [scenario, status] of [['approve', 'demo_approved'], ['reject', 'demo_rejected'], ['cancel', 'cancelled']]) {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/commercial/orders/synthetic-order/confirm')
      assert.deepEqual(JSON.parse(options.body), { scenario })
      return json({ ...order, status })
    }
    assert.equal((await confirmDemoOrder(order.id, scenario)).status, status)
  }
})
test('Comercial: recarga recupera suscripción e historial persistidos; renovación y cancelación usan API', async t => {
  await admin(t)
  const company = { subscription, orders: [{ ...order, status: 'demo_approved' }], transactions: [], simulatorEnabled: true, notice: DEMO_NOTICE }
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/subscription/cancel')) return json({ ...subscription, status: 'cancelled' })
    if (url.endsWith('/orders')) { assert.equal(JSON.parse(options.body).action, 'renew'); return json({ ...order, action: 'renew' }) }
    return json(company)
  }
  assert.deepEqual(await getCompanyCommerce(), company)
  assert.deepEqual(await getCompanyCommerce(), company)
  assert.equal((await createDemoOrder(1, 'renew', 'renewal-reference')).action, 'renew')
  assert.equal((await cancelDemoSubscription()).status, 'cancelled')
})
test('Comercial: denegaciones, aislamiento y simulador deshabilitado no producen éxito local', async t => {
  await admin(t)
  for (const status of [403, 404, 409, 503]) {
    globalThis.fetch = async () => json({ detail: 'Operación denegada' }, status)
    await assert.rejects(createDemoOrder(1, 'subscribe', 'synthetic-reference'), error => error instanceof ApiResponseError && error.status === status)
    await assert.rejects(confirmDemoOrder(order.id, 'approve'), ApiResponseError)
  }
  await assert.rejects(selectOrganization(2), ApiResponseError)
})
test('Comercial: respuesta de orden manipulada o sin aviso DEMO se rechaza', async t => {
  await admin(t)
  for (const invalid of [{ amountCents: 1 }, { notice: 'Pago real' }, { status: 'paid' }]) {
    globalThis.fetch = async () => json({ ...order, ...invalid })
    await assert.rejects(createDemoOrder(1, 'subscribe', 'synthetic-reference'), ApiDataError)
  }
})
test('Comercial: propietario administra versiones y consulta métricas simuladas mediante endpoints protegidos', async t => {
  isolated(t)
  globalThis.fetch = async url => url.endsWith('/api/auth/login') ? json({ access_token: 'owner-synthetic', token_type: 'bearer', is_superadmin: true })
    : json({ id: 9, username: 'owner', fullName: 'Owner', isSuperadmin: true })
  await loginAgroscan('owner', 'synthetic-only')
  const overview = { activeDemoSubscriptions: 0, expiringSoon: 0, activePlans: 1, simulatedTotalCents: 0, subscriptions: [], orders: [], transactions: [], notice: DEMO_NOTICE }
  globalThis.fetch = async (url, options) => {
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer owner-synthetic')
    assert.match(url, /^\/api\/platform\/commercial\//)
    if (url.endsWith('/overview')) return json(overview)
    return json(options?.method === 'POST' || options?.method === 'PATCH' ? plan : [plan])
  }
  assert.deepEqual(await listCommercialPlans(), [plan])
  assert.equal((await saveCommercialPlan(plan)).id, 1)
  assert.equal((await setCommercialPlanStatus(1, false)).id, 1)
  assert.deepEqual(await getCommercialOverview(), overview)
})
test('Comercial: checkout accesible, sin datos financieros, responsive y con confirmación sensible', () => {
  const ui = readFileSync(new URL('../src/features/commercial/Commercial.tsx', import.meta.url), 'utf8')
  const css = readFileSync(new URL('../src/features/commercial/Commercial.css', import.meta.url), 'utf8')
  const routes = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  assert.match(ui, /htmlFor="demo-scenario"/)
  assert.match(ui, /role="alert"/)
  assert.match(ui, /role="status"/)
  assert.match(ui, /scope="col"/)
  assert.match(ui, /aria-label="Confirmar cancelación"/)
  assert.match(ui, /disabled=\{busy/)
  assert.match(ui, /Continuar orden/)
  assert.doesNotMatch(ui, /name="(?:card|cvv|creditCard|tarjeta)"/)
  assert.match(css, /@media \(max-width: 700px\)/)
  assert.match(css, /overflow-x: auto/)
  assert.match(routes, /path="planes"/)
  assert.match(routes, /path="suscripcion"/)
})

test('Comercial: componentes React reales muestran estado de carga y avisos sin inventar ventas', async t => {
  await admin(t)
  const { PlansPage, SubscriptionPage, CommercialDashboard } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  const render = Component => renderToStaticMarkup(createElement(MemoryRouter, {}, createElement(Component)))
  assert.match(render(PlansPage), /role="status">Consultando planes disponibles/)
  assert.match(render(SubscriptionPage), /Consultando suscripci/)
  const dashboard = render(CommercialDashboard)
  assert.match(dashboard, /Consultando métricas DEMO/)
  assert.match(dashboard, /No se realizó ningún cobro/)
  assert.doesNotMatch(dashboard, /S\/\s*[1-9]/)
})

test('COM-07: editor React precarga condiciones y guarda borradores sin publicación implícita', async () => {
  const { PlanEditor } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  const html = renderToStaticMarkup(createElement(PlanEditor, { plan: { ...plan, displayOrder: 3 }, busy: false, onCancel() {} }))
  assert.match(html, /value="199.00"/)
  assert.match(html, /value="cosecha"/)
  assert.match(html, /readOnly=""/)
  assert.match(html, /value="3"/)
  assert.match(html, /Trazabilidad/)
  assert.match(html, /evaluaciones/)
  assert.match(html, /Guardar borrador/)
  assert.match(html, /Cancelar/)
  assert.doesNotMatch(html, /Publicar versión DEMO/)
  const blank = renderToStaticMarkup(createElement(PlanEditor, { plan: null, busy: true, onCancel() {} }))
  assert.match(blank, /Nuevo plan DEMO/)
  assert.match(blank, /fieldset disabled=""/)
})

test('COM-07: API del editor conserva idempotencia, control de versión e historial autenticado', async t => {
  isolated(t)
  const draft = { ...plan, version: 2, isActive: false, state: 'draft', displayOrder: 5 }
  const input = { code: plan.code, name: plan.name, description: plan.description, amountCents: 24900,
    currency: 'PEN', period: 'annual', benefits: ['Condiciones nuevas'], limits: {}, recommended: true,
    publish: false, expectedVersion: 1, idempotencyKey: 'isolated-editor-key-0001' }
  globalThis.fetch = async (url, options) => {
    if (options?.method === 'POST') { assert.equal(url, '/api/platform/commercial/plans'); assert.deepEqual(JSON.parse(options.body), input); return json(draft) }
    assert.equal(url, '/api/platform/commercial/plans/1/versions')
    return json([draft, plan])
  }
  assert.equal((await saveCommercialPlan(input)).state, 'draft')
  assert.deepEqual((await getCommercialPlanVersions(1)).map(row => row.version), [2, 1])
  for (const change of [{ displayOrder: -1 }, { state: 'invented' }, { createdAt: 'not-a-date' }]) {
    assert.throws(() => parsePlan({ ...draft, ...change }), ApiDataError)
  }
})
