export type V2View = {
  imageId: string; roi: number[]; label: string | null; confidence: number | null
  evaluable: boolean; reason: string | null; modelVersion: string
  scoresUncalibrated: Record<string, number>; sampleUse: string
  segmentation?: { partialCoverage?: boolean }
}

export function v2Views(details: unknown): V2View[] {
  if (!details || typeof details !== 'object' || !('labelSpace' in details)
    || details.labelSpace !== 'pilot_declared_e0e1e2_v2' || !('perView' in details) || !Array.isArray(details.perView)) return []
  return details.perView.filter((value: unknown): value is V2View => {
    if (!value || typeof value !== 'object') return false
    const v = value as Record<string, unknown>
    if (typeof v.imageId !== 'string' || typeof v.modelVersion !== 'string' || v.experimental !== true
      || v.proposedGrade !== null || v.confidenceCalibrated !== false || v.independentPerformanceEvaluated !== false
      || typeof v.sampleUse !== 'string' || !Array.isArray(v.roi) || v.roi.length !== 4
      || !v.roi.every(n => typeof n === 'number' && Number.isFinite(n))
      || !v.scoresUncalibrated || typeof v.scoresUncalibrated !== 'object') return false
    const scores = Object.entries(v.scoresUncalibrated)
    if (v.evaluable === false) return v.label === null && v.confidence === null && scores.length === 0
      && v.status === 'no_evaluable' && typeof v.reason === 'string'
    return v.evaluable === true && ['E0','E1','E2'].includes(String(v.label)) && v.reason === null
      && typeof v.confidence === 'number' && Number.isFinite(v.confidence) && v.confidence >= 0 && v.confidence <= 1
      && scores.length === 3 && scores.every(([k,n]) => ['E0','E1','E2'].includes(k)
        && typeof n === 'number' && Number.isFinite(n) && n>=0 && n<=1)
  })
}
