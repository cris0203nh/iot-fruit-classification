import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { homedir } from 'node:os'
import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config.ts'

// npm run dev y el lanzador usan la misma instancia DEV existente.
const dev = resolve(homedir(), 'Documents/AgroScan-Dev')
if (process.env.AGROSCAN_DEV_ROOT && resolve(process.env.AGROSCAN_DEV_ROOT) !== dev) {
  throw new Error('AGROSCAN_DEV_ROOT no corresponde al entorno DEV local')
}
const manifest = JSON.parse(readFileSync(resolve(dev, 'manifest.json'), 'utf8')) as { ready: boolean; instance: string }
if (!manifest.ready) throw new Error('Desarrollo no preparado')
export default mergeConfig(base, defineConfig({
  envDir: resolve(dev, 'frontend-env'),
  plugins: [{
    name: 'agroscan-development-connection-guard',
    configResolved(config) {
      if (config.env.VITE_API_BASE_URL) throw new Error('Desarrollo exige API relativa mediante proxy')
    },
    configureServer(server) {
      server.middlewares.use('/api', async (_request, response, next) => {
        try {
          const health = await fetch('http://127.0.0.1:8000/api/health', {
            headers: { 'X-AgroScan-Dev': manifest.instance }, signal: AbortSignal.timeout(2000),
          })
          if (!health.ok || health.headers.get('X-AgroScan-Dev-ID') !== manifest.instance) throw new Error('Backend incorrecto')
          next()
        } catch {
          response.statusCode = 503
          response.setHeader('Content-Type', 'application/json')
          response.end(JSON.stringify({ detail: 'Backend de desarrollo no disponible; no se usará otra base.' }))
        }
      })
    },
  }],
  server: { host: 'localhost', port: 5173, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true,
      headers: { 'X-AgroScan-Dev': manifest.instance } } } },
}))
