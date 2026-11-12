import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const service = fs.readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
const panel = fs.readFileSync(new URL('../src/features/geometry/BoardCalibrationPanel.tsx', import.meta.url), 'utf8')

test('AG054 A4: selección predeterminada A4 y versión histórica A3 disponible', () => {
  assert.match(panel, /useState<[^>]+>\('ag054-board-a4-v1'\)/)
  assert.match(panel, /<option value="ag054-board-a3-v1">/)
  assert.match(panel, /marcadores ArUco 4×4 \(ID 0–3\)/)
})
test('AG054 A4: el contrato acepta ambas versiones y no confunde imágenes originales con grado', () => {
  assert.match(service, /value\.boardVersion !== 'ag054-board-a4-v1'/)
  assert.match(service, /input\.boardVersion !== 'ag054-board-a4-v1'/)
  assert.match(service, /physicalDimensionsValidated: false/)
})
test('AG054 A4: contraste manual apunta al snapshot correspondiente', () => {
  assert.match(panel, /boardCalibrationId: selected\?\.id/)
  assert.match(service, /boardCalibrationId\?: number/)
  assert.match(panel, /sample\.boardCalibrationId === selected\.id/)
})
