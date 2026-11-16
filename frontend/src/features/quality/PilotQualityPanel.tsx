import { useEffect, useState } from 'react'
import { analyzePilotQuality, getPilotQualityStatus, getQualityProposals, isOperatorAuthenticated, type QualityProposal } from '../../services/agroscanApi'
import { HumanReviewPanel } from './HumanReviewPanel'
import { pilotViews, type PilotView } from './pilotPolicy'

export function PilotQualityPanel({ evaluationId }: { evaluationId: string }) {
  const [available,setAvailable] = useState(false)
  const [loading,setLoading] = useState(true)
  const [rows,setRows] = useState<QualityProposal[]>([])
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [selected,setSelected] = useState<{ predictionId: number; view: PilotView } | null>(null)
  useEffect(() => {
    let active = true
    Promise.all([getPilotQualityStatus(evaluationId),getQualityProposals(evaluationId)])
      .then(([status,data]) => { if (active) { setAvailable(status.models.length>0); setRows(data) } })
      .catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : 'No se pudo consultar el piloto') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  },[evaluationId])
  async function analyze() {
    if (busy) return
    setBusy(true); setError('')
    try { const results = await analyzePilotQuality(evaluationId); setRows(previous => [...previous.filter(p => !results.some(r => r.id === p.id)),...results]) }
    catch (e) { setError(e instanceof Error ? e.message : 'No se pudo ejecutar el piloto') }
    finally { setBusy(false) }
  }
  return <section aria-label="Clasificador de referencia">
    <h4>Clasificador de referencia</h4>
    <p>Rendimiento independiente: <strong>no evaluado</strong>. Kent no acreditado. Las categorías son resultados preliminares, sin decisión oficial automática.</p>
    <p>Este clasificador utiliza la imagen completa, incluido el fondo. Confianza no calibrada; los scores no son probabilidades confiables.</p>
    {loading ? <p role="status">Consultando clasificador…</p> : !available && <p role="status">Clasificador de referencia no disponible para este producto.</p>}
    {available && isOperatorAuthenticated() && <button type="button" className="action-button action-button--secondary" disabled={busy} onClick={() => void analyze()}>
      {busy ? 'Clasificando…' : 'Consultar clasificador de referencia'}</button>}
    <ul>{rows.filter(r => r.status === 'experimental_e0e1e2_pilot').map(row => <li key={row.id}>
      {pilotViews(row.details).map(view => <div key={view.imageId}>
        <p><strong>Propuesta {view.label} · NO confirmada</strong> · {view.imageId} · Puntuación {(view.confidence*100).toFixed(1)}% · {view.modelVersion}</p>
        <p>Confianza no calibrada. Scores: {Object.entries(view.scoresUncalibrated ?? {}).map(([c,s]) => `${c}: ${s.toFixed(4)}`).join(' · ')}</p>
        <p>{view.sampleUse === 'training_photo' ? 'Fotografía utilizada para entrenar: solo diagnóstico, no evaluación independiente.' : 'Fotografía no presente por SHA en entrenamiento; independencia física sin verificar.'}</p>
        {isOperatorAuthenticated() && <button type="button" className="action-button action-button--secondary" onClick={() => setSelected({ predictionId: row.id, view })}>Revisar {view.imageId}</button>}
      </div>)}
    </li>)}</ul>
    {selected && <HumanReviewPanel key={`${selected.predictionId}-${selected.view.imageId}`} evaluationId={evaluationId} {...selected} />}
    {error && <p role="alert">{error}</p>}
  </section>
}
