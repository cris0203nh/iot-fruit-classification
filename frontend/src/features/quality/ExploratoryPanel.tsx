import { useEffect, useState } from 'react'
import {
  analyzeExploratoryQuality, getExploratoryQualityStatus, getQualityProposals,
  isOperatorAuthenticated, type QualityProposal,
} from '../../services/agroscanApi'
import { exploratoryViews, reviewReasonText } from './exploratoryPolicy'
import { HumanReviewPanel } from './HumanReviewPanel'

export function ExploratoryResults({ rows }: { rows: QualityProposal[] }) {
  return <ul>{rows.filter(r => r.status === 'exploratory_original_labels').map(row => <li key={row.id}>
    {exploratoryViews(row.details).map(view => <p key={view.imageId}>
      <strong>{view.label}</strong> · {view.imageId} · Puntuación: {(view.confidence * 100).toFixed(1)}%
      {' · Confianza no calibrada'} · {view.modelVersion}
      {view.scoresUncalibrated && <span className="quality-scores"> · Scores: {Object.entries(view.scoresUncalibrated).map(([label,score]) => `${label}: ${score.toFixed(4)}`).join(' · ')}</span>}
      {view.uncertainty && <span> · Margen: {view.uncertainty.margin.toFixed(4)} · {view.uncertainty.priority === 'priority' ? 'Revisión prioritaria' : view.uncertainty.priority === 'diagnostic_only' ? 'Solo diagnóstico experimental' : 'Revisión humana requerida'}
        {' · '}{view.uncertainty.reasons.map(r => reviewReasonText[r] ?? 'Revisión humana requerida').join(' · ')}</span>}
    </p>)}
    <small>Resultado exploratorio separado. No asigna E0/E1/E2. Revisión humana obligatoria.</small>
  </li>)}</ul>
}

export function ExploratoryPanel({ evaluationId }: { evaluationId: string }) {
  const [selected, setSelected] = useState<{ predictionId: number; view: ReturnType<typeof exploratoryViews>[number] } | null>(null)
  const [tasks, setTasks] = useState<string[]>([])
  const [rows, setRows] = useState<QualityProposal[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    Promise.all([getExploratoryQualityStatus(evaluationId), getQualityProposals(evaluationId)])
      .then(([status, results]) => { if (active) { setTasks(status.models.map(m => m.task)); setRows(results) } })
      .catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : 'No se pudo consultar el modelo') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluationId])
  async function analyze() {
    if (busy) return
    setBusy(true); setError('')
    try { setRows(await analyzeExploratoryQuality(evaluationId)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Evidencia insuficiente') }
    finally { setBusy(false) }
  }
  return <section aria-label="Resultados exploratorios de etiquetas originales">
    <h4>Experimentos con etiquetas originales</h4>
    <p>Fresh/Rotten, enfermedades y niveles de frescura conservan sus categorías originales.
      No acreditan calidad de mango Kent ni grados E0/E1/E2.</p>
    <p><small>ROI automática sin verificación humana. Independencia física y generalización no acreditadas.</small></p>
    {loading ? <p role="status">Consultando experimentos…</p> : <p role="status">
      {tasks.length ? `Modelos experimentales: ${tasks.join(', ')}` : 'Sin modelo exploratorio instalado para este producto.'}
    </p>}
    {tasks.length > 0 && isOperatorAuthenticated() && <button type="button" className="action-button action-button--secondary"
      disabled={busy} onClick={() => void analyze()}>{busy ? 'Procesando…' : 'Explorar fotografías persistidas'}</button>}
    <ExploratoryResults rows={rows} />
    {isOperatorAuthenticated() && rows.filter(r => r.status === 'exploratory_original_labels').map(row =>
      exploratoryViews(row.details).map(view => <button key={`${row.id}-${view.imageId}`} type="button"
        className="action-button action-button--secondary" onClick={() => setSelected({ predictionId: row.id, view })}>
        Revisar {view.imageId} · inferencia {row.id}</button>))}
    {selected && <HumanReviewPanel key={`${selected.predictionId}-${selected.view.imageId}`} evaluationId={evaluationId} {...selected} />}
    {error && <p role="alert">{error}</p>}
  </section>
}
