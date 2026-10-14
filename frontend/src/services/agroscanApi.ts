/** Cliente HTTP del frontend. Los endpoints corresponden al backend incluido en main. */
export type FruitProduct = 'mango' | 'tomate'

export type LotRecord = {
  id: number
  code: string
  product: FruitProduct
  status: 'open' | 'closed'
  responsible: string
  created_at: string
}

export class ApiConnectionError extends Error {
  constructor() {
    super('No se pudo contactar con el backend de AgroScan. Comprueba que FastAPI esté ejecutándose.')
    this.name = 'ApiConnectionError'
  }
}

export class ApiResponseError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiResponseError'
  }
}

export class ApiDataError extends Error {
  constructor() {
    super('El backend devolvió un formato de respuesta inesperado.')
    this.name = 'ApiDataError'
  }
}

const configuredBase = import.meta.env?.VITE_API_BASE_URL?.trim()
const API_BASE = (configuredBase || 'http://127.0.0.1:8000').replace(/\/+$/, '')

function detailMessage(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return null
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first: unknown = detail[0]
    if (typeof first === 'object' && first !== null && 'msg' in first && typeof first.msg === 'string') return first.msg
  }
  return null
}

async function request(path: string, options?: RequestInit): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal })
  } catch {
    throw new ApiConnectionError()
  } finally {
    clearTimeout(timer)
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    if (!response.ok) throw new ApiResponseError(response.status, `La API devolvió el estado HTTP ${response.status}.`)
    throw new ApiDataError()
  }
  if (!response.ok) throw new ApiResponseError(response.status, detailMessage(body) || `La API devolvió el estado HTTP ${response.status}.`)
  return body
}

function isLotRecord(value: unknown): value is LotRecord {
  if (typeof value !== 'object' || value === null) return false
  if (!('id' in value) || !('code' in value) || !('product' in value) || !('status' in value) || !('responsible' in value) || !('created_at' in value)) return false
  return typeof value.id === 'number' && Number.isInteger(value.id) && typeof value.code === 'string'
    && (value.product === 'mango' || value.product === 'tomate')
    && (value.status === 'open' || value.status === 'closed')
    && typeof value.responsible === 'string' && typeof value.created_at === 'string'
}

export async function getBackendHealth(): Promise<void> {
  const body = await request('/api/health')
  if (typeof body !== 'object' || body === null || !('status' in body) || body.status !== 'ok') throw new ApiDataError()
}

export async function listLots(): Promise<LotRecord[]> {
  const body = await request('/api/lots')
  if (!Array.isArray(body) || !body.every(isLotRecord)) throw new ApiDataError()
  return body
}

export async function createLot(input: { code: string; product: FruitProduct }): Promise<LotRecord> {
  const body = await request('/api/lots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: input.code, product: input.product, responsible: '' }),
  })
  if (!isLotRecord(body)) throw new ApiDataError()
  return body
}
