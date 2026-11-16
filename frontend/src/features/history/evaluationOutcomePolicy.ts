/** AgroScan I01: lectura operativa. Nunca convierte estados de registro en precisión acreditada. */
import type { EvaluationStatus } from './historyService.ts'
import { summarizeV2Proposals } from '../quality/automaticQuality.ts'

type Ledger = { currentValue: string | null; decisions: readonly unknown[] }
type QualityStatus = { modelAvailable: boolean }
type Proposal = { status: string; proposedGrade: string | null; details?: unknown }

export type OutcomeInputs = {
  status: EvaluationStatus
  ledger: Ledger | null
  qualityStatus: QualityStatus | null
  proposals: readonly Proposal[] | null
  evidenceIds?: readonly string[]
}

export type OutcomeSummary = {
  process: string
  human: string
  humanNote: string
  ai: string
  aiNote: string
  dimensions: string
}

const VISUAL = new Set(['E0', 'E1', 'E2'])

export function summarizeEvaluation({ status, ledger, qualityStatus, proposals, evidenceIds }: OutcomeInputs): OutcomeSummary {
  const process: Record<EvaluationStatus, string> = {
    processing: 'Registro en proceso',
    pending_review: 'Revisión pendiente',
    completed: 'Proceso cerrado',
    error: 'Proceso con incidencia',
    cancelled: 'Evaluación anulada',
  }

  let human = 'Sin dictamen AG-038 por fotografía'
  let humanNote = ledger === null
    ? 'No se pudo consultar la bitácora de revisión.'
    : 'Consulte la trazabilidad si existen revisiones anteriores.'
  if (ledger && ledger.decisions.length > 0) {
    const value = ledger.currentValue
    human = VISUAL.has(value ?? '') ? value! : value === 'no_evaluable'
      ? 'No evaluable' : 'Resultado histórico sin categoría E0/E1/E2'
    humanNote = status === 'pending_review'
      ? 'Decisión humana parcial: todavía pueden existir fotografías por revisar.'
      : 'Dictamen humano registrado; no es una predicción automática.'
  }

  let ai = 'Análisis IA no consultado'
  let aiNote = 'No se pudo verificar el estado del clasificador.'
  if (proposals !== null) {
    // Únicamente una propuesta experimental explícita puede aparecer como sugerencia.
    const v2Rows = proposals.filter(item => item.status === 'experimental_e0e1e2_v2')
    const v2Grade = summarizeV2Proposals(v2Rows, evidenceIds)
    const suggested = [...proposals].reverse().find((item) =>
      item.status === 'experimental_proposal' && VISUAL.has(item.proposedGrade ?? ''))
    if (v2Grade) {
      ai = `Sugerencia V2 ${v2Grade}`
      aiNote = 'Vistas concordantes en un modelo experimental. No es dictamen ni precisión externa acreditada.'
    } else if (v2Rows.length > 0) {
      ai = 'Análisis V2 requiere revisión'
      aiNote = 'No todas las fotografías obtuvieron un grado concordante y evaluable.'
    } else if (suggested) {
      ai = `Sugerencia ${suggested.proposedGrade}`
      aiNote = 'Resultado experimental guardado, sin confirmación ni precisión externa acreditada.'
    } else if (qualityStatus?.modelAvailable === false) {
      ai = 'Modelo de calidad no instalado'
      aiNote = 'La detección de la fruta no equivale a clasificación E0/E1/E2.'
    } else if (qualityStatus?.modelAvailable === true) {
      ai = 'Sin propuesta automática'
      aiNote = 'Modelo disponible, pero no hay propuesta evaluable registrada.'
    } else {
      ai = 'Resultado automático sin verificar'
      aiNote = 'No se pudo consultar el estado del modelo.'
    }
  }

  return {
    process: process[status], human, humanNote, ai, aiNote,
    dimensions: 'Sin dimensiones físicas validadas',
  }
}
