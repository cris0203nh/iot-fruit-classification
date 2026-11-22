import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config.ts'

// Configuración solo QA: no carga .env del frontend ni admite destinos externos.
const qa = resolve(import.meta.dirname, '../.agroscan-qa')
if (process.env.AGROSCAN_QA_ROOT !== qa) throw new Error('Iniciar mediante tools/agroscan_qa.ps1')
const manifest = JSON.parse(readFileSync(resolve(qa, 'manifest.json'), 'utf8')) as { instance: string; ready: boolean }
if (!manifest.ready || process.env.AGROSCAN_QA_INSTANCE !== manifest.instance) throw new Error('QA no preparado')
export default mergeConfig(base, defineConfig({
  envDir: resolve(qa, 'frontend-env'),
  plugins: [{
    name: 'agroscan-qa-connection-guard',
    transformIndexHtml(html) {
      return { html: html.replace(/<title>[^<]*<\/title>/, '<title>AgroScan — QA local</title>'), tags: [
        { tag: 'style', children: '#qa-environment{padding:10px 16px;background:#173f2c;color:#fff;font:600 14px/1.5 system-ui;text-align:center}', injectTo: 'head' },
        { tag: 'div', attrs: { id: 'qa-environment', role: 'status' },
          children: 'QA LOCAL · Base de pruebas aislada · Sin pagos reales', injectTo: 'body-prepend' },
      ] }
    },
    configResolved(config) {
      if (config.env.VITE_API_BASE_URL) throw new Error('QA exige API relativa, sin VITE_API_BASE_URL')
    },
    configureServer(server) {
      server.middlewares.use('/api', async (_request, response, next) => {
        try {
          const health = await fetch('http://127.0.0.1:8778/api/health', {
            headers: { 'X-AgroScan-QA': manifest.instance }, signal: AbortSignal.timeout(2000),
          })
          if (!health.ok || health.headers.get('X-AgroScan-QA-ID') !== manifest.instance) throw new Error('Backend incorrecto')
          next()
        } catch {
          response.statusCode = 503
          response.setHeader('Content-Type', 'application/json')
          response.end(JSON.stringify({ detail: 'Backend QA no disponible. No se usará otra conexión.' }))
        }
      })
    },
  }],
  server: { host: '127.0.0.1', port: 5188, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8778', headers: { 'X-AgroScan-QA': manifest.instance } } } },
}))
