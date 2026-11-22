import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { EvaluationDetail } from './historyService.ts'
import { formatWeight } from './historyService.ts'
import {
  getQualityModelStatus, getQualityProposals, getReviewDecisions, getV2QualityStatus,
  type QualityProposal, type ReviewDecisionLedger,
} from '../../services/agroscanApi'
import { summarizeEvaluation } from './evaluationOutcomePolicy.ts'
import {
  EvaluationEvidenceSnapshot,
  type DimensionCardRow,
} from './EvaluationEvidenceSnapshot.tsx'
import './EvaluationOutcomePanel.css'

type Sources = {
  loading: boolean
  ledger: ReviewDecisionLedger | null
  qualityStatus: { modelAvailable: boolean } | null
  proposals: QualityProposal[] | null
}

export function EvaluationOutcomePanel({ evaluation }: { evaluation: EvaluationDetail }) {
  const [sources, setSources] = useState<Sources>({
    loading: true, ledger: null, qualityStatus: null, proposals: null,
  })

  const [dimensions, setDimensions] = useState<
    readonly DimensionCardRow[]
  >([])

  useEffect(() => {
    let active = true
    void Promise.allSettled([
      getReviewDecisions(evaluation.id),
      getQualityModelStatus(evaluation.id),
      getQualityProposals(evaluation.id),
      getV2QualityStatus(evaluation.id),
    ] as const).then(([human, quality, proposals, current]) => {
      if (!active) return
      setSources({
        loading: false,
        ledger: human.status === 'fulfilled' ? human.value : null,
        qualityStatus: (quality.status === 'fulfilled' && quality.value.modelAvailable)
          || (current.status === 'fulfilled' && current.value.models.length > 0)
          ? { modelAvailable: true }
          : quality.status === 'fulfilled' && current.status === 'fulfilled'
            ? { modelAvailable: false } : null,
        proposals: proposals.status === 'fulfilled' ? proposals.value : null,
      })
    })
    return () => { active = false }
  }, [evaluation.id])

  const summary = summarizeEvaluation({
    status: evaluation.status,
    ledger: sources.ledger,
    qualityStatus: sources.qualityStatus,
    proposals: sources.proposals,
    evidenceIds: evaluation.evidence.map(item => item.id),
  })

  return (
    <section className="agroscan-outcome" aria-labelledby="agroscan-outcome-title">
      <div className="agroscan-outcome__heading">
        <h3 id="agroscan-outcome-title">Resultado de la evaluación</h3>
        <span className="agroscan-outcome__state">{summary.process}</span>
      </div>
      {sources.loading ? <p role="status">Consultando resultados…</p> : (
        <div className="agroscan-outcome__grid">
          <div className="agroscan-outcome__metric">
            <span>Clasificación registrada por revisor</span>
            <strong>{summary.human}</strong>
            <small>{summary.humanNote}</small>
          </div>
          <div className="agroscan-outcome__metric">
            <span>Calidad sugerida por IA</span>
            <strong>{summary.ai}</strong>
            <small>{summary.aiNote}</small>
          </div>
          <div className="agroscan-outcome__metric">
            <span>Peso registrado</span>
            <strong>{formatWeight(evaluation.weightGrams)}</strong>
            <small>Lectura asociada a esta evaluación.</small>
          </div>
          <div className="agroscan-outcome__metric">
            <span>Dimensiones estimadas</span>

            {dimensions.length > 0 ? (
              dimensions.map(row => (
                <strong key={row.imageId}>
                  {row.view}: Largo ≈ {row.lengthCm.toFixed(2)} cm
                  {' · '}
                  Ancho ≈ {row.widthCm.toFixed(2)} cm
                </strong>
              ))
            ) : (
              <strong>Sin estimaciones en cm registradas</strong>
            )}

            <small>
              Estimaciones ópticas 2D mediante ArUco.
              La precisión física todavía no está validada.
            </small>
          </div>
        </div>
      )}
      {!sources.loading && (
        <EvaluationEvidenceSnapshot
          evaluationId={evaluation.id}
          evidence={evaluation.evidence}
          proposals={sources.proposals}
                    onDimensionsLoaded={setDimensions}
        />
      )}
      <div className="agroscan-outcome__actions">
        <Link to={`/trazabilidad/${encodeURIComponent(evaluation.id)}`}>Ver fotografías, registrar revisión y consultar trazabilidad</Link>
      </div>
    </section>
  )
}
