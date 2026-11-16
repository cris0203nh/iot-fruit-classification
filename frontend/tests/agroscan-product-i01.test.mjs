import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { summarizeEvaluation } from '../src/features/history/evaluationOutcomePolicy.ts'

const input = (extra = {}) => ({ status: 'pending_review', ledger: { currentValue: null, decisions: [] },
  qualityStatus: { modelAvailable: false }, proposals: [], ...extra })

test('I01: registro cerrado no implica clasificación automática ni dimensiones acreditadas', () => {
  const result = summarizeEvaluation(input({ status: 'completed' }))
  assert.equal(result.process, 'Proceso cerrado')
  assert.equal(result.human, 'Sin dictamen AG-038 por fotografía')
  assert.equal(result.ai, 'Modelo de calidad no instalado')
  assert.equal(result.dimensions, 'Sin dimensiones físicas validadas')
})

test('I01: una revisión por fotografía parcial no se presenta como evaluación humana final', () => {
  const result = summarizeEvaluation(input({ ledger: { currentValue: 'E1', decisions: [{}] } }))
  assert.equal(result.human, 'E1')
  assert.match(result.humanNote, /parcial/)
  assert.doesNotMatch(result.humanNote, /predicción automática/)
})

test('I01: revisión humana y propuesta experimental se muestran por separado', () => {
  const result = summarizeEvaluation(input({ status: 'completed',
    ledger: { currentValue: 'E0', decisions: [{}] },
    qualityStatus: { modelAvailable: true },
    proposals: [{ status: 'experimental_proposal', proposedGrade: 'E2' }] }))
  assert.equal(result.human, 'E0')
  assert.equal(result.ai, 'Sugerencia E2')
  assert.match(result.aiNote, /sin confirmación/)
})

test('I01: una predicción sin estado experimental reconocido nunca aparece como grado', () => {
  const result = summarizeEvaluation(input({ qualityStatus: { modelAvailable: true },
    proposals: [{ status: 'needs_review', proposedGrade: 'E1' }] }))
  assert.equal(result.ai, 'Sin propuesta automática')
})

test('I01: errores de consulta no se interpretan como ausencia de evidencia', () => {
  const result = summarizeEvaluation(input({ ledger: null, qualityStatus: null, proposals: null }))
  assert.match(result.humanNote, /No se pudo consultar/)
  assert.equal(result.ai, 'Análisis IA no consultado')
})

test('I01: categorías comerciales no se convierten a E0, E1 o E2', () => {
  const result = summarizeEvaluation(input({ ledger: { currentValue: 'primera', decisions: [{}] } }))
  assert.match(result.human, /sin categoría E0\/E1\/E2/)
})

test('I01: historial enlaza a AG-038, sin formulario antiguo de E0 Primera o E1 Segunda', () => {
  const history = readFileSync(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8')
  assert.match(history, /<EvaluationOutcomePanel evaluation=\{state\.data\} \/>/)
  assert.match(history, /to=\{`\/trazabilidad\/\$\{encodeURIComponent\(state\.data\.id\)\}`\}/)
  assert.doesNotMatch(history, /E0 - Primera|E1 - Segunda|handleReviewSubmit|traceabilityService\.addReview/)
})
