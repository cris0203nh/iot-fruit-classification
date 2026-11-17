import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ApiDataError, ApiResponseError, OrganizationSelectionRequiredError, clearOperatorSession,
  getSessionOrganizationId, getSessionOrganizations, getSessionRole, getEvaluationById,
  isAgroscanAuthenticated, isOperatorAuthenticated, loadProtectedEvidence, loginAgroscan, selectOrganization,
} from '../src/services/agroscanApi.ts'

const previousFetch = globalThis.fetch
const companies = [
  { id: 1, name: 'Empresa A', roles: ['operador'] },
  { id: 2, name: 'Empresa B', roles: ['revisor'] },
]
const json = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const profile = (id, organizations = companies) => ({ id: 7, username: 'shared', organizationId: id,
  roles: organizations.find((company) => company.id === id)?.roles ?? [], organizations })
const evaluation = { id: 'E-000001', lotId: 'SHARED', pieceId: 'P-1', product: 'mango',
  registeredAt: '2026-01-01T00:00:00Z', status: 'processing', weightGrams: null, imageCount: 0,
  evidence: [], visualCategory: null, reviewNote: null, failureReason: null }

function backend(organizations = companies) {
  return async (url, options) => {
    if (url.endsWith('/api/auth/login')) return json({ access_token: 'synthetic-token', token_type: 'bearer' })
    const headers = new Headers(options.headers)
    assert.equal(headers.get('Authorization'), 'Bearer synthetic-token')
    if (url.endsWith('/api/auth/organizations')) return json(organizations)
    if (url.endsWith('/api/auth/me')) {
      const id = Number(headers.get('X-Organization-ID')) || (organizations.length === 1 ? organizations[0].id : null)
      if (!id) return json({ detail: 'Selecciona una empresa.' }, 409)
      if (!organizations.some((company) => company.id === id)) return json({ detail: 'Membresía revocada.' }, 403)
      return json(profile(id, organizations))
    }
    throw new Error(`Unexpected endpoint: ${url}`)
  }
}

async function pendingLogin(t) {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  globalThis.fetch = backend()
  await assert.rejects(loginAgroscan('shared', 'synthetic-password'), OrganizationSelectionRequiredError)
}

test('SaaS-04: varias empresas exigen selección, sin activar permisos antes de validarla', async (t) => {
  await pendingLogin(t)
  assert.equal(isAgroscanAuthenticated(), false)
  assert.equal(getSessionRole(), null)
  assert.equal(getSessionOrganizationId(), null)
  assert.deepEqual(getSessionOrganizations(), companies)
  assert.equal(await selectOrganization(1), 'operador')
  assert.equal(getSessionOrganizationId(), 1)
  assert.equal(isOperatorAuthenticated(), true)
  assert.equal(await selectOrganization(2), 'revisor')
  assert.equal(getSessionOrganizationId(), 2)
  assert.equal(isOperatorAuthenticated(), false)
})

test('SaaS-04: una empresa mantiene el login de dos llamadas y el contexto en memoria', async (t) => {
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  clearOperatorSession()
  let calls = 0
  const handler = backend([companies[0]])
  globalThis.fetch = async (...args) => { calls += 1; return handler(...args) }
  assert.equal(await loginAgroscan('single', 'synthetic-password'), 'operador')
  assert.equal(calls, 2)
  assert.equal(getSessionOrganizationId(), 1)
  assert.equal(getSessionOrganizations().length, 1)
  const list = getSessionOrganizations()
  list[0].roles.push('administrador')
  assert.deepEqual(getSessionOrganizations()[0].roles, ['operador'])
  clearOperatorSession()
  assert.equal(getSessionOrganizationId(), null)
  assert.deepEqual(getSessionOrganizations(), [])
})

test('SaaS-04: empresa ajena rechazada localmente y membresía revocada rechazada por backend', async (t) => {
  await pendingLogin(t)
  await selectOrganization(1)
  await assert.rejects(selectOrganization(999), (error) => error instanceof ApiResponseError && error.status === 403)
  assert.equal(getSessionOrganizationId(), 1)
  globalThis.fetch = backend([companies[0]])
  await assert.rejects(selectOrganization(2), (error) => error instanceof ApiResponseError && error.status === 403)
  assert.equal(isAgroscanAuthenticated(), false)
  assert.equal(getSessionOrganizationId(), null)
})

test('SaaS-04: respuestas de consultas anteriores al cambio no se entregan a la nueva empresa', async (t) => {
  await pendingLogin(t)
  await selectOrganization(1)
  let release
  const normal = backend()
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/api/evaluations/E-000001')) {
      assert.equal(new Headers(options.headers).get('X-Organization-ID'), '1')
      return new Promise((resolve) => { release = resolve })
    }
    return normal(url, options)
  }
  const stale = getEvaluationById('E-000001')
  await selectOrganization(2)
  release(json(evaluation))
  await assert.rejects(stale, (error) => error instanceof ApiResponseError && error.status === 409)
  assert.equal(getSessionOrganizationId(), 2)
})

test('SaaS-04: fotos incluyen la empresa y no entregan bytes del contexto anterior', async (t) => {
  await pendingLogin(t)
  await selectOrganization(1)
  let release
  const normal = backend()
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/api/images/I-000001')) {
      assert.equal(new Headers(options.headers).get('X-Organization-ID'), '1')
      return new Promise((resolve) => { release = resolve })
    }
    return normal(url, options)
  }
  const stale = loadProtectedEvidence('/api/images/I-000001')
  await selectOrganization(2)
  release({ ok: true, headers: new Headers({ 'content-type': 'image/jpeg' }),
    blob: async () => new Blob(['company-A-photo'], { type: 'image/jpeg' }) })
  await assert.rejects(stale, (error) => error instanceof ApiResponseError && error.status === 409)
  globalThis.fetch = async (_url, options) => {
    assert.equal(new Headers(options.headers).get('X-Organization-ID'), '2')
    return { ok: true, headers: new Headers({ 'content-type': 'image/jpeg' }),
      blob: async () => new Blob(['company-B-photo'], { type: 'image/jpeg' }) }
  }
  assert.equal(await (await loadProtectedEvidence('/api/images/I-000002')).text(), 'company-B-photo')
})

test('SaaS-04: perfiles inconsistentes no habilitan la empresa seleccionada', async (t) => {
  await pendingLogin(t)
  globalThis.fetch = async () => json(profile(1))
  await assert.rejects(selectOrganization(2), ApiDataError)
  assert.equal(isAgroscanAuthenticated(), false)
  assert.equal(getSessionOrganizationId(), null)
})

test('SaaS-04: durante un cambio no se permiten operaciones ni cambios simultáneos', async (t) => {
  await pendingLogin(t)
  await selectOrganization(1)
  let release
  globalThis.fetch = async () => new Promise((resolve) => { release = resolve })
  const changing = selectOrganization(2)
  assert.equal(isAgroscanAuthenticated(), false)
  await assert.rejects(selectOrganization(1), (error) => error instanceof ApiResponseError && error.status === 409)
  await assert.rejects(getEvaluationById('E-000001'), (error) => error instanceof ApiResponseError && error.status === 409)
  release(json(profile(2)))
  await changing
  assert.equal(getSessionOrganizationId(), 2)
})
