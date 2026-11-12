import assert from 'node:assert/strict'
import test from 'node:test'
import { acquisitionOutcome, GUIDED_STEP_LABELS, hasConfirmedImages, MIN_CONFIRMED_IMAGES } from '../src/features/evaluation/evaluationFlow.ts'

test('AGROP-33: los cinco pasos del operador siguen el orden acordado', () => {
  assert.deepEqual(GUIDED_STEP_LABELS, [
    'Detectar y registrar pieza', 'Colocar y pesar', 'Capturar imágenes',
    'Confirmar adquisición', 'Retirar pieza',
  ])
})

test('AG-043: exige dos fotografías persistidas de la misma evaluación', () => {
  assert.equal(MIN_CONFIRMED_IMAGES, 2)
  assert.equal(hasConfirmedImages(0), false)
  assert.equal(hasConfirmedImages(-1), false)
  assert.equal(hasConfirmedImages(1.5), false)
  assert.equal(hasConfirmedImages(1), false)
  assert.equal(hasConfirmedImages(2), true)
  assert.equal(hasConfirmedImages(3), true)
})

test('AGROP-33: fotografías sin peso son adquisición parcial, nunca confirmación plena', () => {
  assert.equal(acquisitionOutcome({ imageCount: 1, initialWeightConfirmed: false, finalWeightConfirmed: false }), 'partial')
  assert.equal(acquisitionOutcome({ imageCount: 2, initialWeightConfirmed: true, finalWeightConfirmed: false }), 'partial')
})

test('AG-043: con una foto y ambos pesos la adquisición sigue incompleta', () => {
  assert.equal(acquisitionOutcome({ imageCount: 1, initialWeightConfirmed: true, finalWeightConfirmed: true }), 'partial')
})

test('AGROP-33: adquisiciones confirmadas exigen dos imágenes y ambas etapas de pesaje', () => {
  assert.equal(acquisitionOutcome({ imageCount: 2, initialWeightConfirmed: true, finalWeightConfirmed: true }), 'confirmed')
  assert.equal(acquisitionOutcome({ imageCount: 0, initialWeightConfirmed: true, finalWeightConfirmed: true }), 'without-images')
})

import { resolveAcquisitionProcessStatus } from '../src/features/evaluation/evaluationFlow.ts'

test('AGROP-50: transición a listo', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: false,
    processing: false,
    confirmed: false,
    capturing: false,
  }), 'ready')
})

test('AGROP-50: transición a capturando', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: false,
    processing: false,
    confirmed: false,
    capturing: true,
  }), 'capturing')
})

test('AGROP-50: transición a procesando', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: false,
    processing: true,
    confirmed: false,
    capturing: false,
  }), 'processing')
})

test('AGROP-50: transición a pendiente de revisión', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: false,
    processing: false,
    confirmed: true,
    capturing: false,
  }), 'pending')
})

test('AGROP-50: transición a error', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: true,
    processing: false,
    confirmed: false,
    capturing: false,
  }), 'error')
})

test('AGROP-50: el error tiene prioridad sobre los demás estados', () => {
  assert.equal(resolveAcquisitionProcessStatus({
    hasError: true,
    processing: true,
    confirmed: true,
    capturing: true,
  }), 'error')
})