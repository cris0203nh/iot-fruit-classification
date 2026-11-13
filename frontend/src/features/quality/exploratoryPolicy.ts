export type ExploratoryView = {
  imageId: string; label: string; confidence: number; modelVersion: string
  experimental: true; proposedGrade: null; confidenceCalibrated: false
  roi?: number[]; scoresUncalibrated?: Record<string, number>
  uncertainty?: { margin: number; priority: string; reasons: string[]; thresholdSource: string }
}

export const reviewReasonText: Record<string, string> = {
  confidence_not_calibrated: 'Confianza no calibrada',
  ambiguous_class_margin: 'Margen entre categorías ambiguo',
  potential_rotten_prioritize_review: 'Tomate potencialmente Rotten: revisión prioritaria incluso si aparece Fresh',
  visible_disease_category_requires_review: 'Categoría de enfermedad que requiere valoración humana',
  no_defensible_validation_policy: 'No hay umbrales defendibles de validación; revisar la evidencia',
  fgrade_diagnostic_only_no_operational_decisions: 'FGrade solo diagnóstico experimental; no apto para decisiones operativas',
}

export function exploratoryViews(details: unknown): ExploratoryView[] {
  if (!details || typeof details !== 'object' || !('labelSpace' in details)
      || details.labelSpace !== 'original_source_labels' || !('perView' in details)
      || !Array.isArray(details.perView)) return []
  return details.perView.filter((x: unknown): x is ExploratoryView => {
    if (!x || typeof x !== 'object') return false
    const v = x as Record<string, unknown>
    if (v.scoresUncalibrated !== undefined && (!v.scoresUncalibrated || typeof v.scoresUncalibrated !== 'object'
      || !Object.entries(v.scoresUncalibrated).every(([k,n]) => !['E0','E1','E2'].includes(k)
        && typeof n === 'number' && Number.isFinite(n) && n>=0 && n<=1))) return false
    if (v.uncertainty !== undefined) {
      const u = v.uncertainty as Record<string, unknown> | null
      if (!u || typeof u !== 'object' || typeof u.margin !== 'number' || !Number.isFinite(u.margin)
        || u.margin<0 || u.margin>1 || !['normal','priority','diagnostic_only'].includes(String(u.priority))
        || !Array.isArray(u.reasons) || !u.reasons.every(r => typeof r === 'string') || typeof u.thresholdSource !== 'string') return false
    }
    return typeof v.imageId === 'string' && typeof v.label === 'string'
      && !['E0', 'E1', 'E2'].includes(v.label) && typeof v.modelVersion === 'string'
      && typeof v.confidence === 'number' && Number.isFinite(v.confidence)
      && v.confidence >= 0 && v.confidence <= 1 && v.experimental === true
      && v.proposedGrade === null && v.confidenceCalibrated === false
  })
}
