import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { projectedBoundingSize } from '../src/features/geometry/geometryView.ts'

test('AG-054: ancho y alto de caja son pixeles proyectados, sin conversion fisica', () => {
  assert.deepEqual(projectedBoundingSize([12, 14, 112, 84]), { widthPx: 100, heightPx: 70 })
  assert.equal(projectedBoundingSize([4, 5, 3, 8]), null)
  assert.equal(projectedBoundingSize([1, 1, NaN, 10]), null)
  assert.equal(projectedBoundingSize([1, 2]), null)
})

test('AG-054: API mantiene la version, inmutabilidad del original y sin E0 E1 E2', () => {
  const api = readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
  assert.match(api, /vision\/geometry/)
  assert.match(api, /classificationE0E1E2Produced: false/)
  assert.match(api, /calibrated: false/)
})
