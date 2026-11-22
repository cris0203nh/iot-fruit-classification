import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { tsxUrl } from './support/load-tsx.mjs'
import { clearOperatorSession, loginAgroscan, selectOrganization } from '../src/services/agroscanApi.ts'

const render = (Component, path, props = {}) => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [path] }, createElement(Component, props)))
const json = body => ({ ok: true, status: 200, json: async () => body })

for (const [path, heading] of [['empresas', 'Empresas'], ['administradores', 'Administradores'], ['planes', 'Planes y contrataciones DEMO']]) {
  test(`Propietario: ruta ${path} reutiliza layout y muestra únicamente su sección`, async () => {
    const { OwnerWorkspace } = await import(tsxUrl(new URL('../src/pages/OwnerWorkspace.tsx', import.meta.url)))
    const html = render(OwnerWorkspace, '/plataforma/' + path, { onLogout() {} })
    assert.match(html, /app-shell--owner/)
    assert.match(html, new RegExp(`<h1[^>]*>${heading}</h1>`))
    assert.equal((html.match(/<h1\b/g) ?? []).length, 1)
    assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1)
    assert.match(html, new RegExp(`href="/plataforma/${path}"[^>]*aria-current="page"|aria-current="page"[^>]*href="/plataforma/${path}"`))
    for (const section of ['empresas', 'administradores', 'planes']) assert.match(html, new RegExp(`href="/plataforma/${section}"`))
    assert.match(html, /Cerrar sesión/)
    assert.match(html, /Propietario global/)
    assert.doesNotMatch(html, /Nueva evaluación|href="\/usuarios"|href="#company/)
    if (path !== 'planes') assert.doesNotMatch(html, /id="commercial-heading"/)
    else assert.doesNotMatch(html, /id="platform-company-name"|id="platform-admin-password"/)
  })
}

test('Propietario: AuthGate sigue diferenciando al propietario de los tres roles empresariales', async t => {
  const previousFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  const { AuthGate } = await import(tsxUrl(new URL('../src/features/auth/AuthGate.tsx', import.meta.url)))
  for (const role of ['propietario', 'administrador', 'operador', 'revisor']) {
    clearOperatorSession()
    globalThis.fetch = async url => url.endsWith('/api/auth/login')
      ? json({ access_token: 'synthetic', token_type: 'bearer', is_superadmin: role === 'propietario' })
      : role === 'propietario' ? json({ id: 9, username: 'owner', fullName: 'Owner', isSuperadmin: true })
        : json({ id: 2, username: role, roles: [role], organizationId: 1, organizations: [{ id: 1, name: 'A', roles: [role] }] })
    await loginAgroscan(role, 'synthetic-password')
    const html = render(AuthGate, '/plataforma/empresas', { children: createElement('p', {}, 'Operación empresarial') })
    if (role === 'propietario') {
      assert.match(html, /app-shell--owner/)
      assert.doesNotMatch(html, /Operación empresarial/)
    } else {
      assert.doesNotMatch(html, /app-shell--owner/)
      assert.match(html, /Operación empresarial/)
    }
  }
})

test('Propietario: vistas comerciales seleccionables por URL, sin mezclar paneles', async () => {
  const { CommercialDashboard } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  for (const [query, label] of [['', 'Catálogo'], ['?vista=suscripciones', 'Suscripciones'], ['?vista=operaciones', 'Operaciones DEMO']]) {
    const html = render(CommercialDashboard, '/plataforma/planes' + query)
    assert.match(html, new RegExp(`aria-pressed="true"[^>]*>${label}</button>`))
    assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1)
    assert.match(html, /No se realizó ningún cobro/)
    assert.match(html, /role="status"/)
  }
})

test('Propietario: tablas comerciales conservan importes, estados y condiciones históricas', async () => {
  const { OwnerSubscriptions, OwnerTransactions } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  const plan = { name: 'Plan sintético DEMO', version: 4, amountCents: 12900, period: 'monthly' }
  const sub = { organizationId: 2, plan, status: 'expired', startsAt: '2026-01-01T00:00:00Z', endsAt: '2026-02-01T00:00:00Z' }
  const subscriptions = render(OwnerSubscriptions, '/', { subscriptions: [sub] })
  assert.match(subscriptions, /Empresa #2/)
  assert.match(subscriptions, /Versión 4/)
  assert.match(subscriptions, /Vencida/)
  assert.match(subscriptions, /scope="col"/)
  const tx = render(OwnerTransactions, '/', { transactions: [{ id: 1, organizationId: 2, orderId: 'synthetic-order', outcome: 'demo_rejected', amountCents: 0, createdAt: '2026-01-01T00:00:00Z' }] })
  assert.match(tx, /Simulación rechazada/)
  assert.match(tx, /No se realizó ningún cobro/)
  assert.match(tx, /synthetic-order/)
})

test('Propietario: estados vacíos comerciales explican el siguiente paso sin inventar actividad', async () => {
  const { OwnerSubscriptions, OwnerTransactions } = await import(tsxUrl(new URL('../src/features/commercial/Commercial.tsx', import.meta.url)))
  assert.match(render(OwnerSubscriptions, '/', { subscriptions: [] }), /cuando un administrador empresarial/)
  assert.match(render(OwnerTransactions, '/', { transactions: [] }), /sin ingresos reales/)
})

test('Propietario: foco, Escape, menú móvil y tablas desbordables siguen disponibles', () => {
  const source = relative => readFileSync(new URL('../src/' + relative, import.meta.url), 'utf8')
  const layout = source('components/layout/AppLayout.tsx')
  const platform = source('pages/PlatformDashboard.tsx')
  assert.match(layout, /menuTabTarget/)
  assert.match(layout, /mainRef.current\?\.focus/)
  assert.match(layout, /inert=\{menuOpen\}/)
  assert.match(platform, /editorOpener.current\?\.focus/)
  assert.match(platform, /event.key === 'Escape'/)
  assert.match(platform, /tabIndex=\{0\}/)
  assert.match(source('pages/PlatformDashboard.css'), /@media \(max-width: 700px\)/)
})

test('Refinamiento: KPIs usan iconos accesibles y mantienen cifras reales, incluso cero', async () => {
  const { PlatformSummary } = await import(tsxUrl(new URL('../src/pages/PlatformDashboard.tsx', import.meta.url)))
  const html = render(PlatformSummary, '/', { metrics: { organizations: 2, activeOrganizations: 1, users: 4, activeUsers: 4, evaluations: 0 } })
  assert.equal((html.match(/class="executive-metric executive-metric--/g) ?? []).length, 3)
  assert.equal((html.match(/<svg/g) ?? []).length, 3)
  assert.equal((html.match(/aria-hidden="true"/g) ?? []).length, 3)
  assert.match(html, /<strong>0<\/strong>/)
  assert.match(html, /Empresas · 1 activas/)
})

test('Refinamiento: la cuenta y sus acciones pertenecen al sidebar, sin duplicarlas en la barra superior', async () => {
  const { AppLayout } = await import(tsxUrl(new URL('../src/components/layout/AppLayout.tsx', import.meta.url)))
  const html = render(AppLayout, '/', { owner: true, account: createElement('span', {}, 'Owner sintético'), actions: createElement('button', {}, 'Cerrar sesión') })
  const sidebar = html.split('</aside>')[0]
  assert.match(sidebar, /Owner sintético/)
  assert.match(sidebar, /Cerrar sesión/)
  assert.match(html, /layout-mobile-controls/)
  assert.equal((html.match(/Owner sintético/g) ?? []).length, 1)
})

test('Refinamiento: asignación guiada mantiene ambas operaciones y su confirmación explícita', () => {
  const source = readFileSync(new URL('../src/pages/PlatformDashboard.tsx', import.meta.url), 'utf8')
  assert.match(source, /Elige la empresa/)
  assert.match(source, /Elige cómo asignar a la persona/)
  assert.match(source, /Confirma la asignación/)
  assert.equal((source.match(/name="admin-account-path"/g) ?? []).length, 2)
  assert.match(source, /createPlatformAdministrator\(Number\(company\)/)
  assert.match(source, /designatePlatformAdministrator\(Number\(company\), Number\(user\)\)/)
  assert.match(source, /Crear cuenta y asignar administrador/)
})

test('Refinamiento: Google conserva la autorización explícita y usa diálogo con cancelación y foco restaurado', async () => {
  const { GoogleLinkAccount } = await import(tsxUrl(new URL('../src/features/auth/GoogleAccess.tsx', import.meta.url)))
  const html = render(GoogleLinkAccount, '/')
  assert.match(html, /aria-haspopup="dialog"/)
  assert.match(html, /<dialog[^>]*aria-labelledby="google-link-title"/)
  assert.doesNotMatch(html, /<details/)
  const source = readFileSync(new URL('../src/features/auth/GoogleAccess.tsx', import.meta.url), 'utf8')
  assert.match(source, /showModal\(\)/)
  assert.match(source, /trigger.current\?\.focus\(\)/)
  assert.match(source, /linkGoogle\(credential, password\)/)
  assert.match(source, /Confirmar y elegir cuenta Google/)
  assert.match(source, /onCancel=/)
})

async function businessSession(t, role, multiple = false) {
  const previousFetch = globalThis.fetch
  clearOperatorSession()
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  const organizations = [{ id: 1, name: 'Empresa A sintética', roles: [role] },
    ...(multiple ? [{ id: 2, name: 'Empresa B autorizada', roles: [role] }] : [])]
  globalThis.fetch = async url => url.endsWith('/api/auth/login')
    ? json({ access_token: 'synthetic-business-session', token_type: 'bearer', organization_id: 1 })
    : json({ id: 4, username: 'synthetic-admin', fullName: 'Persona de ensayo', roles: [role], organizationId: 1, organizations })
  assert.equal(await loginAgroscan('synthetic-admin', 'synthetic-password'), role)
}

test('Administrador: cuenta en sidebar, modal Google único y seis enlaces intactos', async t => {
  await businessSession(t, 'administrador')
  const { AuthGate } = await import(tsxUrl(new URL('../src/features/auth/AuthGate.tsx', import.meta.url)))
  const { AppLayout } = await import(tsxUrl(new URL('../src/components/layout/AppLayout.tsx', import.meta.url)))
  const html = render(AuthGate, '/', { children: createElement(AppLayout) })
  assert.match(html, /app-shell--administrator/)
  assert.doesNotMatch(html, /class="agroscan-session"/)
  const sidebar = html.split('</aside>')[0]
  assert.match(sidebar, /Administrador empresarial/)
  assert.match(sidebar, /Cerrar sesión/)
  assert.match(sidebar, /Vincular Google a mi cuenta/)
  assert.equal((html.match(/aria-haspopup="dialog"/g) ?? []).length, 1)
  const navigation = html.split('<nav')[1].split('</nav>')[0]
  for (const path of ['/app', '/revisiones', '/usuarios', '/trazabilidad', '/estadisticas', '/suscripcion']) {
    assert.ok(navigation.includes(`href="${path}"`))
  }
  assert.equal((navigation.match(/<a /g) ?? []).length, 6)
})

test('Operador y revisor: reutilizan cuenta y acciones del sidebar, sin barras superiores', async t => {
  const previousFetch = globalThis.fetch
  const { AuthGate } = await import(tsxUrl(new URL('../src/features/auth/AuthGate.tsx', import.meta.url)))
  const { AppLayout } = await import(tsxUrl(new URL('../src/components/layout/AppLayout.tsx', import.meta.url)))
  for (const role of ['operador', 'revisor']) {
    await businessSession(t, role)
    const html = render(AuthGate, '/', { children: createElement(AppLayout) })
    assert.doesNotMatch(html, /class="agroscan-session"|class="topbar"|app-shell--administrator/)
    const sidebar = html.split('</aside>')[0]
    assert.match(sidebar, /owner-sidebar-account/)
    assert.match(sidebar, /Sesión activa/)
    assert.match(sidebar, role === 'operador' ? /Operador/ : /Revisor \(consulta\)/)
    assert.match(sidebar, /Empresa A sintética/)
    assert.equal((html.match(/Cerrar sesión/g) ?? []).length, 1)
    assert.equal((html.match(/Vincular Google a mi cuenta/g) ?? []).length, 1)
    assert.equal((sidebar.match(/class="nav-link/g) ?? []).length, role === 'operador' ? 5 : 4)
    assert.doesNotMatch(sidebar, /href="\/usuarios"|href="\/suscripcion"|href="\/plataforma/)
  }
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
})

test('Todos los roles empresariales: selector autorizado aparece una sola vez en el sidebar', async t => {
  const { AuthGate } = await import(tsxUrl(new URL('../src/features/auth/AuthGate.tsx', import.meta.url)))
  const { AppLayout } = await import(tsxUrl(new URL('../src/components/layout/AppLayout.tsx', import.meta.url)))
  for (const role of ['administrador', 'operador', 'revisor']) {
    await businessSession(t, role, true)
    const html = render(AuthGate, '/app', { children: createElement(AppLayout) })
    assert.equal((html.match(/id="agroscan-company-active"/g) ?? []).length, 1)
    const sidebar = html.split('</aside>')[0]
    assert.match(sidebar, /Empresa A sintética/)
    assert.match(sidebar, /Empresa B autorizada/)
    assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1)
  }
  const source = readFileSync(new URL('../src/components/layout/AppLayout.tsx', import.meta.url), 'utf8')
  assert.match(source, /select:not\(\[disabled\]\)/)
  assert.match(source, /dialog\.google-link-dialog\[open\]/)
})

test('Cuenta compartida: identidad y rol legibles, barra de escritorio oculta y menú móvil conservado', async () => {
  const { SidebarAccount } = await import(tsxUrl(new URL('../src/components/layout/SidebarAccount.tsx', import.meta.url)))
  const html = render(SidebarAccount, '/', { role: 'Administrador empresarial', identity: createElement('strong', {}, 'Nombre de ensayo'), actions: createElement('button', {}, 'Cerrar sesión') })
  assert.match(html, /Nombre de ensayo/)
  assert.match(html, /Administrador empresarial/)
  const css = readFileSync(new URL('../src/components/layout/AppLayout.css', import.meta.url), 'utf8')
  assert.match(css, /\.layout-mobile-controls\s*\{ display: none; \}/)
  assert.match(css, /@media \(max-width: 1000px\)[\s\S]*\.layout-mobile-controls\s*\{ display: flex;/)
  assert.match(css, /\.sidebar-nav\s*\{[^}]*overflow-y: auto/)
  assert.match(css, /\.sidebar-bottom\s*\{[^}]*flex-shrink: 0/)
})

test('Cambio de empresa: el sidebar refleja el rol validado y retira enlaces administrativos', async t => {
  const previousFetch = globalThis.fetch
  clearOperatorSession()
  t.after(() => { globalThis.fetch = previousFetch; clearOperatorSession() })
  const organizations = [{ id: 1, name: 'Empresa A', roles: ['administrador'] }, { id: 2, name: 'Empresa B', roles: ['revisor'] }]
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/api/auth/login')) return json({ access_token: 'test-only', token_type: 'bearer', organization_id: 1 })
    const id = Number(new Headers(options.headers).get('X-Organization-ID'))
    return json({ id: 4, username: 'shared-test', roles: organizations.find(row => row.id === id).roles, organizationId: id, organizations })
  }
  const { AuthGate } = await import(tsxUrl(new URL('../src/features/auth/AuthGate.tsx', import.meta.url)))
  const { AppLayout } = await import(tsxUrl(new URL('../src/components/layout/AppLayout.tsx', import.meta.url)))
  await loginAgroscan('shared-test', 'test-only-password')
  assert.match(render(AuthGate, '/usuarios', { children: createElement(AppLayout) }), /href="\/usuarios"/)
  await selectOrganization(2)
  const html = render(AuthGate, '/historial', { children: createElement(AppLayout) })
  assert.match(html, /Revisor \(consulta\)/)
  assert.match(html, /value="2" selected=""/)
  assert.doesNotMatch(html, /href="\/usuarios"|href="\/suscripcion"|href="\/evaluacion"/)
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1)
})
