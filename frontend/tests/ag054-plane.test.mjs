import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import test from 'node:test'
const api = readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
const component = readFileSync(new URL('../src/features/geometry/PhysicalCalibrationPanel.tsx', import.meta.url), 'utf8')
const geometry = readFileSync(new URL('../src/features/geometry/GeometryEvidence.tsx', import.meta.url), 'utf8')

test('AG054 I02: nunca declara medidas 3D validadas', () => {
  assert.match(api, /physicalDimensionsValidated: false/)
  assert.match(api, /fruitHeightCorrected: false/)
  assert.match(api, /cameraIntrinsicsCalibrated: false/)
  assert.match(api, /cm_reference_plane/)
})
test('AG054 I02: la UI exige medida real y declaracion de plano', () => {
  assert.match(component, /markerAtPlatformLevel: true/)
  assert.match(component, /!samePlane/)
  assert.match(component, /Lado negro exterior/)
  assert.match(component, /plano de referencia/)
})
test('AG054 I02: visualiza el marcador sin sustituir imagen original', () => {
  assert.match(geometry, /PhysicalCalibrationPanel/)
  assert.match(geometry, /plane\?\.markerCornersPx/)
  assert.match(geometry, /ProtectedEvidenceImage/)
})
