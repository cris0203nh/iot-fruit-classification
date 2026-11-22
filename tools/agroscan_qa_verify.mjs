// Cliente TypeScript real contra el proxy QA. No modifica registros operativos.
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

let input = ''
for await (const chunk of process.stdin) input += chunk
const accounts = JSON.parse(input)
const api = await import(pathToFileURL(resolve('frontend/src/services/agroscanApi.ts')).href)
const commerce = await import(pathToFileURL(resolve('frontend/src/features/commercial/commercialApi.ts')).href)
const actualFetch = globalThis.fetch
const page = await actualFetch('http://127.0.0.1:5188/')
assert.equal(page.status, 200)
const html = await page.text()
assert.match(html, /QA LOCAL/)
assert.match(html, /AgroScan — QA local/)
const unauthorizedBackend = await actualFetch('http://127.0.0.1:8778/api/health', { headers: { 'X-AgroScan-QA': 'other-instance' } })
assert.equal(unauthorizedBackend.status, 503)
globalThis.fetch = async (url, options) => {
  assert.match(String(url), /^\/api\//, 'QA solo usa API relativa')
  const response = await actualFetch('http://127.0.0.1:5188' + url, options)
  assert.equal(response.headers.get('X-AgroScan-QA-ID'), process.env.AGROSCAN_QA_INSTANCE)
  return response
}
const catalog = await commerce.getCatalog()
assert.equal(catalog.simulatorEnabled, true)
assert.ok(catalog.plans.length > 0)
assert.ok(catalog.plans.every(plan => plan.isActive))
assert.equal((await api.request('/api/auth/google/config')).enabled, false)
const results = {}
for (const role of ['propietario', 'administrador', 'operador', 'revisor']) {
  api.clearOperatorSession()
  const account = accounts[role]
  const effective = await api.loginAgroscan(account.username, account.password)
  assert.equal(effective, role === 'propietario' ? 'superadmin' : role)
  assert.equal(api.isPlatformOwner(), role === 'propietario')
  if (role === 'propietario') {
    const overview = await commerce.getCommercialOverview()
    assert.equal(overview.activeDemoSubscriptions, overview.subscriptions.filter(sub => sub.status === 'active').length)
    assert.equal(overview.simulatedTotalCents, overview.transactions.filter(tx => tx.outcome === 'demo_approved').reduce((sum, tx) => sum + tx.amountCents, 0))
    assert.equal(api.getSessionRole(), null)
    await assert.rejects(commerce.getCompanyCommerce(), api.ApiResponseError)
  } else {
    assert.equal(api.getSessionOrganizationId(), 1)
    const lots = await api.request('/api/lots')
    const evaluations = await api.request('/api/evaluations')
    assert.ok(Array.isArray(lots))
    assert.ok(Array.isArray(evaluations))
    await assert.rejects(api.request('/api/platform/organizations'), error => error.status === 403)
    await assert.rejects(api.request('/api/lots', { headers: { 'X-Organization-ID': '2' } }, 8000, 2), error => error.status === 403)
    if (role === 'administrador') {
      const company = await commerce.getCompanyCommerce()
      assert.ok(company.orders.every(order => order.organizationId === api.getSessionOrganizationId()))
      assert.ok(company.transactions.every(tx => tx.organizationId === api.getSessionOrganizationId()))
      if (company.subscription) assert.equal(company.subscription.organizationId, api.getSessionOrganizationId())
      assert.ok((await api.request('/api/users')).some(user => user.username === account.username))
    } else {
      await assert.rejects(commerce.getCompanyCommerce(), error => error.status === 403)
      await assert.rejects(api.request('/api/users'), error => error.status === 403)
    }
    if (role === 'operador') await assert.rejects(api.request('/api/reviews/queue'), error => error.status === 403)
    if (role === 'revisor') {
      assert.ok(await api.request('/api/reviews/queue'))
    }
  }
  results[role] = 'APROBADO'
}
api.clearOperatorSession()
console.log(JSON.stringify({ roles: results, actualFrontendHttpClient: true, qaProxy: true,
  unauthorizedCompanyB: 'DENEGADA', productionDatabaseAccessed: false, qaRecordsCreated: 0 }, null, 2))
