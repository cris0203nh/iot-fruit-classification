import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { paramsForHistoryView, resolveHistoryView } from '../src/features/history/historyView.ts'

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('I03: el historial abre evaluaciones por defecto y AG-040 con un enlace directo', () => {
  assert.equal(resolveHistoryView(null), 'evaluaciones')
  assert.equal(resolveHistoryView('otra-vista'), 'evaluaciones')
  assert.equal(resolveHistoryView('piezas'), 'piezas')
})

test('I03: cambiar de vista conserva filtros URL ajenos sin modificar el original', () => {
  const previous = new URLSearchParams('origen=panel&vista=piezas')
  const evalParams = paramsForHistoryView(previous, 'evaluaciones')
  const pieceParams = paramsForHistoryView(evalParams, 'piezas')
  assert.equal(evalParams.get('origen'), 'panel')
  assert.equal(evalParams.has('vista'), false)
  assert.equal(pieceParams.get('vista'), 'piezas')
  assert.equal(previous.get('vista'), 'piezas')
})

test('I03: alternar las vistas no desmonta el historial integral AG-040', () => {
  const history = source('pages/HistoryPage.tsx')
  assert.match(history, /className="historial__piece-view" hidden=\{currentView !== 'piezas'\}/)
  assert.match(history, /<PieceHistoryPanel suggestedLots=\{lots\} \/>/)
  assert.match(history, /aria-controls="historial-vista-piezas"/)
  assert.match(source('pages/HistoryPage.css'), /\.historial__piece-view\[hidden\]\s*\{\s*display:\s*none/)
})

test('I03: permite ir a trazabilidad desde cada registro sin alterar la consulta', () => {
  const history = source('pages/HistoryPage.tsx')
  assert.match(history, /to=\{`\/trazabilidad\/\$\{encodeURIComponent\(record\.id\)\}`\}/)
  assert.match(history, /historyService\.list\(\)/)
  assert.match(history, /historyService\.getById\(evaluationId\)/)
})

test('I03: Inicio no muestra métricas no consultadas como si fueran reales', () => {
  const home = source('pages/HomePage.tsx')
  assert.match(home, /getBackendHealth\(\)/)
  assert.match(home, /to="\/historial\?vista=piezas"/)
  assert.doesNotMatch(home, /const indicators =/)
  assert.match(home, /El estado del hardware no se deduce de la respuesta de la API/)
})

test('I03: consultas, controles y exportación AG-040 permanecen disponibles', () => {
  const panel = source('features/history/PieceHistoryPanel.tsx')
  assert.match(panel, /getLotTraceabilityReport\(lot\)/)
  assert.match(panel, /report\.integrity\.status === 'inconsistent'/)
  assert.match(panel, /downloadReport\('csv'\)/)
  assert.match(panel, /downloadReport\('json'\)/)
  const trace = source('pages/TraceabilityPage.tsx')
  assert.match(trace, /traceabilityService\.getByEvaluationId\(evaluationId\)/)
  assert.match(trace, /markUncertainEvaluationImage\(/)
  assert.match(trace, /resolveUncertainEvaluation\(/)
  assert.match(trace, /<ReviewDecisionPanel record=\{record\}/)
})
