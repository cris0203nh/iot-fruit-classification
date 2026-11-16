import type { BoardEstimate } from '../../services/agroscanApi.ts'
const VERSION = 'ag054-board-plane-v4-a4-marker-pixels'
export type Evidence = { id: string; view: string }
export type Result = { imageId: string; view: string; status: 'pending' | 'estimated' | 'needs_review' | 'error';
  reason?: string; record?: BoardEstimate }

export function recoverApproxA4(evaluationId: string, evidence: readonly Evidence[],
    groups: readonly BoardEstimate[][]): Result[] {
  return evidence.map((item, index) => {
    const rows = (groups[index] ?? []).filter(row => row.evaluationId === evaluationId &&
      row.imageId === item.id && row.boardVersion === 'ag054-board-a4-v1' &&
      row.rulesVersion === VERSION && row.physicalDimensionsValidated === false &&
      row.fruitHeightCorrected === false && row.cameraIntrinsicsCalibrated === false &&
      row.classificationE0E1E2Produced === false)
    const record = rows.at(-1)
    if (!record) return { imageId: item.id, view: item.view, status: 'pending' }
    if (record.status === 'pixel_scale_estimate' && record.measurements &&
        record.markerIds.length >= 3 && record.unit === 'cm_reference_plane' &&
        [record.measurements.majorAxisCm,record.measurements.minorAxisCm].every(x => Number.isFinite(x) && x > 0)) {
      return { imageId: item.id, view: item.view, status: 'estimated', record }
    }
    return { imageId: item.id, view: item.view, status: 'needs_review', reason: record.reason }
  })
}
