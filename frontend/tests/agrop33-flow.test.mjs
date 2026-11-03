import assert from 'node:assert/strict'
import test from 'node:test'
import { acquisitionOutcome, GUIDED_STEP_LABELS, hasConfirmedImages } from '../src/features/evaluation/evaluationFlow.ts'

test('AGROP-33: los cinco pasos del operador siguen el orden acordado', () => {
  assert.deepEqual(GUIDED_STEP_LABELS, [
    'Identificar pieza', 'Colocar y pesar', 'Capturar imágenes',
    'Confirmar adquisición', 'Retirar pieza',
  ])
})

test('AGROP-33: sin fotografía confirmada no se avanza a la confirmación', () => {
  assert.equal(hasConfirmedImages(0), false)
  assert.equal(hasConfirmedImages(-1), false)
  assert.equal(hasConfirmedImages(1.5), false)
  assert.equal(hasConfirmedImages(1), true)
})

test('AGROP-33: fotografías sin peso son adquisición parcial, nunca confirmación plena', () => {
  assert.equal(acquisitionOutcome({ imageCount: 1, initialWeightConfirmed: false, finalWeightConfirmed: false }), 'partial')
  assert.equal(acquisitionOutcome({ imageCount: 2, initialWeightConfirmed: true, finalWeightConfirmed: false }), 'partial')
})

test('AGROP-33: adquisiciones confirmadas exigen imágenes y ambas etapas de pesaje', () => {
  assert.equal(acquisitionOutcome({ imageCount: 2, initialWeightConfirmed: true, finalWeightConfirmed: true }), 'confirmed')
  assert.equal(acquisitionOutcome({ imageCount: 0, initialWeightConfirmed: true, finalWeightConfirmed: true }), 'without-images')
})
