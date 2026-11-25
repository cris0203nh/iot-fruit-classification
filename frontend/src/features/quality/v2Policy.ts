export type V2View = {
  imageId: string; roi: number[]; label: string | null; confidence: number | null
  evaluable: boolean; reason: string | null; modelVersion: string
  scoresUncalibrated: Record<string, number>; sampleUse: string
  segmentation?: { partialCoverage?: boolean }
}

export function v2Reason(reason: string | null | undefined): string {
  const messages: Record<string, string> = {
    fruit_not_detected: 'No se detectó una fruta.',
    ambiguous_fruit_detection: 'Se detectaron varias frutas; no hay una identidad única.',
    incompatible_or_uncertain_detection: 'La fruta detectada no coincide con el producto o la detección es incierta.',
    detector_mask_unavailable: 'El detector no obtuvo una máscara de fruta válida.',
    segmentation_failed: 'Falló la segmentación de la fruta.',
    fruit_not_separated: 'La segmentación no logró separar la fruta del fondo.',
    insufficient_fruit_area_in_frame: 'La fruta ocupa menos área de la que admite el modelo actual; requiere revisión o una nueva versión del modelo.',
    excessive_or_irregular_foreground: 'El área o la forma de la máscara no cumple las condiciones del modelo.',
    insufficient_chromatic_fruit: 'La región no contiene suficiente información de color.',
    insufficient_fruit_interior: 'No hay suficiente superficie interior de fruta para extraer características.',
    partial_fruit_coverage: 'La fruta aparece cortada o toca el límite de segmentación.',
    unsupported_image_size: 'Las dimensiones de la fotografía están fuera de las condiciones admitidas.',
    image_decode_failed: 'No se pudo decodificar la fotografía.',
    incompatible_features: 'Las características visuales son incompatibles con el modelo.',
  }
  return messages[reason ?? ''] ?? 'Evidencia insuficiente; motivo técnico: ' + (reason || 'no disponible') + '.'
}

export function v2ReviewMessage(views: readonly V2View[]): string {
  if (views.length < 2) return 'El análisis de las fotografías está incompleto. Se requiere revisión humana.'
  const failed = views.filter(view => !view.evaluable)
  if (failed.length) return failed.map(view => `${view.imageId}: ${v2Reason(view.reason)}`).join(' ') + ' No hay un grado consolidado; revisión humana obligatoria.'
  if (new Set(views.map(view => view.label)).size < 2) return 'No se pudo verificar una propuesta completa para las fotografías actuales. Se requiere revisión humana.'
  return 'Las vistas discrepan en sus propuestas E0/E1/E2. Se requiere revisión humana.'
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
