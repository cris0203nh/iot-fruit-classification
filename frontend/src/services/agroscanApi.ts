import type { EvaluationDetail, EvaluationSummary } from '../features/history/historyService'
import type { TraceabilityRecord } from '../features/traceability/traceabilityService'
import { buildReviewQueueQuery, parseReviewQueue,
  type ReviewQueueFilters, type ReviewQueueResponse } from '../features/reviews/reviewQueuePolicy.ts'
import { validatePieceAggregates } from '../features/history/pieceHistoryPolicy.ts'
import { validateLotTraceabilityReport, type LotTraceabilityReport } from '../features/history/pieceReportPolicy.ts'

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
// En desarrollo, Vite redirige /api a FastAPI; también funciona desde el teléfono en la LAN.
const API_BASE = (configuredBase || '').replace(/\/+$/, '')

// Token de sesión exclusivamente en memoria; nunca se guarda en localStorage ni en URL.
export type AgroScanRole = 'administrador' | 'operador' | 'revisor'
let sessionToken: string | null = null
let sessionRole: AgroScanRole | null = null

export function clearOperatorSession(): void {
  sessionToken = null
  sessionRole = null
}

export function getSessionRole(): AgroScanRole | null {
  return sessionRole
}

export function isAgroscanAuthenticated(): boolean {
  return sessionToken !== null && sessionRole !== null
}

export function isOperatorAuthenticated(): boolean {
  return isAgroscanAuthenticated() && (sessionRole === 'operador' || sessionRole === 'administrador')
}

/** AG-056: cola derivada de SQLite; el token JWT permanece en memoria. */
export async function getReviewQueue(filters: ReviewQueueFilters = {}): Promise<ReviewQueueResponse> {
  if (sessionRole !== 'revisor' && sessionRole !== 'administrador') {
    throw new ApiResponseError(403, 'Acceso exclusivo para revisores y administradores.')
  }
  let query: string
  try { query = buildReviewQueueQuery(filters) }
  catch { throw new ApiDataError() }
  const limit = filters.limit ?? 20
  const offset = filters.offset ?? 0
  const body = await request(`/api/reviews/queue?${query}`)
  try { return parseReviewQueue(body, { limit, offset }) }
  catch { throw new ApiDataError() }
}

function detailMessage(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return null
  }

  const detail = body.detail

  if (typeof detail === 'string') return detail

  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    const message = detail.message
    const action = 'action' in detail ? detail.action : null

    if (typeof message === 'string') {
      return typeof action === 'string'
        ? `${message} ${action}`
        : message
    }
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first: unknown = detail[0]

    if (
      typeof first === 'object'
      && first !== null
      && 'msg' in first
      && typeof first.msg === 'string'
    ) {
      return first.msg
    }
  }

  return null
}

async function request(
  path: string,
  options?: RequestInit,
  timeoutMs = 8000
): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let response: Response
  try {
    const headers = sessionToken ? new Headers(options?.headers) : options?.headers
    if (sessionToken && headers instanceof Headers) headers.set('Authorization', `Bearer ${sessionToken}`)
    response = await fetch(`${API_BASE}${path}`, { ...options, ...(headers ? { headers } : {}), signal: controller.signal })
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
export type WeightStep = {
  stage: 'pre' | 'post'
  weightG: number
  deviceId: string
  receivedAt: string
}

function isWeightStep(value: unknown): value is WeightStep {
  if (!object(value)) return false

  return (value.stage === 'pre' || value.stage === 'post')
    && typeof value.weightG === 'number'
    && Number.isFinite(value.weightG)
    && value.weightG >= 0
    && typeof value.deviceId === 'string'
    && value.deviceId.length > 0
    && typeof value.receivedAt === 'string'
    && Number.isFinite(Date.parse(value.receivedAt))
}

export async function captureWeightPre(
  evaluationId: string,
): Promise<WeightStep> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/weight/pre`,
    { method: 'POST' },
  )

  if (!isWeightStep(body) || body.stage !== 'pre') {
    throw new ApiDataError()
  }

  return body
}

export async function captureWeightPost(
  evaluationId: string,
): Promise<WeightStep> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/weight/post`,
    { method: 'POST' },
  )

  if (!isWeightStep(body) || body.stage !== 'post') {
    throw new ApiDataError()
  }

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
    && (review.type === 'review' || review.type === 'cancellation' || review.type === 'uncertainty')
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

/** AGROP-43: contrato de registro de revisión. */
export type EvaluationReviewInput = {
  reason: string
  newValue: 'E0' | 'E1'
}

function isReviewEvent(value: unknown): value is import('../features/traceability/traceabilityService').ReviewEvent {
  if (!object(value)) return false

  return typeof value.id === 'string'
    && REVIEW_ID_PATTERN.test(value.id)
    && typeof value.performedAt === 'string'
    && Number.isFinite(Date.parse(value.performedAt))
    && typeof value.actorId === 'string'
    && typeof value.reason === 'string'
    && value.type === 'review'
    && nullableString(value.previousValue)
    && nullableString(value.updatedValue)
}

/**
 * Registra una revisión utilizando la sesión autenticada.
 * El backend determina el responsable real mediante current_user.
 */
export async function createEvaluationReview(
  evaluationId: string,
  input: EvaluationReviewInput,
): Promise<TraceabilityRecord['reviews'][number]> {
  if (!validEvaluationId(evaluationId)) {
    throw new ApiDataError()
  }

  if (getSessionRole() !== 'revisor') {
    throw new ApiResponseError(
      403,
      'Solo el usuario revisor puede registrar revisiones.',
    )
  }

  const reason = input.reason.trim()

  if (!reason || reason.length > 500) {
    throw new ApiDataError()
  }

  if (input.newValue !== 'E0' && input.newValue !== 'E1') {
    throw new ApiDataError()
  }

  // ReviewCreate exige actorId. Se obtiene del usuario autenticado.
  const currentUser = await request('/api/auth/me')

  if (!object(currentUser) || typeof currentUser.username !== 'string') {
    throw new ApiDataError()
  }

  const actorId = currentUser.username

  if (!actorId.trim() || actorId.length > 64) {
    throw new ApiDataError()
  }

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/reviews`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        actorId,
        reason,
        newValue: input.newValue,
      }),
    },
  )

  if (!isReviewEvent(body)) {
    throw new ApiDataError()
  }

  return body
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


/** AGROP-32: evidencia RGB asociada a una evaluación. */
export type CapturedEvidence = {
  id: string
  view: string
  imageUrl: string
}

/** Genera una clave estable para identificar el mismo archivo y reintento. */
export async function createEvidenceIdempotencyKey(
  evaluationId: string,
  file: File,
  view: string,
): Promise<string> {
  const prefix = new TextEncoder().encode(
    `${evaluationId}|${view}|${file.name}|${file.size}|${file.lastModified}|`,
  )

  const content = new Uint8Array(await file.arrayBuffer())
  const combined = new Uint8Array(prefix.length + content.length)

  combined.set(prefix)
  combined.set(content, prefix.length)

  const digest = await crypto.subtle.digest('SHA-256', combined)

  return Array.from(new Uint8Array(digest))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('')
}

/** AGROP-32: subida RGB idempotente y recuperable. */
export async function uploadEvaluationPhoto(
  evaluationId: string,
  file: File,
  view = 'vista-1',
): Promise<CapturedEvidence> {
  if (
    !validEvaluationId(evaluationId) ||
    !/^vista-[1-9]\d{0,2}$/.test(view)
  ) {
    throw new ApiDataError()
  }

  const idempotencyKey = await createEvidenceIdempotencyKey(
    evaluationId,
    file,
    view,
  )

  const form = new FormData()
  form.append('view', view)
  form.append('file', file, file.name)

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/images`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: form,
    },
  )

  if (!isEvidence(body) || !object(body) || body.view !== view) {
    throw new ApiDataError()
  }

  return {
    id: body.id as string,
    view: body.view as string,
    imageUrl: body.imageUrl as string,
  }
}



/** AGROP-47: autentica al operador contra FastAPI y verifica su rol real. */
async function authenticateWithRoles(
  username: string,
  password: string,
  allowedRoles: readonly AgroScanRole[],
): Promise<AgroScanRole> {
  clearOperatorSession()
  if (!username.trim() || !password) throw new ApiDataError()
  const credentials = new URLSearchParams({ username: username.trim(), password })
  const login = await request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: credentials,
  })
  if (!object(login) || typeof login.access_token !== 'string' || !login.access_token || login.token_type !== 'bearer') {
    throw new ApiDataError()
  }
  sessionToken = login.access_token
  try {
    const me = await request('/api/auth/me')
    if (!object(me) || !Array.isArray(me.roles) || !me.roles.every((role: unknown) => typeof role === 'string')) {
      throw new ApiDataError()
    }
    const recognized: readonly AgroScanRole[] = ['administrador', 'operador', 'revisor']
    const validatedRoles: string[] = me.roles
    const role = recognized.find((candidate) => validatedRoles.includes(candidate) && allowedRoles.includes(candidate))
    if (!role) {
      throw new ApiResponseError(403, 'Esta cuenta no tiene permisos para acceder al módulo solicitado.')
    }
    sessionRole = role
    return role
  } catch (error) {
    clearOperatorSession()
    throw error
  }
}

/** Inicio de sesión general: los revisores pueden consultar, nunca operar el registro. */
export async function loginAgroscan(username: string, password: string): Promise<AgroScanRole> {
  return authenticateWithRoles(username, password, ['administrador', 'operador', 'revisor'])
}

/** Mantiene la restricción anterior para flujos que requieren operador o administrador. */
export async function loginOperator(username: string, password: string): Promise<void> {
  await authenticateWithRoles(username, password, ['administrador', 'operador'])
}

/** Imágenes protegidas AGROP-47: el token va en la cabecera, nunca en el src ni en la URL. */
export async function loadProtectedEvidence(path: string, signal?: AbortSignal): Promise<Blob> {
  const url = resolveEvidenceUrl(path)
  if (!url) throw new ApiDataError()
  if (!sessionToken) throw new ApiResponseError(401, 'Inicia sesión para consultar las fotografías.')
  let response: Response
  try {
    response = await fetch(url, { headers: { Authorization: `Bearer ${sessionToken}` }, signal })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiConnectionError()
  }
  if (!response.ok) throw new ApiResponseError(response.status, `No se pudo obtener la fotografía (HTTP ${response.status}).`)
  const contentType = response.headers.get('content-type')?.split(';', 1)[0]?.trim()
  if (contentType !== 'image/jpeg' && contentType !== 'image/png') throw new ApiDataError()
  const blob = await response.blob()
  if (blob.size === 0 || blob.size > 5 * 1024 * 1024) throw new ApiDataError()
  return blob
}
export type AcquisitionConfirmation = {
  confirmed: true
  evaluationId: string
  pieceId: string
  product: FruitProduct
  weightGrams: number
  imageCount: number
  deviceId: string
}

export async function confirmEvaluationAcquisition(
  evaluationId: string,
): Promise<AcquisitionConfirmation> {
  if (!validEvaluationId(evaluationId)) {
    throw new ApiDataError()
  }

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/acquisition/confirm`,
    { method: 'POST' },
  )

  if (
    !object(body)
    || body.confirmed !== true
    || body.evaluationId !== evaluationId
    || typeof body.pieceId !== 'string'
    || (body.product !== 'mango' && body.product !== 'tomate')
    || typeof body.weightGrams !== 'number'
    || !Number.isFinite(body.weightGrams)
    || body.weightGrams < 0
    || typeof body.imageCount !== 'number'
    || !Number.isInteger(body.imageCount)
    || body.imageCount < 1
    || typeof body.deviceId !== 'string'
  ) {
    throw new ApiDataError()
  }

  return body as AcquisitionConfirmation
}



// AGROP-42: resultado de detecci?n y segmentaci?n en vivo.

/** AG-053: detección YOLOE sin evaluación previa ni predicción de calidad. */
export type FruitPrecheck = {
  detected: boolean
  readyToRegister: boolean
  product: FruitProduct | null
  confidence: number | null
  candidateCount: number
  box: [number, number, number, number] | null
  polygon: Array<[number, number]>
  frameWidth: number
  frameHeight: number
  reason: string
  detectionToken: string | null
  modelVersion: string
  classificationE0E1E2Produced: false
}

export async function precheckFruit(frame: File): Promise<FruitPrecheck> {
  if (frame.type !== 'image/jpeg' || !frame.size) throw new ApiDataError()
  const form = new FormData()
  form.append('file', frame, frame.name)
  const body = await request('/api/vision/precheck', { method: 'POST', body: form }, 120000)
  if (!object(body) || typeof body.detected !== 'boolean'
    || typeof body.readyToRegister !== 'boolean'
    || typeof body.candidateCount !== 'number'
    || typeof body.reason !== 'string' || typeof body.modelVersion !== 'string'
    || typeof body.frameWidth !== 'number' || typeof body.frameHeight !== 'number'
    || body.classificationE0E1E2Produced !== false) throw new ApiDataError()
  if (body.readyToRegister) {
    if (!(body.product === 'mango' || body.product === 'tomate')
      || typeof body.detectionToken !== 'string'
      || !/^[a-f0-9]{64}$/.test(body.detectionToken)
      || typeof body.confidence !== 'number' || body.confidence < 0.40) throw new ApiDataError()
  } else if (body.detectionToken !== null || body.product !== null) {
    throw new ApiDataError()
  }
  return body as unknown as FruitPrecheck
}

/** El token permite reintentar sin duplicar la pieza, incluso con respuesta perdida. */
export async function createAutomaticEvaluation(input: {
  lotId: string
  detectionToken: string
}): Promise<EvaluationDetail> {
  if (!input.lotId.trim() || !/^[a-f0-9]{64}$/.test(input.detectionToken)) throw new ApiDataError()
  const body = await request('/api/evaluations/auto', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lotId: input.lotId.trim(), detectionToken: input.detectionToken }),
  }, 30000)
  if (!isEvaluationDetail(body) || body.lotId.toLowerCase() !== input.lotId.trim().toLowerCase()
    || body.status !== 'processing' || !/^P-\d{6,9}$/.test(body.pieceId)) throw new ApiDataError()
  return body
}

/** AG-054: geometría 2D versionada sobre fotografías originales persistidas. */
export type FruitGeometryMeasurements = {
  widthPx: number
  heightPx: number
  majorAxisPx: number
  minorAxisPx: number
  areaPx2: number
  perimeterPx: number
  aspectRatio: number
  frameCoverage: number
}
/** AG-054 I02: proyeccion sobre plano ArUco; no dimensiones fisicas validadas. */
export type PlanarMeasurement = {
  id: number
  evaluationId: string
  imageId: string
  geometryId: number
  imageSha256: string
  modelVersion: string
  rulesVersion: string
  markerId: number
  markerSideMm: number
  markerAtPlatformLevelDeclared: boolean
  status: 'reference_plane_estimate' | 'needs_review'
  reason: string
  markerCornersPx: Array<[number, number]>
  measurements: null | {
    widthCm: number
    heightCm: number
    majorAxisCm: number
    minorAxisCm: number
    projectedAreaCm2: number
    projectedPerimeterCm: number
  }
  unit: 'cm_reference_plane'
  physicalDimensionsValidated: false
  cameraIntrinsicsCalibrated: false
  fruitHeightCorrected: false
  classificationE0E1E2Produced: false
  createdAt: string
}

function validPlanarMeasurement(value: unknown): value is PlanarMeasurement {
  if (!object(value) || !Number.isSafeInteger(value.id) || !Number.isSafeInteger(value.geometryId)
      || typeof value.evaluationId !== 'string' || !EVALUATION_ID_PATTERN.test(value.evaluationId)
      || typeof value.imageId !== 'string' || !IMAGE_ID_PATTERN.test(value.imageId)
      || typeof value.imageSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.imageSha256)
      || typeof value.modelVersion !== 'string' || typeof value.rulesVersion !== 'string'
      || !Number.isInteger(value.markerId) || typeof value.markerSideMm !== 'number'
      || !Number.isFinite(value.markerSideMm) || value.markerSideMm < 15 || value.markerSideMm > 150
      || value.markerAtPlatformLevelDeclared !== true
      || (value.status !== 'reference_plane_estimate' && value.status !== 'needs_review')
      || typeof value.reason !== 'string' || !Array.isArray(value.markerCornersPx)
      || !value.markerCornersPx.every(point => Array.isArray(point) && point.length === 2
         && point.every(n => typeof n === 'number' && Number.isFinite(n)))
      || value.unit !== 'cm_reference_plane' || value.physicalDimensionsValidated !== false
      || value.cameraIntrinsicsCalibrated !== false || value.fruitHeightCorrected !== false
      || value.classificationE0E1E2Produced !== false || typeof value.createdAt !== 'string'
      || !Number.isFinite(Date.parse(value.createdAt))) return false
  if (value.status === 'needs_review') return value.measurements === null
  if (!object(value.measurements)) return false
  return ['widthCm', 'heightCm', 'majorAxisCm', 'minorAxisCm', 'projectedAreaCm2', 'projectedPerimeterCm']
    .every(k => typeof (value.measurements as Record<string, unknown>)[k] === 'number'
      && Number.isFinite((value.measurements as Record<string, number>)[k])
      && (value.measurements as Record<string, number>)[k] > 0)
}

export async function listPlanarMeasurements(evaluationId: string, imageId: string): Promise<PlanarMeasurement[]> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)) throw new ApiDataError()
  const items = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/physical/${encodeURIComponent(imageId)}`)
  if (!Array.isArray(items) || !items.every(validPlanarMeasurement)
      || !items.every(v => v.evaluationId === evaluationId && v.imageId === imageId)) throw new ApiDataError()
  return items
}

export async function createPlanarMeasurement(evaluationId: string, imageId: string, input: {
  markerId: number; markerSideMm: number; markerAtPlatformLevel: boolean
}): Promise<PlanarMeasurement> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId) ||
      input.markerId !== 0 || !Number.isFinite(input.markerSideMm) || input.markerSideMm < 15 ||
      input.markerSideMm > 150 || input.markerAtPlatformLevel !== true) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/physical/${encodeURIComponent(imageId)}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input),
  }, 45000)
  if (!validPlanarMeasurement(value) || value.evaluationId !== evaluationId || value.imageId !== imageId) throw new ApiDataError()
  return value
}

export type FruitGeometryResult = {
  id: number
  evaluationId: string
  imageId: string
  imageSha256: string
  modelVersion: string
  rulesVersion: string
  status: 'measured' | 'needs_review'
  reason: string
  product: FruitProduct | null
  confidence: number | null
  candidateCount: number
  frameWidth: number
  frameHeight: number
  box: [number, number, number, number] | null
  polygon: Array<[number, number]>
  measurements: FruitGeometryMeasurements | null
  unit: 'px'
  calibrated: false
  classificationE0E1E2Produced: false
  createdAt: string
}
function geometryResult(value: unknown): value is FruitGeometryResult {
  if (!object(value) || !Number.isSafeInteger(value.id) || typeof value.evaluationId !== 'string'
      || !EVALUATION_ID_PATTERN.test(value.evaluationId) || typeof value.imageId !== 'string'
      || !IMAGE_ID_PATTERN.test(value.imageId) || typeof value.imageSha256 !== 'string'
      || !/^[a-f0-9]{64}$/.test(value.imageSha256) || typeof value.modelVersion !== 'string'
      || typeof value.rulesVersion !== 'string' || (value.status !== 'measured' && value.status !== 'needs_review')
      || typeof value.reason !== 'string' || !(value.product === null || value.product === 'mango' || value.product === 'tomate')
      || !(value.confidence === null || (typeof value.confidence === 'number' && Number.isFinite(value.confidence)))
      || !Number.isSafeInteger(value.candidateCount) || !Number.isSafeInteger(value.frameWidth)
      || !Number.isSafeInteger(value.frameHeight) || (value.frameWidth as number) < 128
      || (value.frameHeight as number) < 128 || !Array.isArray(value.polygon)
      || !value.polygon.every(point => Array.isArray(point) && point.length === 2 && point.every((n: unknown) => typeof n === 'number' && Number.isFinite(n)))
      || !(value.box === null || (Array.isArray(value.box) && value.box.length === 4 && value.box.every((n: unknown) => typeof n === 'number' && Number.isFinite(n))))
      || value.unit !== 'px' || value.calibrated !== false || value.classificationE0E1E2Produced !== false
      || typeof value.createdAt !== 'string' || !Number.isFinite(Date.parse(value.createdAt))) return false
  if (value.measurements === null) return value.status === 'needs_review'
  if (value.status !== 'measured' || !object(value.measurements)) return false
  return ['widthPx', 'heightPx', 'majorAxisPx', 'minorAxisPx', 'areaPx2',
    'perimeterPx', 'aspectRatio', 'frameCoverage'].every(key =>
    typeof (value.measurements as Record<string, unknown>)[key] === 'number'
    && Number.isFinite((value.measurements as Record<string, number>)[key]))
}

export async function listFruitGeometries(evaluationId: string): Promise<FruitGeometryResult[]> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const body = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/geometry`)
  if (!Array.isArray(body) || !body.every(geometryResult)
      || !body.every(item => item.evaluationId === evaluationId)) throw new ApiDataError()
  return body
}

export async function analyzeFruitGeometry(evaluationId: string, imageId: string): Promise<FruitGeometryResult> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)) throw new ApiDataError()
  const body = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/geometry/${encodeURIComponent(imageId)}`,
    { method: 'POST' }, 120000)
  if (!geometryResult(body) || body.evaluationId !== evaluationId || body.imageId !== imageId) throw new ApiDataError()
  return body
}

export type FruitDetectionResult = {
  detected: boolean
  readyToCapture: boolean
  product: FruitProduct
  confidence: number | null
  box: [number, number, number, number] | null
  polygon: Array<[number, number]>
  candidateCount: number
  frameWidth: number
  frameHeight: number
  reason: string
}

export async function detectEvaluationFrame(
  evaluationId: string,
  frame: Blob
): Promise<FruitDetectionResult> {

  if (!validEvaluationId(evaluationId) || frame.type !== "image/jpeg") {
    throw new ApiDataError()
  }

  const form = new FormData()
  form.append("file", frame, "fotograma.jpg")

  const body = await request(
    `/api/evaluations/${encodeURIComponent(evaluationId)}/vision/detect`,
    {
      method: "POST",
      body: form
    },
    30000
  )

  if (typeof body !== "object" || body === null) {
    throw new ApiDataError()
  }

  const value = body as Record<string, unknown>

  if (
    typeof value.detected !== "boolean" ||
    typeof value.readyToCapture !== "boolean" ||
    typeof value.frameWidth !== "number" ||
    typeof value.frameHeight !== "number" ||
    typeof value.candidateCount !== "number" ||
    !Array.isArray(value.polygon)
  ) {
    throw new ApiDataError()
  }

  return value as unknown as FruitDetectionResult
}

// AGROSCAN: consulta de usuarios para el Dashboard administrativo.

export type AdminUser = {
  id: number
  username: string
  fullName: string
  isActive: boolean
  roles: string[]
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  if (getSessionRole() !== 'administrador') {
    throw new ApiResponseError(403, 'Acceso exclusivo del administrador.')
  }

  const body = await request('/api/users')

  if (!Array.isArray(body)) throw new ApiDataError()

  const valid = body.every((user: unknown) =>
    object(user)
    && typeof user.id === 'number'
    && typeof user.username === 'string'
    && typeof user.fullName === 'string'
    && typeof user.isActive === 'boolean'
    && Array.isArray(user.roles)
    && user.roles.every((role: unknown) => typeof role === 'string')
  )

  if (!valid) throw new ApiDataError()

  return body as AdminUser[]
}

// ====
// GESTIÓN ADMINISTRATIVA DE USUARIOS
// ====

export type AdminRole = 'administrador' | 'operador' | 'revisor'

export type AdminUserCreateInput = {
  username: string
  fullName: string
  password: string
  role: AdminRole
}

export async function createAdminUser(
  input: AdminUserCreateInput,
): Promise<AdminUser> {
  if (getSessionRole() !== 'administrador') {
    throw new ApiResponseError(403, 'Acceso exclusivo del administrador.')
  }

  const username = input.username.trim().toLowerCase()
  const fullName = input.fullName.trim()

  if (username.length < 3 || fullName.length < 2 || input.password.length < 12) {
    throw new ApiDataError()
  }

  const body = await request('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      fullName,
      password: input.password,
      role: input.role,
    }),
  })

  if (
    !object(body)
    || typeof body.id !== 'number'
    || typeof body.username !== 'string'
    || typeof body.fullName !== 'string'
    || typeof body.isActive !== 'boolean'
    || !Array.isArray(body.roles)
  ) {
    throw new ApiDataError()
  }

  return body as AdminUser
}

export async function updateAdminUserRole(
  userId: number,
  role: AdminRole,
): Promise<AdminUser> {
  if (getSessionRole() !== 'administrador') {
    throw new ApiResponseError(403, 'Acceso exclusivo del administrador.')
  }

  const body = await request(`/api/users/${userId}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })

  if (
    !object(body)
    || typeof body.id !== 'number'
    || typeof body.username !== 'string'
    || typeof body.fullName !== 'string'
    || typeof body.isActive !== 'boolean'
    || !Array.isArray(body.roles)
  ) {
    throw new ApiDataError()
  }

  return body as AdminUser
}

export async function updateAdminUserStatus(
  userId: number,
  isActive: boolean,
): Promise<AdminUser> {
  if (getSessionRole() !== 'administrador') {
    throw new ApiResponseError(403, 'Acceso exclusivo del administrador.')
  }

  const body = await request(`/api/users/${userId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ isActive }),
  })

  if (
    !object(body)
    || typeof body.id !== 'number'
    || typeof body.username !== 'string'
    || typeof body.fullName !== 'string'
    || typeof body.isActive !== 'boolean'
    || !Array.isArray(body.roles)
  ) {
    throw new ApiDataError()
  }

  return body as AdminUser
}

/** AG-037: detección asociada a una imagen ya guardada (no calidad E0/E1/E2). */
export type UncertaintyGateResponse = {
  evaluationId: string
  imageId: string
  status: 'processing' | 'completed' | 'pending_review'
  decision: 'pending_review' | 'ready_to_capture'
  reason: string
  imageSha256: string
  threshold: number
  assessmentId: number | null
  originalPreserved: true
  visualCategoryChanged: false
  classificationE0E1E2Produced: false
}

function isGateResponse(value: unknown, evaluationId: string, imageId: string): value is UncertaintyGateResponse {
  return object(value) && value.evaluationId === evaluationId && value.imageId === imageId
    && (value.status === 'processing' || value.status === 'completed' || value.status === 'pending_review')
    && (value.decision === 'pending_review' || value.decision === 'ready_to_capture')
    && typeof value.reason === 'string' && /^[a-f0-9]{64}$/.test(String(value.imageSha256))
    && typeof value.threshold === 'number' && value.originalPreserved === true
    && value.visualCategoryChanged === false && value.classificationE0E1E2Produced === false
}

/** Evalúa automáticamente una foto persistida sin generar grado de calidad. */
export async function assessEvaluationImage(evaluationId: string, imageId: string): Promise<UncertaintyGateResponse> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)) throw new ApiDataError()
  const body = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/review-gate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageId }),
  }, 120000)
  if (!isGateResponse(body, evaluationId, imageId)) throw new ApiDataError()
  return body
}

/** Un revisor puede objetar una foto sin modificar la salida automática. */
export async function markUncertainEvaluationImage(evaluationId: string, imageId: string, note: string): Promise<UncertaintyGateResponse> {
  const text = note.trim()
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)
      || text.length < 10 || text.length > 300) throw new ApiDataError()
  const body = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/review-gate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageId, forceReview: true, note: text }),
  })
  if (!isGateResponse(body, evaluationId, imageId) || body.status !== 'pending_review') throw new ApiDataError()
  return body
}

export type VisionAssessment = {
  id: number
  imageId: string
  outcome: 'pending_review' | 'ready_to_capture'
  reason: string
  confidence: number | null
  threshold: number
  imageSha256: string
  modelVersion: string
}

export async function getVisionAssessments(evaluationId: string): Promise<VisionAssessment[]> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const body = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/assessments`)
  if (!Array.isArray(body) || !body.every(item => object(item) && typeof item.id === 'number'
      && typeof item.imageId === 'string' && typeof item.reason === 'string'
      && typeof item.imageSha256 === 'string' && typeof item.modelVersion === 'string'
      && typeof item.threshold === 'number' && (item.confidence === null || typeof item.confidence === 'number')
      && (item.outcome === 'pending_review' || item.outcome === 'ready_to_capture'))) throw new ApiDataError()
  return body as VisionAssessment[]
}

export async function resolveUncertainEvaluation(evaluationId: string, outcome: 'E0' | 'E1' | 'E2' | 'no_evaluable', reason: string): Promise<void> {
  const note = reason.trim()
  if (!validEvaluationId(evaluationId) || note.length < 10 || note.length > 500) throw new ApiDataError()
  const response = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/resolve`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outcome, reason: note }),
  })
  if (!object(response) || response.evaluationId !== evaluationId
      || response.status !== 'completed' || response.reviewOutcome !== outcome
      || response.originalPreserved !== true) throw new ApiDataError()
}

/** AG-038: bitácora de decisiones vinculadas a una fotografía y su SHA256. */
export type ReviewDecisionAction = 'confirm' | 'correct' | 'initial_label' | 'no_evaluable'
export type HumanReviewDecision = {
  id: string
  evaluationId: string
  action: ReviewDecisionAction
  previousValue: string | null
  newValue: string
  actorId: string
  performedAt: string
  reason: string
  imageId: string
  imageSha256: string
  requestId: string
}
export type ReviewDecisionLedger = {
  evaluationId: string
  originalValue: string | null
  currentValue: string | null
  revisionId: string | null
  decisions: HumanReviewDecision[]
}
export type NewReviewDecision = {
  action: ReviewDecisionAction
  imageId: string
  newValue: string
  reason: string
  expectedReviewId: string | null
  requestId: string
}

function isReviewDecision(entry: unknown): entry is HumanReviewDecision {
  return object(entry) && typeof entry.id === 'string' && /^R-\d{1,9}$/.test(entry.id)
    && typeof entry.evaluationId === 'string' && validEvaluationId(entry.evaluationId)
    && ['confirm', 'correct', 'initial_label', 'no_evaluable'].includes(String(entry.action))
    && nullableString(entry.previousValue) && typeof entry.newValue === 'string'
    && typeof entry.actorId === 'string' && typeof entry.performedAt === 'string'
    && Number.isFinite(Date.parse(entry.performedAt)) && typeof entry.reason === 'string'
    && typeof entry.imageId === 'string' && IMAGE_ID_PATTERN.test(entry.imageId)
    && typeof entry.imageSha256 === 'string' && /^[0-9a-f]{64}$/.test(entry.imageSha256)
    && typeof entry.requestId === 'string'
}

export async function getReviewDecisions(evaluationId: string): Promise<ReviewDecisionLedger> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const data = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/review-decisions`)
  if (!object(data) || data.evaluationId !== evaluationId
      || !nullableString(data.originalValue) || !nullableString(data.currentValue)
      || !nullableString(data.revisionId) || (data.revisionId !== null && !/^R-\d{1,9}$/.test(data.revisionId))
      || !Array.isArray(data.decisions) || !data.decisions.every(isReviewDecision)) throw new ApiDataError()
  return data as unknown as ReviewDecisionLedger
}

export async function postReviewDecision(evaluationId: string, decision: NewReviewDecision): Promise<HumanReviewDecision> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(decision.imageId)
      || decision.reason.trim().length < 10 || decision.reason.trim().length > 500
      || !['confirm', 'correct', 'initial_label', 'no_evaluable'].includes(decision.action)) throw new ApiDataError()
  const data = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/review-decisions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(decision),
  })
  if (!isReviewDecision(data) || data.evaluationId !== evaluationId || data.requestId !== decision.requestId) {
    throw new ApiDataError()
  }
  return data
}

// AG-040 / AGROP-48: expediente por lote y pieza (lectura autenticada).
export type PieceHistorySummary = {
  lotCode: string
  pieceCode: string
  pieceId: number | null
  identitySource: 'registered' | 'legacy_inferred'
  attemptCount: number
  captureCount: number
  automaticAssessmentCount: number
  reviewEventCount: number
  latestEvaluationId: string | null
  latestStatus: string | null
}

export type PieceHistoryList = {
  lotCode: string
  product: FruitProduct
  pieceCount: number
  attemptCount: number
  captureCount: number
  pieces: PieceHistorySummary[]
}

export type PieceHistoryAttempt = {
  id: string
  attemptNumber: number
  createdAt: string
  status: string
  product: FruitProduct
  weightGrams: number | null
  weightPreGrams: number | null
  weightPostGrams: number | null
  deviceId: string | null
  calibrationReference: string | null
  declaredModelVersion: string | null
  declaredRulesVersion: string | null
  originalVisualCategory: string | null
  failureReason: string | null
  captures: Array<{
    id: string; view: string; createdAt: string; imageUrl: string
    imageSha256: string | null; hashConflict: boolean
  }>
  automaticAssessments: Array<{
    assessmentId: number; imageId: string; imageSha256: string
    createdAt: string; modelVersion: string; rulesVersion: string
    inferenceSize: number; threshold: number; confidence: number | null
    candidateCount: number; outcome: string; reason: string
    detections: unknown
  }>
  reviews: Array<{
    id: string; createdAt: string; type: string; actorId: string
    reason: string; previousValue: string | null; updatedValue: string | null
    action: string | null; imageId: string | null; imageSha256: string | null
    requestId: string | null
  }>
  dataQualityNotes: string[]
}

export type PieceHistoryDetail = {
  lotCode: string
  piece: PieceHistorySummary
  attempts: PieceHistoryAttempt[]
  identityWarning: string | null
}

function ag040IsRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function ag040IsCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function ag040IsOptionalText(value: unknown): boolean {
  return value === null || typeof value === 'string'
}

function ag040Summary(value: unknown, lot: string): value is PieceHistorySummary {
  if (!ag040IsRecord(value)) return false
  return value.lotCode === lot
    && typeof value.pieceCode === 'string' && value.pieceCode.length > 0
    && (value.pieceId === null || ag040IsCount(value.pieceId))
    && (value.identitySource === 'registered' || value.identitySource === 'legacy_inferred')
    && ag040IsCount(value.attemptCount) && ag040IsCount(value.captureCount)
    && ag040IsCount(value.reviewEventCount) && ag040IsCount(value.automaticAssessmentCount)
    && ag040IsOptionalText(value.latestEvaluationId) && ag040IsOptionalText(value.latestStatus)
}

export async function listPieceHistories(lotCode: string): Promise<PieceHistoryList> {
  const lot = lotCode.trim()
  if (!lot || lot.length > 32) throw new ApiDataError()
  const body = await request(`/api/piece-history?lot=${encodeURIComponent(lot)}`)
  if (!ag040IsRecord(body) || typeof body.lotCode !== 'string'
      || !['mango', 'tomate'].includes(String(body.product))
      || !ag040IsCount(body.pieceCount) || !ag040IsCount(body.attemptCount)
      || !ag040IsCount(body.captureCount) || !Array.isArray(body.pieces)
      || !body.pieces.every(value => ag040Summary(value, body.lotCode as string))) {
    throw new ApiDataError()
  }
  const payload = body as PieceHistoryList
  if (!validatePieceAggregates(payload.pieces, payload)) throw new ApiDataError()
  return payload
}

function ag040ValidateAttempt(value: unknown): value is PieceHistoryAttempt {
  if (!ag040IsRecord(value) || typeof value.id !== 'string' || !/^E-\d{1,9}$/.test(value.id)
      || !ag040IsCount(value.attemptNumber) || typeof value.createdAt !== 'string'
      || typeof value.status !== 'string' || !['mango', 'tomate'].includes(String(value.product))
      || !Array.isArray(value.captures) || !Array.isArray(value.automaticAssessments)
      || !Array.isArray(value.reviews) || !Array.isArray(value.dataQualityNotes)) return false
  if (!value.dataQualityNotes.every((item: unknown) => typeof item === 'string')) return false
  if (!value.captures.every((img: unknown) => ag040IsRecord(img)
      && typeof img.id === 'string' && /^I-\d{1,9}$/.test(img.id)
      && typeof img.view === 'string' && typeof img.imageUrl === 'string'
      && typeof img.createdAt === 'string'
      && ag040IsOptionalText(img.imageSha256) && typeof img.hashConflict === 'boolean')) return false
  if (!value.automaticAssessments.every((item: unknown) => ag040IsRecord(item)
      && ag040IsCount(item.assessmentId) && typeof item.imageId === 'string'
      && typeof item.modelVersion === 'string' && typeof item.rulesVersion === 'string'
      && typeof item.createdAt === 'string' && typeof item.reason === 'string'
      && typeof item.outcome === 'string')) return false
  return value.reviews.every((event: unknown) => ag040IsRecord(event)
      && typeof event.id === 'string' && typeof event.actorId === 'string'
      && typeof event.createdAt === 'string' && typeof event.reason === 'string'
      && ag040IsOptionalText(event.previousValue) && ag040IsOptionalText(event.updatedValue)
      && ag040IsOptionalText(event.action))
}

export async function getPieceHistory(lotCode: string, pieceCode: string): Promise<PieceHistoryDetail> {
  const lot = lotCode.trim()
  const piece = pieceCode.trim()
  if (!lot || lot.length > 32 || !piece || piece.length > 64) throw new ApiDataError()
  const body = await request(`/api/piece-history/${encodeURIComponent(lot)}/${encodeURIComponent(piece)}`)
  if (!ag040IsRecord(body) || typeof body.lotCode !== 'string'
      || !ag040Summary(body.piece, body.lotCode)
      || body.piece.pieceCode !== piece
      || !Array.isArray(body.attempts)
      || body.attempts.length !== body.piece.attemptCount
      || !body.attempts.every(ag040ValidateAttempt)
      || !ag040IsOptionalText(body.identityWarning)) throw new ApiDataError()
  return body as PieceHistoryDetail
}

/** AG-040 / AGROP-48: informe de solo lectura, con los mismos encabezados JWT. */
export async function getLotTraceabilityReport(lotCode: string): Promise<LotTraceabilityReport> {
  const lot = lotCode.trim()
  if (!lot || lot.length > 32) throw new ApiDataError()
  const body = await request(`/api/piece-history/report?lot=${encodeURIComponent(lot)}`, undefined, 30000)
  if (!ag040IsRecord(body) || typeof body.lotCode !== 'string'
      || body.lotCode.toLowerCase() !== lot.toLowerCase()
      || !validateLotTraceabilityReport(body, body.lotCode)) throw new ApiDataError()
  return body as LotTraceabilityReport
}

/** AG-054 I03: proyecciones en cm del tablero multimarcas, nunca dimensiones físicas acreditadas. */
export type BoardEstimate = {
  id: number
  evaluationId: string
  imageId: string
  geometryId: number
  imageSha256: string
  modelVersion: string
  rulesVersion: string
  boardVersion: 'ag054-board-a3-v1' | 'ag054-board-a4-v1'
  status: 'reference_plane_estimate' | 'needs_review'
  reason: string
  markerIds: number[]
  markerCornersPx: Record<string, Array<[number, number]>>
  rmsReprojectionMm: number | null
  measurements: null | {
    widthCm: number
    heightCm: number
    majorAxisCm: number
    minorAxisCm: number
    projectedAreaCm2: number
    projectedPerimeterCm: number
  }
  unit: 'cm_reference_plane'
  physicalDimensionsValidated: false
  fruitHeightCorrected: false
  cameraIntrinsicsCalibrated: false
  classificationE0E1E2Produced: false
  createdAt: string
}

function isBoardEstimate(value: unknown): value is BoardEstimate {
  if (!object(value) || !Number.isSafeInteger(value.id) || !Number.isSafeInteger(value.geometryId)
    || typeof value.evaluationId !== 'string' || !EVALUATION_ID_PATTERN.test(value.evaluationId)
    || typeof value.imageId !== 'string' || !IMAGE_ID_PATTERN.test(value.imageId)
    || typeof value.imageSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.imageSha256)
    || typeof value.modelVersion !== 'string' || typeof value.rulesVersion !== 'string'
    || (value.boardVersion !== 'ag054-board-a3-v1' && value.boardVersion !== 'ag054-board-a4-v1')
    || (value.status !== 'reference_plane_estimate' && value.status !== 'needs_review')
    || typeof value.reason !== 'string' || !Array.isArray(value.markerIds)
    || !value.markerIds.every(n => Number.isInteger(n) && n >= 0 && n <= 3)
    || !object(value.markerCornersPx)
    || !Object.values(value.markerCornersPx).every(points => Array.isArray(points)
      && points.length === 4 && points.every(pt => Array.isArray(pt) && pt.length === 2
      && pt.every(n => typeof n === 'number' && Number.isFinite(n))))
    || !(value.rmsReprojectionMm === null || (typeof value.rmsReprojectionMm === 'number'
      && Number.isFinite(value.rmsReprojectionMm) && value.rmsReprojectionMm >= 0))
    || value.unit !== 'cm_reference_plane' || value.physicalDimensionsValidated !== false
    || value.fruitHeightCorrected !== false || value.cameraIntrinsicsCalibrated !== false
    || value.classificationE0E1E2Produced !== false || typeof value.createdAt !== 'string'
    || !Number.isFinite(Date.parse(value.createdAt))) return false
  if (value.status === 'needs_review') return value.measurements === null
    && value.rmsReprojectionMm === null && value.markerIds.length === 0
  if (!object(value.measurements) || value.markerIds.length < 3
    || value.rmsReprojectionMm === null) return false
  return ['widthCm', 'heightCm', 'majorAxisCm', 'minorAxisCm', 'projectedAreaCm2', 'projectedPerimeterCm']
    .every(k => typeof (value.measurements as Record<string, unknown>)[k] === 'number'
      && Number.isFinite((value.measurements as Record<string, number>)[k])
      && (value.measurements as Record<string, number>)[k] > 0)
}

export type DimensionalComparison = {
  id: number
  boardCalibrationId: number
  referenceMajorCm: number
  referenceMinorCm: number
  instrumentId: string
  comparison: {
    status: 'comparison_only'
    physicalDimensionsValidated: false
    major: { projectedCm: number; manualCm: number; signedErrorCm: number; absoluteErrorCm: number; relativeAbsoluteErrorPct: number }
    minor: { projectedCm: number; manualCm: number; signedErrorCm: number; absoluteErrorCm: number; relativeAbsoluteErrorPct: number }
  }
  physicalDimensionsValidated: false
  createdAt: string
}
function isDimensionalComparison(value: unknown): value is DimensionalComparison {
  if (!object(value) || !Number.isSafeInteger(value.id) || !Number.isSafeInteger(value.boardCalibrationId)
    || typeof value.referenceMajorCm !== 'number' || !Number.isFinite(value.referenceMajorCm)
    || typeof value.referenceMinorCm !== 'number' || !Number.isFinite(value.referenceMinorCm)
    || value.referenceMinorCm <= 0 || value.referenceMajorCm < value.referenceMinorCm
    || typeof value.instrumentId !== 'string' || value.instrumentId.length < 2
    || value.physicalDimensionsValidated !== false || typeof value.createdAt !== 'string'
    || !Number.isFinite(Date.parse(value.createdAt)) || !object(value.comparison)
    || value.comparison.status !== 'comparison_only'
    || value.comparison.physicalDimensionsValidated !== false) return false
  for (const axis of ['major', 'minor']) {
    const entry = value.comparison[axis]
    if (!object(entry) || !['projectedCm','manualCm','signedErrorCm','absoluteErrorCm','relativeAbsoluteErrorPct']
      .every(k => typeof entry[k] === 'number' && Number.isFinite(entry[k]))) return false
  }
  return true
}

export async function listBoardEstimates(evaluationId: string, imageId: string): Promise<BoardEstimate[]> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)) throw new ApiDataError()
  const items = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/board/${encodeURIComponent(imageId)}`)
  if (!Array.isArray(items) || !items.every(isBoardEstimate)
    || !items.every(v => v.evaluationId === evaluationId && v.imageId === imageId)) throw new ApiDataError()
  return items
}

export async function createBoardEstimate(evaluationId: string, imageId: string, input: {
  boardVersion: 'ag054-board-a3-v1' | 'ag054-board-a4-v1'
  markerAtPlatformLevel: boolean
  independentSupport: boolean
  printedDimensionsVerified: boolean
  fixedCamera: boolean
}): Promise<BoardEstimate> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)
    || (input.boardVersion !== 'ag054-board-a3-v1' && input.boardVersion !== 'ag054-board-a4-v1')
    || !input.markerAtPlatformLevel || !input.independentSupport
    || !input.printedDimensionsVerified || !input.fixedCamera) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/board/${encodeURIComponent(imageId)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }, 45000)
  if (!isBoardEstimate(value) || value.evaluationId !== evaluationId || value.imageId !== imageId) throw new ApiDataError()
  return value
}

export async function listDimensionalComparisons(evaluationId: string, imageId: string): Promise<DimensionalComparison[]> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)) throw new ApiDataError()
  const items = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/board/${encodeURIComponent(imageId)}/comparisons`)
  if (!Array.isArray(items) || !items.every(isDimensionalComparison)) throw new ApiDataError()
  return items
}

export async function createDimensionalComparison(evaluationId: string, imageId: string, input: {
  boardCalibrationId?: number
  referenceMajorCm: number; referenceMinorCm: number; instrumentId: string
}): Promise<DimensionalComparison> {
  if (!validEvaluationId(evaluationId) || !IMAGE_ID_PATTERN.test(imageId)
    || (input.boardCalibrationId !== undefined && (!Number.isSafeInteger(input.boardCalibrationId) || input.boardCalibrationId < 1))
    || !Number.isFinite(input.referenceMajorCm) || !Number.isFinite(input.referenceMinorCm)
    || input.referenceMinorCm < 0.1 || input.referenceMinorCm > input.referenceMajorCm
    || input.referenceMajorCm > 60 || input.instrumentId.trim().length < 2) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/board/${encodeURIComponent(imageId)}/comparisons`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }, 15000)
  if (!isDimensionalComparison(value)) throw new ApiDataError()
  return value
}

// AG-055: lectura de propuestas experimentales sin modificar clasificación humana.
export type QualityModelStatus = {
  evaluationId: string
  product: FruitProduct
  modelAvailable: boolean
  modelSha256: string | null
  stage: string
  reason: string
  humanReviewRequired: boolean
  automaticallyFinalized: false
}

export type ExploratoryStatus = {
  evaluationId: string; experimental: true
  models: { task: string; labels: string[]; modelVersion: string; modelSha256: string }[]
  reason: string
}

export type QualityReviewEvent = {
  eventId: string; imageId?: string; grade: string; reviewer: string | null; reviewedAt: string | null
  evidence: string | null; rubricVersion: string | null; supersedesEventId: string | null; accreditationVerified: false
  annotationPurpose?: string; importedAt?: string
}
export type QualityReviewQueue = {
  evaluationId: string; accreditationVerified: false
  images: { imageId: string; imageUrl: string; imageSha256: string; status: 'pending' | 'reviewed' | 'declared_pending_metadata'; history: QualityReviewEvent[] }[]
}
export async function getQualityReviewQueue(evaluationId: string): Promise<QualityReviewQueue> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/reviews`)
  if (!object(v) || v.evaluationId !== evaluationId || v.accreditationVerified !== false || !Array.isArray(v.images)
    || !v.images.every(i => object(i) && typeof i.imageId === 'string' && typeof i.imageUrl === 'string'
      && typeof i.imageSha256 === 'string' && ['pending','reviewed','declared_pending_metadata'].includes(String(i.status)) && Array.isArray(i.history)
      && i.history.every(e => object(e) && typeof e.eventId === 'string'
        && ['reviewer','reviewedAt','evidence','rubricVersion'].every(k => typeof e[k] === 'string'
          || (e.annotationPurpose === 'human_label_declaration_import' && e[k] === null))
        && ['E0','E1','E2','no_evaluable'].includes(String(e.grade)) && e.accreditationVerified === false))) throw new ApiDataError()
  return v as QualityReviewQueue
}

export async function getPilotQualityStatus(evaluationId: string): Promise<ExploratoryStatus> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/pilot/status`)
  if (!object(v) || v.evaluationId !== evaluationId || v.experimental !== true || v.independentTestMetrics !== null
    || typeof v.reason !== 'string' || !Array.isArray(v.models) || !v.models.every(m => object(m)
      && m.task === 'PILOT117' && JSON.stringify(m.labels) === JSON.stringify(['E0','E1','E2'])
      && typeof m.modelVersion === 'string' && typeof m.modelSha256 === 'string')) throw new ApiDataError()
  return v as ExploratoryStatus
}
export async function analyzePilotQuality(evaluationId: string): Promise<QualityProposal[]> {
  if (!validEvaluationId(evaluationId) || !isOperatorAuthenticated()) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/pilot/analyze`, { method: 'POST' })
  if (!Array.isArray(v) || !v.every(r => isQualityProposal(r) && r.evaluationId === evaluationId
    && r.status === 'experimental_e0e1e2_pilot' && r.proposedGrade === null)) throw new ApiDataError()
  return v
}
export async function getV2QualityStatus(evaluationId: string): Promise<ExploratoryStatus> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/v2/status`)
  if (!object(v) || v.evaluationId !== evaluationId || v.experimental !== true || v.independentTestMetrics !== null
    || typeof v.reason !== 'string' || !Array.isArray(v.models) || !v.models.every(m => object(m)
      && m.task === 'PILOT117_V2' && JSON.stringify(m.labels) === JSON.stringify(['E0','E1','E2'])
      && typeof m.modelVersion === 'string' && typeof m.modelSha256 === 'string')) throw new ApiDataError()
  return v as ExploratoryStatus
}
export async function analyzeV2Quality(evaluationId: string): Promise<QualityProposal[]> {
  if (!validEvaluationId(evaluationId) || !isOperatorAuthenticated()) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/v2/analyze`, { method: 'POST' })
  if (!Array.isArray(v) || !v.every(r => isQualityProposal(r) && r.evaluationId === evaluationId
    && r.status === 'experimental_e0e1e2_v2' && r.proposedGrade === null)) throw new ApiDataError()
  return v
}
export async function saveQualityHumanReview(evaluationId: string, body: {
  imageId: string; predictionId: number; grade: string; roi: number[]; roiConfirmed: boolean
  humanConfirmed: boolean; rubricVersion: string; evidence: string; expectedLastEventId: string | null
}): Promise<void> {
  if (!validEvaluationId(evaluationId) || !isOperatorAuthenticated()) throw new ApiDataError()
  const v = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/reviews`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!object(v) || typeof v.eventId !== 'string' || v.accreditationVerified !== false) throw new ApiDataError()
}

export async function getExploratoryQualityStatus(evaluationId: string): Promise<ExploratoryStatus> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/exploratory/status`)
  if (!object(value) || value.evaluationId !== evaluationId || value.experimental !== true
      || typeof value.reason !== 'string' || !Array.isArray(value.models)
      || !value.models.every(m => object(m) && ['TQ','SEN','FG'].includes(String(m.task))
        && Array.isArray(m.labels) && m.labels.every((x: unknown) => typeof x === 'string' && !['E0','E1','E2'].includes(x))
        && typeof m.modelVersion === 'string' && typeof m.modelSha256 === 'string')) throw new ApiDataError()
  return value as ExploratoryStatus
}

export async function analyzeExploratoryQuality(evaluationId: string): Promise<QualityProposal[]> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/exploratory/analyze`, { method: 'POST' })
  if (!Array.isArray(value) || !value.every(v => isQualityProposal(v)
      && v.evaluationId === evaluationId && v.proposedGrade === null
      && v.status === 'exploratory_original_labels')) throw new ApiDataError()
  return value
}

export type QualityProposal = {
  id: number
  evaluationId: string
  product: FruitProduct
  status: string
  reason: string
  proposedGrade: 'E0' | 'E1' | 'E2' | null
  modelVersion: string
  modelSha256: string
  sourceFingerprint: string
  details: unknown
  humanReviewRequired: true
  automaticallyFinalized: false
  createdAt: string
}

function isQualityModelStatus(value: unknown): value is QualityModelStatus {
  return object(value) && typeof value.evaluationId === 'string'
    && (value.product === 'mango' || value.product === 'tomate')
    && typeof value.modelAvailable === 'boolean'
    && (value.modelSha256 === null || typeof value.modelSha256 === 'string')
    && typeof value.stage === 'string' && typeof value.reason === 'string'
    && value.humanReviewRequired === true && value.automaticallyFinalized === false
}

function isQualityProposal(value: unknown): value is QualityProposal {
  return object(value) && typeof value.id === 'number'
    && typeof value.evaluationId === 'string'
    && (value.product === 'mango' || value.product === 'tomate')
    && typeof value.status === 'string' && typeof value.reason === 'string'
    && (value.proposedGrade === null || ['E0','E1','E2'].includes(String(value.proposedGrade)))
    && typeof value.modelVersion === 'string' && typeof value.modelSha256 === 'string'
    && typeof value.sourceFingerprint === 'string'
    && value.humanReviewRequired === true && value.automaticallyFinalized === false
    && typeof value.createdAt === 'string'
}

export async function getQualityModelStatus(evaluationId: string): Promise<QualityModelStatus> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/status`)
  if (!isQualityModelStatus(value) || value.evaluationId !== evaluationId) throw new ApiDataError()
  return value
}

export async function getQualityProposals(evaluationId: string): Promise<QualityProposal[]> {
  if (!validEvaluationId(evaluationId)) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/proposals`)
  if (!Array.isArray(value) || !value.every(isQualityProposal)
    || !value.every(x => x.evaluationId === evaluationId)) throw new ApiDataError()
  return value
}

export async function analyzeQualityProposal(evaluationId: string): Promise<QualityProposal | {
  evaluationId: string; product: FruitProduct; status: string; reason: string
  proposedGrade: null; humanReviewRequired: true; automaticallyFinalized: false
}> {
  if (!validEvaluationId(evaluationId) || !isOperatorAuthenticated()) throw new ApiDataError()
  const value = await request(`/api/evaluations/${encodeURIComponent(evaluationId)}/vision/quality/analyze`,
    { method: 'POST' }, 120000)
  if (isQualityProposal(value) && value.evaluationId === evaluationId) return value
  if (!object(value) || value.evaluationId !== evaluationId
    || (value.product !== 'mango' && value.product !== 'tomate')
    || (value.status !== 'blocked_no_eligible_model' && value.status !== 'needs_review')
    || value.proposedGrade !== null || value.humanReviewRequired !== true
    || value.automaticallyFinalized !== false || typeof value.reason !== 'string') throw new ApiDataError()
  return value as {
    evaluationId: string; product: FruitProduct; status: string; reason: string
    proposedGrade: null; humanReviewRequired: true; automaticallyFinalized: false
  }
}
