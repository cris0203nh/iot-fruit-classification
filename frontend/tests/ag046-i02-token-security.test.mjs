/**
 * AG-046 I02 / SEC-04: comprobaciones de fuente (NO ensayo en navegador real).
 * Sin servidor, credenciales ni datos productivos.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const api = readFileSync(new URL('../src/services/agroscanApi.ts', import.meta.url), 'utf8')
const gate = readFileSync(new URL('../src/features/auth/AuthGate.tsx', import.meta.url), 'utf8')

function block(name, nextName) {
  const start = api.indexOf(name)
  const end = api.indexOf(nextName, start + name.length)
  assert.ok(start >= 0 && end > start, `No se encontró el bloque ${name}`)
  return api.slice(start, end)
}

test('SEC-04: JWT reside en variables de módulo, sin almacenamiento persistente', () => {
  assert.match(api, /let\s+sessionToken\s*:\s*string\s*\|\s*null\s*=\s*null/)
  assert.match(api, /let\s+sessionRole\s*:\s*AgroScanRole\s*\|\s*null\s*=\s*null/)
  // No admitir llamadas de persistencia del token en el cliente HTTP.
  assert.doesNotMatch(api, /\b(?:localStorage|sessionStorage)\s*(?:\.|\[|\()/)
  assert.doesNotMatch(api, /\b(?:document\.cookie|window\.name)\s*=/)
})

test('SEC-04: cierre de sesión elimina token y rol de memoria', () => {
  const logout = block('export function clearOperatorSession()', 'export function getSessionRole()')
  assert.match(logout, /sessionToken\s*=\s*null/)
  assert.match(logout, /sessionRole\s*=\s*null/)
  assert.match(gate, /onClick=\{\(\)\s*=>\s*\{\s*clearOperatorSession\(\)/)
})

test('SEC-04: el token se entrega en la cabecera Authorization, no en URL', () => {
  const request = block('async function request(', 'function isLotRecord(')
  assert.match(request, /headers\.set\(['"]Authorization['"],\s*`Bearer \$\{sessionToken\}`\)/)
  assert.doesNotMatch(request, /\?token=|access_token\s*\+|URLSearchParams\(\{\s*token/)
  const protectedImage = block('export async function loadProtectedEvidence(', 'export type AcquisitionConfirmation')
  assert.match(protectedImage, /Authorization:\s*`Bearer \$\{sessionToken\}`/)
  assert.doesNotMatch(protectedImage, /\?token=|\?access_token=/)
})

test('SEC-04: el cliente borra la sesión ante fallo de verificación de perfil', () => {
  const auth = block('async function authenticateWithRoles(', '/** Inicio de sesión general')
  assert.match(auth, /const\s+me\s*=\s*await\s+request\(['"]\/api\/auth\/me['"]\)/)
  assert.match(auth, /catch\s*\(error\)\s*\{\s*clearOperatorSession\(\)/)
})
