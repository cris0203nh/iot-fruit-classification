import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { menuTabTarget } from '../src/components/layout/menuFocus.ts'

const read = (path) => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')

// Pruebas puras del cierre de foco: funcionan sin navegador ni backend.
test('I04: Shift+Tab desde el primer enlace vuelve al último', () => {
  const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
  assert.equal(menuTabTarget(items, items[0], true), items[2])
})
test('I04: Tab desde el último enlace vuelve al primero', () => {
  const items = ['inicio', 'historial', 'trazabilidad']
  assert.equal(menuTabTarget(items, items[2], false), items[0])
})
test('I04: Tab no interrumpe el avance dentro del menú y recupera foco externo', () => {
  const items = ['inicio', 'historial', 'lotes']
  assert.equal(menuTabTarget(items, items[1], false), null)
  assert.equal(menuTabTarget(items, items[1], true), null)
  assert.equal(menuTabTarget(items, null, false), items[0])
  assert.equal(menuTabTarget(items, 'fuera', true), items[2])
  assert.equal(menuTabTarget([], null, false), null)
})
test('I04: el menú tiene Escape, diálogo modal, foco inicial y restauración', () => {
  const src = read('components/layout/AppLayout.tsx')
  assert.match(src, /aria-modal=\{menuOpen \|\| undefined\}/)
  assert.match(src, /role=\{menuOpen \? 'dialog' : undefined\}/)
  assert.match(src, /if \(event\.key === 'Escape'\)/)
  assert.match(src, /mobileMenuButtonRef\.current\?\.focus\(\)/)
  assert.match(src, /sidebar\?\.querySelector<HTMLElement>\('\.nav-link'\)\?\.focus\(\)/)
  assert.match(src, /inert=\{menuOpen\}/)
  assert.match(src, /previousPathname\.current === pathname/)
})
test('I04: los formularios no ocultan el indicador de foco de teclado', () => {
  for (const [path, selector] of [
    ['pages/EvaluationPage.css', '.evaluation-field__control:focus-within'],
    ['pages/LotsPage.css', '.lotes__control:focus-within'],
    ['pages/HistoryPage.css', '.history-field__control:focus-within'],
    ['pages/TraceabilityPage.css', '.trace-field__control:focus-within'],
    ['features/traceability/ReviewDecisionPanel.css', '.ag038-review__form select:focus-visible'],
    ['features/auth/AuthGate.css', '.agroscan-login__line:focus-within'],
  ]) {
    const css = read(path)
    const pos = css.lastIndexOf(selector)
    assert.ok(pos >= 0, `${path} sin selector ${selector}`)
    assert.match(css.slice(pos, pos + 180), /outline:\s*(2|3)px solid/)
  }
})
test('I04: zoom, pantallas estrechas y movimiento reducido tienen reglas explícitas', () => {
  const layout = read('components/layout/AppLayout.css')
  assert.match(layout, /max-height:\s*100dvh/)
  assert.match(layout, /overflow-y:\s*auto/)
  const shared = read('index.css')
  assert.match(shared, /@media \(prefers-reduced-motion: reduce\)/)
  assert.match(shared, /animation-duration:\s*0\.01ms !important/)
  assert.match(read('features/iot/WeightCaptureCard.css'), /weight-capture__hint \{ font-size: var\(--fs-sm\)/)
  assert.match(read('features/history/PieceHistoryPanel.css'), /@media \(max-width: 440px\)/)
})
