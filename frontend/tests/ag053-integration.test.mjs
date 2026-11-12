import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const read = (name) => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8')

test('AG053: iniciar con YOLOE antes del alta de evaluación', () => {
  const page = read('src/pages/EvaluationPage.tsx')
  assert.match(page, /<AutoRegistrationPanel[\s\S]*?onRegistered=/)
  assert.match(page, /setGuideStep\(2\)/)
  assert.match(page, /Registro manual \/ excepción|Volver a identificación automática/)
})

test('AG053: solo registra con token respaldado por detección', () => {
  const api = read('src/services/agroscanApi.ts')
  assert.match(api, /\/api\/vision\/precheck/)
  assert.match(api, /\/api\/evaluations\/auto/)
  assert.match(api, /detectionToken/)
  assert.match(api, /classificationE0E1E2Produced: false/)
})

test('AG053: conserva recepción de dos imágenes y cinco pasos durante incremento 01', () => {
  const src = read('src/features/evaluation/evaluationFlow.ts')
  assert.match(src, /Detectar y registrar pieza/)
  assert.match(src, /Capturar imágenes/)
  assert.match(src, /Confirmar adquisición/)
})
