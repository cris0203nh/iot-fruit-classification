import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { analyzeStoredV2, summarizeCaptureV2 } from '../src/features/quality/autoV2Preview.ts'
import { clearOperatorSession, loginAgroscan } from '../src/services/agroscanApi.ts'

// Render the real components using the repository's existing TSX test pattern.
async function component(file, stubs = {}) {
  const source = readFileSync(new URL(`../src/features/quality/${file}`, import.meta.url), 'utf8')
  let code = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  } }).outputText
  const modules = {
    react: import.meta.resolve('react'), 'react/jsx-runtime': import.meta.resolve('react/jsx-runtime'),
    '../../services/agroscanApi': new URL('../src/services/agroscanApi.ts', import.meta.url).href,
    '../../services/agroscanApi.ts': new URL('../src/services/agroscanApi.ts', import.meta.url).href,
    './autoV2Preview.ts': new URL('../src/features/quality/autoV2Preview.ts', import.meta.url).href,
    ...stubs,
  }
  for (const [name, url] of Object.entries(modules)) {
    code = code.replaceAll(`from "${name}"`, `from ${JSON.stringify(url)}`)
      .replaceAll(`from '${name}'`, `from ${JSON.stringify(url)}`)
  }
  return import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))
}

const { ClassificationResult } = await component('AutoV2QualityPanel.tsx')

test('commercial: absent model shows no grade and never requests inference', async () => {
  const result = await analyzeStoredV2('E-000001', [
    { id: 'I-000001', view: 'vista-1' }, { id: 'I-000002', view: 'vista-2' },
  ], {
    getV2QualityStatus: async () => ({ models: [] }),
    getQualityProposals: async () => assert.fail('No prediction read without a model'),
    analyzeV2Quality: async () => assert.fail('No inference without a model'),
  })
  assert.equal(result.grade, null)
  const html = renderToStaticMarkup(createElement(ClassificationResult, { preview: result }))
  assert.match(html, /Clasificación no disponible/)
  assert.doesNotMatch(html, /AGROSCAN_|V2|FastAPI|Resultado preliminar: E[012]/)
})

test('commercial: technical tools remain restricted to administrators', async t => {
  const stubs = Object.fromEntries(['ExploratoryPanel', 'PilotQualityPanel', 'V2QualityPanel'].map(name =>
    [`./${name}`, `data:text/javascript,export function ${name}(){return null}`]))
  const { QualityProposalPanel } = await component('QualityProposalPanel.tsx', stubs)
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch; clearOperatorSession() })
  for (const role of ['operador', 'revisor', 'administrador']) {
    globalThis.fetch = async url => ({ ok: true, status: 200, json: async () =>
      String(url).endsWith('/auth/me') ? { roles: [role] } : { access_token: 'test-session', token_type: 'bearer' } })
    await loginAgroscan('test', 'test')
    const html = renderToStaticMarkup(createElement(QualityProposalPanel, { evaluationId: 'E-000001' }))
    if (role === 'administrador') assert.match(html, /Herramientas técnicas de clasificación/)
    else assert.equal(html, '')
  }
})

test('commercial: actual recorded inference reaches the React result', {
  skip: !process.env.AGROSCAN_INFERENCE_EVIDENCE && 'Provide the isolated real-inference evidence file',
}, () => {
  const report = JSON.parse(readFileSync(process.env.AGROSCAN_INFERENCE_EVIDENCE, 'utf8'))
  assert.equal(report.mockedInference, false)
  assert.equal(report.databaseUnchanged, true)
  for (const row of report.evaluations) {
    assert.ok(row.freshInferenceCalls.length >= 2)
    const preview = summarizeCaptureV2(row.response, row.images, row.model.modelSha256)
    assert.ok(preview)
    const html = renderToStaticMarkup(createElement(ClassificationResult, { preview }))
    if (preview.grade) {
      assert.match(html, new RegExp(`Resultado preliminar: ${preview.grade}`))
      assert.ok(row.freshInferenceCalls.every(view => view.evaluable && view.label === preview.grade))
    } else {
      assert.match(html, /Revisión requerida/)
      assert.doesNotMatch(html, /Resultado preliminar: E[012]/)
    }
    assert.doesNotMatch(html, /V2|ag055|AGROSCAN_|FastAPI/)
  }
})
