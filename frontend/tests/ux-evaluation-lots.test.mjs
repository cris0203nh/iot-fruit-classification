import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filterVisibleLots } from '../src/features/lots/lotListView.ts'

const lots = Object.freeze([
  Object.freeze({ id: 1, code: 'MANGO-001', product: 'mango', status: 'open' }),
  Object.freeze({ id: 2, code: 'tomate-002', product: 'tomate', status: 'closed' }),
  Object.freeze({ id: 3, code: 'MANGO-003', product: 'mango', status: 'open' }),
])

test('I02: el filtro inicial muestra todos los lotes en el orden original', () => {
  assert.deepEqual(filterVisibleLots(lots, '', 'all').map((lot) => lot.id), [1, 2, 3])
})

test('I02: filtra lotes abiertos sin permitir que los cerrados aparezcan', () => {
  assert.deepEqual(filterVisibleLots(lots, '', 'open').map((lot) => lot.id), [1, 3])
})

test('I02: filtra lotes cerrados para consulta sin convertirlos en abiertos', () => {
  assert.deepEqual(filterVisibleLots(lots, '', 'closed').map((lot) => lot.id), [2])
  assert.equal(lots[1].status, 'closed')
})

test('I02: busca por código sin distinguir mayúsculas y omite espacios de consulta', () => {
  assert.deepEqual(filterVisibleLots(lots, '  mango  ', 'all').map((lot) => lot.id), [1, 3])
  assert.deepEqual(filterVisibleLots(lots, 'tOMaTE', 'all').map((lot) => lot.id), [2])
})

test('I02: combina búsqueda y estado sin modificar datos originales', () => {
  assert.deepEqual(filterVisibleLots(lots, 'mango', 'closed'), [])
  assert.deepEqual(lots.map((lot) => lot.id), [1, 2, 3])
})

test('I02: distingue resultados vacíos de la ausencia real de registros', () => {
  assert.deepEqual(filterVisibleLots([], 'LOTE', 'all'), [])
  assert.deepEqual(filterVisibleLots(lots, 'inexistente', 'all'), [])
})
