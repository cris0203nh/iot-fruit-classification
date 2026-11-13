import type { ExploratoryView } from './exploratoryPolicy'

export type PilotView = ExploratoryView & { sampleUse: string; independentPerformanceEvaluated: false }
export function pilotViews(details: unknown): PilotView[] {
  if (!details || typeof details !== 'object' || !('labelSpace' in details)
    || details.labelSpace !== 'pilot_declared_e0e1e2' || !('perView' in details) || !Array.isArray(details.perView)) return []
  return details.perView.filter((v: unknown): v is PilotView => {
    if (!v || typeof v !== 'object') return false
    const p = v as Record<string, unknown>
    return typeof p.imageId === 'string' && ['E0','E1','E2'].includes(String(p.label))
      && p.experimental === true && p.proposedGrade === null && p.confidenceCalibrated === false
      && p.independentPerformanceEvaluated === false && typeof p.sampleUse === 'string'
      && typeof p.confidence === 'number' && Number.isFinite(p.confidence) && p.confidence>=0 && p.confidence<=1
      && typeof p.modelVersion === 'string' && !!p.scoresUncalibrated && typeof p.scoresUncalibrated === 'object'
      && Object.entries(p.scoresUncalibrated).length === 3 && Object.entries(p.scoresUncalibrated).every(([k,s]) =>
        ['E0','E1','E2'].includes(k) && typeof s === 'number' && Number.isFinite(s) && s>=0 && s<=1)
  })
}
