import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const css = (relative) => readFileSync(new URL(`../${relative}`, import.meta.url), 'utf8')
const root = css('src/index.css')
const layout = css('src/components/layout/AppLayout.css')

function fontToken(name) {
  const match = root.match(new RegExp(`--fs-${name}:\\s*([\\d.]+)rem;`))
  assert.ok(match, `Falta el token --fs-${name}`)
  return Number(match[1]) * 16
}

function linear(value) {
  const n = value / 255
  return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4
}

function luminance([r, g, b]) {
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
}

function ratio(a, b) {
  const [max, min] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (max + 0.05) / (min + 0.05)
}

function blend(fg, bg, opacity) {
  return fg.map((c, i) => c * opacity + bg[i] * (1 - opacity))
}

test('escala de texto compartida preserva mínimos operativos', () => {
  assert.ok(fontToken('micro') >= 12)
  assert.ok(fontToken('label') >= 13)
  assert.ok(fontToken('sm') >= 14)
  assert.ok(fontToken('body') >= 15)
  assert.ok(fontToken('md') >= 16)
})

test('navegación secundaria mantiene contraste suficiente sobre la barra lateral', () => {
  // Valores vigentes de .sidebar, .nav-link y .sidebar-disclaimer.
  const sidebar = [23, 32, 27]
  const paper = [239, 232, 218]
  for (const opacity of [0.78, 0.86]) {
    assert.ok(ratio(blend(paper, sidebar, opacity), sidebar) >= 4.5)
  }
  assert.match(layout, /\.sidebar-disclaimer\s*\{[^}]*rgba\(239, 232, 218, 0\.78\)/s)
  assert.match(layout, /\.nav-link\s*\{[^}]*rgba\(239, 232, 218, 0\.86\)/s)
})

test('la navegación móvil contempla foco y tamaños táctiles', () => {
  assert.match(root, /--tap:\s*46px/)
  assert.match(layout, /\.mobile-menu-button\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px/s)
  assert.match(layout, /\.sidebar:not\(\.sidebar--open\)\s*\{[^}]*visibility:\s*hidden/s)
  assert.match(layout, /\.sidebar\s+\.nav-link--active:focus-visible/)
})


test('AG043/AG056: los tres roles presentan 5, 4 y 5 enlaces sin privilegios adicionales', () => {
  const src = css('src/app/navigation.ts')
  const links = (name) => {
    const signature = `export const ${name}: NavigationItem[] = [`
    assert.equal(src.split(signature).length, 2, `No se encontró ${name} de forma única`)
    const body = src.split(signature)[1].split(']')[0]
    return [...body.matchAll(/\{ path: '([^']+)'/g)].map((item) => item[1])
  }
  assert.deepEqual(links('operatorNavigation'), ['/', '/evaluacion', '/lotes', '/historial', '/trazabilidad'])
  assert.deepEqual(links('reviewerNavigation'), ['/', '/revisiones', '/historial', '/trazabilidad'])
  assert.deepEqual(links('administratorNavigation'), ['/', '/revisiones', '/usuarios', '/trazabilidad', '/estadisticas'])
})

test('AG043: la sesión distingue explícitamente al administrador', () => {
  const src = css('src/features/auth/AuthGate.tsx')
  assert.match(src, /getSessionRole\(\) === 'administrador' \? 'administrador' : 'operador'/)
  assert.match(src, /if \(role === 'revisor'\) navigate\('\/historial'/)
})

test('AG043: inicio del revisor es de consulta y no ofrece altas operativas', () => {
  const src = css('src/pages/HomePage.tsx')
  assert.match(src, /const reviewer = getSessionRole\(\) === 'revisor'/)
  assert.match(src, /reviewer \? 'Inicio: revisión y consulta'/)
  assert.match(src, /\{!reviewer && \(\s*<>\s*<Link className="inicio__accion inicio__accion--primaria" to="\/evaluacion"/s)
  assert.match(src, /to="\/lotes"/)
  assert.match(src, /to="\/historial"/)
  assert.match(src, /to="\/trazabilidad"/)
})

test('AG043: el administrador no anuncia hardware sin verificación física', () => {
  const src = css('src/pages/AdminDashboard.tsx')
  for (const title of ['Cámara web RGB', 'Balanza digital ESP32']) {
    const signature = `title="${title}"`
    assert.equal(src.split(signature).length, 2, `Falta el indicador único de ${title}`)
    const block = src.split(signature)[1].split('/>')[0]
    assert.match(block, /status="Sin verificar"/)
    assert.match(block, /online=\{false\}/)
  }
  assert.doesNotMatch(src, /status="Validada"/)
  assert.match(src, /La disponibilidad de FastAPI no confirma/)
})
