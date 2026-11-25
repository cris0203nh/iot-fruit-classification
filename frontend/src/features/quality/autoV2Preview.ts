/** Vista preliminar V2 durante captura: nunca confirma una clasificación ni sustituye el pesaje. */
import { v2Views, v2ReviewMessage } from './v2Policy.ts'
import type { QualityProposal } from '../../services/agroscanApi.ts'

export type V2Evidence = { id: string; view: string }
export type V2Preview = {
  status: 'suggested' | 'needs_review' | 'no_model'
  grade: 'E0' | 'E1' | 'E2' | null
  modelVersion: string | null
  views: { id: string; grade: 'E0' | 'E1' | 'E2' | null; evaluable: boolean; reason?: string | null }[]
  message: string
}

type V2Gateway = {
  getV2QualityStatus: (id: string) => Promise<{ models: { task: string; modelSha256: string; modelVersion: string; inferencePolicyVersion?: string }[] }>
  getQualityProposals: (id: string) => Promise<QualityProposal[]>
  analyzeV2Quality: (id: string) => Promise<QualityProposal[]>
}

const needsReview = (message: string): V2Preview => ({
  status: 'needs_review', grade: null, modelVersion: null, views: [], message,
})
const sameIds = (actual: string[], expected: string[]) =>
  actual.length === expected.length && new Set(actual).size === actual.length &&
  expected.every(id => actual.includes(id))

/** Descarta propuestas de otro modelo, evaluación o conjunto de fotografías.
 * Comprueba todas las vistas, incluidas las que no son evaluables. */
export function summarizeCaptureV2(
  rows: readonly QualityProposal[], evidence: readonly V2Evidence[], modelSha: string, inferencePolicyVersion?: string,
): V2Preview | null {
  const ids = evidence.map(x => x.id)
  const selected = [...rows].reverse().find(row => {
    if (row.status !== 'experimental_e0e1e2_v2' || row.modelSha256 !== modelSha ||
        row.automaticallyFinalized !== false || row.proposedGrade !== null ||
        !row.details || typeof row.details !== 'object' || !('sources' in row.details)) return false
    if (inferencePolicyVersion && (!('inferencePolicyVersion' in row.details) || row.details.inferencePolicyVersion !== inferencePolicyVersion)) return false
    const sources = row.details.sources
    return Array.isArray(sources) && sameIds(sources.map((x: unknown) =>
      x && typeof x === 'object' && 'imageId' in x ? String(x.imageId) : ''), ids)
  })
  if (!selected) return null

  const original = selected.details && typeof selected.details === 'object' && 'perView' in selected.details
    ? selected.details.perView : null
  const parsed = v2Views(selected.details)
  if (!Array.isArray(original) || parsed.length !== original.length ||
      !sameIds(parsed.map(x => x.imageId), ids)) {
    return needsReview('No se pudo verificar el análisis de todas las fotografías. Revisa la evaluación.')
  }
  const views = evidence.map(item => {
    const match = parsed.find(x => x.imageId === item.id)!
    return { id: item.id, evaluable: match.evaluable, reason: match.reason,
      grade: match.evaluable ? match.label as 'E0' | 'E1' | 'E2' : null }
  })
  const labels = views.map(x => x.grade)
  const agreed = labels.every(label => label !== null && label === labels[0])
  return agreed
    ? { status: 'suggested', grade: labels[0], views, modelVersion: selected.modelVersion,
        message: 'Las vistas coinciden. Resultado preliminar; revisión humana obligatoria.' }
    : { status: 'needs_review', grade: null, views, modelVersion: selected.modelVersion,
        message: v2ReviewMessage(parsed) }
}

/** Usa predicciones existentes idempotentes; si faltan, solicita V2 a FastAPI.
 * No consulta ni escribe pesos y no cambia estados de la evaluación. */
export async function analyzeStoredV2(
  evaluationId: string, evidence: readonly V2Evidence[], gateway: V2Gateway,
): Promise<V2Preview> {
  const ids = evidence.map(x => x.id)
  if (ids.length < 2 || new Set(ids).size !== ids.length ||
      new Set(evidence.map(x => x.view)).size < 2) {
    return needsReview('Se necesitan dos fotografías guardadas con vistas distintas de la misma pieza.')
  }
  const models = (await gateway.getV2QualityStatus(evaluationId)).models
  const model = models.find(row => row.task === 'PILOT117_V2' && row.modelSha256)
  if (!model) return {
    status: 'no_model', grade: null, modelVersion: null, views: [],
    message: 'La clasificación no está habilitada para este producto. Las fotografías siguen guardadas; solicita ayuda al administrador.',
  }
  const previous = summarizeCaptureV2(await gateway.getQualityProposals(evaluationId), evidence, model.modelSha256, model.inferencePolicyVersion)
  if (previous) return previous
  const result = await gateway.analyzeV2Quality(evaluationId)
  return summarizeCaptureV2(result, evidence, model.modelSha256, model.inferencePolicyVersion) ??
    needsReview('No se obtuvo un análisis verificable para estas fotografías. Revisión requerida.')
}
