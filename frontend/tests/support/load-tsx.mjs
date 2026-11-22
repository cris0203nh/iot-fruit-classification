import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

// Compila componentes reales sin dependencias adicionales. Conserva imports TS
// nativos y resuelve componentes TSX anidados para pruebas SSR de contrato.
const cache = new Map()
export function tsxUrl(url) {
  const href = String(url)
  if (cache.has(href)) return cache.get(href)
  let code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
  } }).outputText.replace(/^import\s+["'].*\.css["'];?$/gm, '')
  code = code.replace(/from (["'])([^"']+)\1/g, (_all, _quote, name) => {
    let target
    if (name.startsWith('.')) {
      if (/\.(webp|png|jpe?g|gif|svg|avif)$/.test(name)) {
        const asset = new URL(name, url)
        if (!existsSync(asset)) throw new Error(`Asset not found: ${asset.pathname}`)
        // Vite devuelve una URL para assets; SSR necesita el mismo contrato,
        // sin convertir el archivo binario en un modulo TypeScript.
        return 'from ' + JSON.stringify('data:text/javascript;base64,' +
          Buffer.from('export default ' + JSON.stringify(asset.href)).toString('base64'))
      }
      let resolved = new URL(/\.tsx?$/.test(name) ? name : name + '.tsx', url)
      if (!existsSync(resolved)) resolved = new URL(name + '.ts', url)
      target = resolved.pathname.endsWith('.tsx') ? tsxUrl(resolved) : resolved.href
    } else target = import.meta.resolve(name)
    return 'from ' + JSON.stringify(target)
  })
  const target = 'data:text/javascript;base64,' + Buffer.from(code).toString('base64')
  cache.set(href, target)
  return target
}
