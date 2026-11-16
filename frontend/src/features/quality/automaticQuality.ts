/** AgroScan I02: análisis automático experimental al confirmar la adquisición.
 * No crea dictámenes humanos, ni convierte las puntuaciones en probabilidades.
 */
import { v2Views } from './v2Policy.ts'
import type { QualityProposal } from '../../services/agroscanApi.ts'

export type QualityGrade = 'E0' | 'E1' | 'E2'
export type AutoQualityStatus = 'suggested' | 'needs_review' | 'no_model' | 'error'
export type AutomaticQualityResult = {
  status: AutoQualityStatus
  grade: QualityGrade | null
  source: 'v2' | 'quality_i01' | null
  message: string
}

type EvaluationEvidence = { id: string; view: string }
type EvaluationRecord = { id: string; status: string; evidence: EvaluationEvidence[] }
type LegacyAnalysis = QualityProposal | {
  status: string; proposedGrade: null; reason: string
}

/** Dependencias inyectadas: el servicio se prueba sin red ni escribir en SQLite. */
export type AutomaticQualityGateway = {
  getEvaluationById: (id: string) => Promise<EvaluationRecord | null>
  getV2QualityStatus: (id: string) => Promise<{ models: readonly unknown[] }>
  analyzeV2Quality: (id: string) => Promise<QualityProposal[]>
  getQualityModelStatus: (id: string) => Promise<{ modelAvailable: boolean }>
  analyzeQualityProposal: (id: string) => Promise<LegacyAnalysis>
}

const GRADES = new Set(['E0', 'E1', 'E2'])
const unavailable = (message: string): AutomaticQualityResult => ({
  status: 'needs_review', grade: null, source: null, message,
})

/** Nunca propone un grado si falta una vista, una predicción es inválida,
 * o las propuestas de las fotografías no concuerdan. */
export function summarizeV2Proposals(
  proposals: readonly { status: string; details?: unknown }[],
  evidenceIds?: readonly string[],
): QualityGrade | null {
  const last = [...proposals].reverse().find(row => row.status === 'experimental_e0e1e2_v2')
  if (!last || !last.details || typeof last.details !== 'object' || !('perView' in last.details)
    || !Array.isArray(last.details.perView)) return null
  const originals = last.details.perView as unknown[]
  const valid = v2Views(last.details)
  if (originals.length < 2 || valid.length !== originals.length) return null
  if (new Set(valid.map(x => x.imageId)).size !== valid.length) return null
  if (evidenceIds && (evidenceIds.length !== valid.length
      || new Set(evidenceIds).size !== evidenceIds.length
      || valid.some(x => !evidenceIds.includes(x.imageId)))) return null
  if (valid.some(x => !x.evaluable || !GRADES.has(x.label ?? ''))) return null
  if (valid.some(x => x.label !== valid[0].label)) return null
  return valid[0].label as QualityGrade
}

/** Tras confirmar con FastAPI, analiza V2 preferentemente; si no existe,
 * intenta el modelo AG-055 I01. V1 queda en modo diagnóstico manual. */
export async function runAutomaticQuality(
  evaluationId: string, gateway: AutomaticQualityGateway,
): Promise<AutomaticQualityResult> {
  try {
    const record = await gateway.getEvaluationById(evaluationId)
    if (!record || record.id !== evaluationId) {
      return { status: 'error', grade: null, source: null, message: 'No se pudo consultar la evaluación confirmada.' }
    }
    if (record.status !== 'pending_review' && record.status !== 'completed') {
      return unavailable('Confirma el peso y las fotografías antes de ejecutar la clasificación automática.')
    }
    const evidence = record.evidence
    if (!Array.isArray(evidence) || evidence.length < 2
      || new Set(evidence.map(x => x.id)).size !== evidence.length
      || new Set(evidence.map(x => x.view)).size < 2) {
      return unavailable('Se requieren al menos dos fotografías con identificadores y vistas diferentes.')
    }
    const v2 = await gateway.getV2QualityStatus(evaluationId)
    if (v2.models.length > 0) {
      const predictions = await gateway.analyzeV2Quality(evaluationId)
      const grade = summarizeV2Proposals(predictions, evidence.map(x => x.id))
      return grade
        ? { status: 'suggested', grade, source: 'v2', message: 'Propuesta experimental V2; revisión humana obligatoria. No implica precisión validada.' }
        : { status: 'needs_review', grade: null, source: 'v2', message: 'V2 analizó las imágenes, pero no obtuvo un grado concordante y evaluable. Revisar fotografías.' }
    }
    const legacy = await gateway.getQualityModelStatus(evaluationId)
    if (!legacy.modelAvailable) {
      return { status: 'no_model', grade: null, source: null, message: 'No hay un modelo E0/E1/E2 habilitado para esta estación. La evaluación y las fotos permanecen guardadas.' }
    }
    const result = await gateway.analyzeQualityProposal(evaluationId)
    if (result.status === 'experimental_proposal' && GRADES.has(result.proposedGrade ?? '')) {
      return { status: 'suggested', grade: result.proposedGrade as QualityGrade, source: 'quality_i01', message: 'Propuesta experimental sobre dos vistas; revisión humana obligatoria.' }
    }
    return { status: 'needs_review', grade: null, source: 'quality_i01', message: 'El modelo no obtuvo una propuesta concordante. Revisar las fotografías.' }
  } catch {
    return { status: 'error', grade: null, source: null, message: 'No pudo completarse el análisis automático. El registro permanece guardado; verifica el modelo y reintenta desde los detalles.' }
  }
}
