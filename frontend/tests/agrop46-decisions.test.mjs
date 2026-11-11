import assert from 'node:assert/strict'
import { test } from 'node:test'
import { possibleActions, gradeOptions, canSubmitDecision } from '../src/features/traceability/reviewDecisionPolicy.ts'

test('AG038: sin grado previo solo admite etiqueta inicial o no evaluable', () => {
  assert.deepEqual(possibleActions(null), ['initial_label', 'no_evaluable'])
  assert.equal(canSubmitDecision('initial_label', null, 'E0'), true)
  assert.equal(canSubmitDecision('confirm', null, 'E0'), false)
  assert.equal(canSubmitDecision('correct', null, 'E1'), false)
})
test('AG038: confirmar no altera el grado y corregir sí', () => {
  assert.equal(canSubmitDecision('confirm', 'E1', 'E1'), true)
  assert.equal(canSubmitDecision('confirm', 'E1', 'E2'), false)
  assert.equal(canSubmitDecision('correct', 'E1', 'E2'), true)
  assert.equal(canSubmitDecision('correct', 'E1', 'E1'), false)
})
test('AG038: las taxonomías comercial y visual se mantienen separadas', () => {
  assert.deepEqual(gradeOptions('primera'), ['primera', 'segunda'])
  assert.equal(canSubmitDecision('correct', 'primera', 'E0'), false)
  assert.equal(canSubmitDecision('correct', 'E1', 'segunda'), false)
})
test('AG038: no evaluable se procesa de forma explícita', () => {
  assert.equal(canSubmitDecision('no_evaluable', 'E1', 'no_evaluable'), true)
  assert.equal(canSubmitDecision('correct', 'no_evaluable', 'E2'), true)
})
