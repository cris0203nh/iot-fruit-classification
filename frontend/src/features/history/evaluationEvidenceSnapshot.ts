/** I04: lectura histórica de propuestas V2 y aproximaciones ArUco, sin efectos ni escrituras. */
import type { BoardEstimate, QualityProposal } from '../../services/agroscanApi.ts'
import { summarizeCaptureV2, type V2Preview } from '../quality/autoV2Preview.ts'
import { recoverApproxA4, type Result } from '../geometry/approxA4Flow.ts'

export type EvidenceI04 = { id: string; view: string }
export type EvidenceSnapshotI04 = {
  quality: V2Preview | null
  dimensions: Result[]
}

/**
 * Solo admite snapshots completos, de la misma evaluación y de todas las fotos actuales.
 * Nunca interpreta una etiqueta de YOLOE o una medición como dictamen humano.
 */
export function summarizeEvidenceI04(
  evaluationId: string,
  evidence: readonly EvidenceI04[],
  proposals: readonly QualityProposal[],
  boardGroups: readonly BoardEstimate[][],
): EvidenceSnapshotI04 {
  const ids = evidence.map(item => item.id)
  const views = evidence.map(item => item.view)
  const distinct = evidence.length >= 2 && new Set(ids).size === ids.length &&
    new Set(views).size === views.length
  const dimensions = recoverApproxA4(evaluationId, evidence, boardGroups)
  if (!distinct) return { quality: null, dimensions }

  const v2 = proposals.filter(row =>
    row.evaluationId === evaluationId &&
    row.status === 'experimental_e0e1e2_v2' &&
    row.proposedGrade === null && row.humanReviewRequired === true &&
    row.automaticallyFinalized === false &&
    typeof row.modelSha256 === 'string' && row.modelSha256.length > 0,
  ).sort((a, b) => b.id - a.id)

  for (const row of v2) {
    const result = summarizeCaptureV2([row], evidence, row.modelSha256)
    if (result) return { quality: result, dimensions }
  }
  return { quality: null, dimensions }
}
