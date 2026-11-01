import type { EvaluationDetail, EvaluationSummary } from '../features/history/historyService'
import type { TraceabilityRecord } from '../features/traceability/traceabilityService'

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

/** Estado instantáneo de la última lectura recibida por la API (NO implica pesaje físico verificado). */
export type IotStatus = {
  online: boolean
  deviceId: string | null
  weightG: number | null
  stable: boolean | null
  receivedAt: string | null
  ageSeconds: number | null
}

function isIotStatus(value: unknown): value is IotStatus {
  if (!object(value)) return false
  if (typeof value.online !== 'boolean') return false
  if (!(value.deviceId === null || (typeof value.deviceId === 'string' && value.deviceId.length > 0))) return false
  if (!(value.weightG === null || (typeof value.weightG === 'number' && Number.isFinite(value.weightG) && value.weightG >= 0 && value.weightG <= 5000))) return false
  if (!(value.stable === null || typeof value.stable === 'boolean')) return false
  if (!(value.receivedAt === null || (typeof value.receivedAt === 'string' && Number.isFinite(Date.parse(value.receivedAt))))) return false
  if (!(value.ageSeconds === null || (typeof value.ageSeconds === 'number' && Number.isFinite(value.ageSeconds) && value.ageSeconds >= 0))) return false
  // El backend nunca debe publicar una masa "actual" con el dispositivo fuera de línea.
  if (!value.online) return value.weightG === null && value.stable === null
  return value.deviceId !== null && value.weightG !== null && value.stable !== null
    && value.receivedAt !== null && value.ageSeconds !== null
}

export async function getIotStatus(): Promise<IotStatus> {
  const body = await request('/api/iot/status')
  if (!isIotStatus(body)) throw new ApiDataError()
  return body
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
  if (!isLotRecord(body) || body.code !== input.code.trim() || body.product !== input.product || body.status !== 'open') {
    throw new ApiDataError()
  }
  return body
}

/** Contratos de lectura confirmados en backend/app/evaluation_schemas.py y review_schemas.py. */
const EVALUATION_ID_PATTERN = /^E-\d{1,9}$/
const IMAGE_ID_PATTERN = /^I-\d{1,9}$/
const REVIEW_ID_PATTERN = /^R-\d{1,9}$/
const STATUSES = new Set(['processing', 'completed', 'pending_review', 'error', 'cancelled'])

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isEvidence(value: unknown): boolean {
  if (!object(value)) return false
  return typeof value.id === 'string' && IMAGE_ID_PATTERN.test(value.id)
    && typeof value.view === 'string'
    && value.imageUrl === `/api/images/${value.id}`
}

function isEvaluationSummary(value: unknown): value is EvaluationSummary {
  if (!object(value)) return false
  return typeof value.id === 'string' && EVALUATION_ID_PATTERN.test(value.id)
    && typeof value.lotId === 'string' && typeof value.pieceId === 'string'
    && (value.product === 'mango' || value.product === 'tomate')
    && typeof value.registeredAt === 'string' && Number.isFinite(Date.parse(value.registeredAt))
    && typeof value.status === 'string' && STATUSES.has(value.status)
    && (value.weightGrams === null || (typeof value.weightGrams === 'number' && Number.isFinite(value.weightGrams) && value.weightGrams >= 0))
    && typeof value.imageCount === 'number' && Number.isInteger(value.imageCount) && value.imageCount >= 0
}

function isEvaluationDetail(value: unknown): value is EvaluationDetail {
  if (!isEvaluationSummary(value)) return false

  return 'evidence' in value
    && Array.isArray(value.evidence)
    && value.evidence.every(isEvidence)
    && 'visualCategory' in value
    && nullableString(value.visualCategory)
    && 'reviewNote' in value
    && nullableString(value.reviewNote)
    && 'failureReason' in value
    && nullableString(value.failureReason)
}

function isTraceability(value: unknown): value is TraceabilityRecord {
  if (!object(value) || !isEvaluationDetail(value.evaluation)) return false
  if (!nullableString(value.calibrationReference) || !nullableString(value.modelVersion) || !nullableString(value.rulesVersion)) return false
  if (!Array.isArray(value.reviews)) return false
  return value.reviews.every((review: unknown) => object(review)
    && typeof review.id === 'string' && REVIEW_ID_PATTERN.test(review.id)
    && typeof review.performedAt === 'string' && Number.isFinite(Date.parse(review.performedAt))
    && typeof review.actorId === 'string' && typeof review.reason === 'string'
    && (review.type === 'review' || review.type === 'cancellation')
    && nullableString(review.previousValue) && nullableString(review.updatedValue))
}

function validEvaluationId(id: string): boolean {
  return EVALUATION_ID_PATTERN.test(id)
}

export async function listEvaluations(): Promise<EvaluationSummary[]> {
  const body = await request('/api/evaluations')
  if (!Array.isArray(body) || !body.every(isEvaluationSummary)) throw new ApiDataError()
  return body
}

export async function getEvaluationById(id: string): Promise<EvaluationDetail | null> {
  if (!validEvaluationId(id)) return null
  try {
    const body = await request(`/api/evaluations/${encodeURIComponent(id)}`)
    if (!isEvaluationDetail(body)) throw new ApiDataError()
    return body
  } catch (error) {
    if (error instanceof ApiResponseError && error.status === 404) return null
    throw error
  }
}

export async function getEvaluationTraceability(id: string): Promise<TraceabilityRecord | null> {
  if (!validEvaluationId(id)) return null
  try {
    const body = await request(`/api/evaluations/${encodeURIComponent(id)}/traceability`)
    if (!isTraceability(body)) throw new ApiDataError()
    return body
  } catch (error) {
    if (error instanceof ApiResponseError && error.status === 404) return null
    throw error
  }
}

/** Solo permite rutas de imágenes emitidas por el backend de AgroScan. */
export function resolveEvidenceUrl(path: string): string | null {
  if (!/^\/api\/images\/I-\d{1,9}$/.test(path)) return null
  return `${API_BASE}${path}`
}

/** POST confirmado en backend/app/routers/evaluations.py. Solo inicia una evaluación; no la completa. */
export async function createEvaluation(input: { lotId: string; pieceId: string }): Promise<EvaluationDetail> {
  const lotId = input.lotId.trim()
  const pieceId = input.pieceId.trim()
  const body = await request('/api/evaluations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lotId, pieceId }),
  })
  if (!isEvaluationDetail(body) || body.lotId !== lotId || body.pieceId !== pieceId || body.status !== 'processing') {
    throw new ApiDataError()
  }
  return body
}
