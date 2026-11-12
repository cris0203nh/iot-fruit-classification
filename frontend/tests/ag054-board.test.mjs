import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const service = fs.readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
const panel = fs.readFileSync(new URL('../src/features/geometry/BoardCalibrationPanel.tsx', import.meta.url), 'utf8')
const evidence = fs.readFileSync(new URL('../src/features/geometry/GeometryEvidence.tsx', import.meta.url), 'utf8')

test('AG054 I03: marco con IDs, condiciones y resultado no acreditado', () => {
  assert.match(panel, /marcadores ArUco 4×4 \(ID 0–3\)/)
  assert.match(panel, /independentSupport: true/)
  assert.match(panel, /printedDimensionsVerified: true/)
  assert.match(panel, /No es diámetro real validado/)
})
test('AG054 I03: contraste de referencia real sin conversión automática', () => {
  assert.match(panel, /referenceMajorCm: refMajor/)
  assert.match(panel, /referenceMinorCm: refMinor/)
  assert.match(panel, /Registrar contraste dimensional/)
  assert.match(panel, /no se corrige automáticamente/)
})
test('AG054 I03: API valida respuestas inalteradas y conserva estado solo proyectado', () => {
  assert.match(service, /physicalDimensionsValidated: false/)
  assert.match(service, /unit: 'cm_reference_plane'/)
  assert.match(service, /listBoardEstimates/)
  assert.match(service, /createDimensionalComparison/)
  assert.match(evidence, /BoardCalibrationPanel/)
  assert.match(evidence, /board\.markerCornersPx/)
})
