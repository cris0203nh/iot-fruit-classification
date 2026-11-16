/** I03: mediacion A4 multimarcas sobre el plano de referencia.
 * Nunca convierte la proyeccion en dimension fisica 3D acreditada. */
import type { BoardEstimate, FruitGeometryResult } from '../../services/agroscanApi.ts'

export const A4_BOARD_VERSION = 'ag054-board-a4-v1' as const
export const A4_MARKER_SIDE_MM = 30
/** La version cambia porque el reajuste validado debe poder reanalizar rechazos v2. */
export const A4_RULES_VERSION = 'ag054-board-plane-v3-a4-global-fit' as const
const A4_LEGACY_RULES_VERSION = 'ag054-board-plane-v2-a4' as const

export type A4Evidence = { id: string; view: string }
export type A4View = {
  imageId: string
  view: string
  status: 'pending' | 'projected' | 'needs_review' | 'error'
  reason: string | null
  measurement: BoardEstimate['measurements']
  markerIds: number[]
  modelVersion: string | null
}

export type A4Gateway = {
  listBoardEstimates: (evaluationId: string, imageId: string) => Promise<BoardEstimate[]>
  listFruitGeometries: (evaluationId: string) => Promise<FruitGeometryResult[]>
  analyzeFruitGeometry: (evaluationId: string, imageId: string) => Promise<FruitGeometryResult>
  createBoardEstimate: (evaluationId: string, imageId: string, input: {
    boardVersion: typeof A4_BOARD_VERSION
    markerAtPlatformLevel: boolean
    independentSupport: boolean
    printedDimensionsVerified: boolean
    fixedCamera: boolean
  }) => Promise<BoardEstimate>
}

function validEvidence(evidence: readonly A4Evidence[]) {
  return evidence.length >= 2 && evidence.every(item => /^I-\d{6,9}$/.test(item.id) &&
    /^vista-\d+$/.test(item.view)) && new Set(evidence.map(item => item.id)).size === evidence.length &&
    new Set(evidence.map(item => item.view)).size === evidence.length
}

export function pendingA4(item: A4Evidence): A4View {
  return { imageId: item.id, view: item.view, status: 'pending', reason: null,
    measurement: null, markerIds: [], modelVersion: null }
}

function rejected(item: A4Evidence, status: 'needs_review' | 'error', reason: string): A4View {
  return { ...pendingA4(item), status, reason }
}

/** Acepta solo un registro correspondiente a la vista A4 correcta y con restricciones persistidas. */
export function boardToA4(
  item: A4Evidence, evaluationId: string, rows: readonly BoardEstimate[],
): A4View | null {
  const matches = rows.filter(row => row.evaluationId === evaluationId && row.imageId === item.id &&
    row.boardVersion === A4_BOARD_VERSION && row.status !== 'pixel_scale_estimate' &&
    (row.rulesVersion === A4_RULES_VERSION ||
      (row.rulesVersion === A4_LEGACY_RULES_VERSION &&
        !(row.status === 'needs_review' && row.reason === 'board_inconsistent_markers'))) &&
    row.physicalDimensionsValidated === false &&
    row.fruitHeightCorrected === false && row.cameraIntrinsicsCalibrated === false &&
    row.classificationE0E1E2Produced === false && row.unit === 'cm_reference_plane')
  const latest = matches.at(-1)
  if (!latest) return null
  if (latest.status === 'needs_review') {
    return rejected(item, 'needs_review', latest.reason)
  }
  if (latest.status !== 'reference_plane_estimate' || !latest.measurements ||
      latest.markerIds.length < 3 || ![latest.measurements.majorAxisCm, latest.measurements.minorAxisCm,
      latest.measurements.widthCm, latest.measurements.heightCm].every(n => Number.isFinite(n) && n > 0)) {
    return rejected(item, 'needs_review', 'board_projection_invalid')
  }
  return { imageId: item.id, view: item.view, status: 'projected', reason: null,
    measurement: latest.measurements, markerIds: latest.markerIds, modelVersion: latest.modelVersion }
}

/** Solo GET: muestra estimaciones previamente persistidas; jamas simula una medida. */
export async function readStoredA4(
  evaluationId: string, evidence: readonly A4Evidence[], gateway: A4Gateway,
): Promise<A4View[]> {
  if (!validEvidence(evidence)) return evidence.map(pendingA4)
  return Promise.all(evidence.map(async item => {
    try {
      const rows = await gateway.listBoardEstimates(evaluationId, item.id)
      return boardToA4(item, evaluationId, rows) ?? pendingA4(item)
    } catch (cause) {
      return rejected(item, 'error', cause instanceof Error ? cause.message : 'No se pudieron consultar las medidas.')
    }
  }))
}

/** Operacion manual unica por evaluacion, con verificacion explicita del montaje.
 * Usa el YOLOE guardado, ejecuta geometria faltante y el backend A4 existente.
 * Cada imagen tiene resultado independiente; no promedia vistas ni inventa profundidad. */
export async function measureA4(
  evaluationId: string, evidence: readonly A4Evidence[], verifiedMount: boolean, gateway: A4Gateway,
): Promise<A4View[]> {
  if (!validEvidence(evidence)) throw new Error('Se requieren dos vistas diferentes, guardadas en la misma evaluación.')
  if (!verifiedMount) throw new Error('Debes verificar físicamente el montaje A4 antes de medir.')

  // No publicar falsos éxitos por error de lectura del inventario de geometrías.
  const geometries = await gateway.listFruitGeometries(evaluationId)
  const output: A4View[] = []
  for (const item of evidence) {
    try {
      const existing = boardToA4(item, evaluationId,
        await gateway.listBoardEstimates(evaluationId, item.id))
      if (existing) { output.push(existing); continue }

      let geometry = geometries.filter(row => row.imageId === item.id && row.evaluationId === evaluationId).at(-1)
      if (!geometry) geometry = await gateway.analyzeFruitGeometry(evaluationId, item.id)
      if (geometry.imageId !== item.id || geometry.evaluationId !== evaluationId) {
        output.push(rejected(item, 'error', 'La geometría retornada pertenece a otra fotografía.'))
        continue
      }
      if (geometry.status !== 'measured' || !geometry.measurements) {
        output.push(rejected(item, 'needs_review', geometry.reason || 'No se pudo detectar una única fruta con YOLOE.'))
        continue
      }
      const board = await gateway.createBoardEstimate(evaluationId, item.id, {
        boardVersion: A4_BOARD_VERSION,
        markerAtPlatformLevel: true,
        independentSupport: true,
        printedDimensionsVerified: true,
        fixedCamera: true,
      })
      output.push(boardToA4(item, evaluationId, [board]) ??
        rejected(item, 'error', 'FastAPI devolvió una medición con identidad o versión incompatibles.'))
    } catch (cause) {
      output.push(rejected(item, 'error', cause instanceof Error ? cause.message : 'Fallo de medición A4.'))
    }
  }
  return output
}
