import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { tsxUrl } from './support/load-tsx.mjs'
import { projectedBoundingSize } from '../src/features/geometry/geometryView.ts'

const { PixelGeometryCells } = await import(tsxUrl(new URL('../src/features/history/EvaluationEvidenceSnapshot.tsx', import.meta.url)))

test('AG-054: ancho y alto de caja son pixeles proyectados, sin conversion fisica', () => {
  assert.deepEqual(projectedBoundingSize([12, 14, 112, 84]), { widthPx: 100, heightPx: 70 })
  assert.equal(projectedBoundingSize([4, 5, 3, 8]), null)
  assert.equal(projectedBoundingSize([1, 1, NaN, 10]), null)
  assert.equal(projectedBoundingSize([1, 2]), null)
})

test('AG-054: resultado React muestra los ejes persistidos de I-000006 e I-000007 en px', () => {
  // Valores leídos de AG-054 en DEV; no constituyen calibración ni exactitud experimental.
  for (const [majorAxisPx, minorAxisPx, areaPx2, perimeterPx] of [
    [312, 292, 72202, 1012.35], [481.34, 347.66, 132333.75, 1397.42],
  ]) {
    const html = renderToStaticMarkup(createElement(PixelGeometryCells, {
      result: { status: 'measured', measurements: { majorAxisPx, minorAxisPx, areaPx2, perimeterPx } },
    }))
    assert.ok(html.includes(`${majorAxisPx.toFixed(1)} px`))
    assert.ok(html.includes(`${minorAxisPx.toFixed(1)} px`))
    assert.ok(html.includes(areaPx2.toFixed(0)))
    assert.doesNotMatch(html, /cm|mm|Sin estimaci/)
  }
})

test('AG-054: segmentación inválida conserva motivo real y no inventa ejes', () => {
  const html = renderToStaticMarkup(createElement(PixelGeometryCells, {
    result: { status: 'needs_review', reason: 'multiples_candidatos', measurements: null },
  }))
  assert.match(html, /No evaluable: multiples_candidatos/)
  assert.doesNotMatch(html, /\d+\.\d+ px|cm|mm/)
})

test('AG-054: consulta fallida no presenta medidas antiguas como verificadas', () => {
  const html = renderToStaticMarkup(createElement(PixelGeometryCells, {
    unavailable: true, result: { status: 'measured', measurements: { majorAxisPx: 312 } },
  }))
  assert.match(html, /Consulta no disponible/)
  assert.doesNotMatch(html, /312/)
})

test('AG-054: API mantiene la version, inmutabilidad del original y sin E0 E1 E2', () => {
  const api = readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
  assert.match(api, /vision\/geometry/)
  assert.match(api, /classificationE0E1E2Produced: false/)
  assert.match(api, /calibrated: false/)
})
