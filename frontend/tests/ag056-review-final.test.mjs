import assert from 'node:assert/strict'
import test from 'node:test'
import { chooseReviewImage, eligibleReviewImages } from '../src/features/reviews/pendingImagePolicy.ts'

const evidence = Object.freeze([{ id: 'I-000001' }, { id: 'I-000002' }])

test('AG056 I04: first decision automatically advances to unreviewed second photo', () => {
  const options = eligibleReviewImages(evidence, [])
  assert.equal(chooseReviewImage(options, []), 'I-000001')
  assert.equal(chooseReviewImage(options, [{ imageId: 'I-000001' }]), 'I-000002')
})

test('AG056 I04: queue source identity limits selectable photos', () => {
  const options = eligibleReviewImages(evidence, ['I-000002'])
  assert.deepEqual(options, [{ id: 'I-000002' }])
  assert.equal(chooseReviewImage(options, [], 'I-000001'), 'I-000002')
})

test('AG056 I04: invalid or missing source ID never falls back to other images', () => {
  assert.deepEqual(eligibleReviewImages(evidence, ['I-999999']), [])
  assert.equal(chooseReviewImage([], []), '')
})

test('AG056 I04: explicit eligible selection is preserved, never a foreign selection', () => {
  const options = eligibleReviewImages(evidence)
  assert.equal(chooseReviewImage(options, [], 'I-000002'), 'I-000002')
  assert.equal(chooseReviewImage(options, [], 'I-999999'), 'I-000001')
})

test('AG056 I04: no source data is mutated during selection', () => {
  const decisions = Object.freeze([{ imageId: 'I-000001' }])
  eligibleReviewImages(evidence, ['I-000001'])
  chooseReviewImage(evidence, decisions)
  assert.deepEqual(evidence, [{ id: 'I-000001' }, { id: 'I-000002' }])
  assert.deepEqual(decisions, [{ imageId: 'I-000001' }])
})
