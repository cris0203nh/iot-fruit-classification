import { useEffect, useState } from 'react'
import { analyzeV2Quality, getV2QualityStatus, getQualityProposals, isOperatorAuthenticated, type QualityProposal } from '../../services/agroscanApi'
import { HumanReviewPanel } from './HumanReviewPanel'
import { v2Views, type V2View } from './v2Policy'

export function V2QualityPanel({ evaluationId }: { evaluationId: string }) {
  const [available,setAvailable] = useState(false)
  const [rows,setRows] = useState<QualityProposal[]>([])
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [selected,setSelected] = useState<{ predictionId: number; view: V2View } | null>(null)
  useEffect(() => {
    let active = true
    Promise.all([getV2QualityStatus(evaluationId),getQualityProposals(evaluationId)])
      .then(([status,data]) => { if (active) { setAvailable(status.models.length>0); setRows(data) } })
      .catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : 'No se pudo consultar V2') })
    return () => { active = false }
  },[evaluationId])
  async function analyze() {
    if (busy) return
    setBusy(true);setError('')
    try { const results = await analyzeV2Quality(evaluationId); setRows(previous => [...previous.filter(r => !results.some(s => s.id === r.id)),...results]) }
    catch (e) { setError(e instanceof Error ? e.message : 'No se pudo ejecutar V2') }
    finally { setBusy(false) }
  }
  return <section aria-label="V2 E0 E1 E2 experimental">
    <h4>V2 E0/E1/E2 experimental</h4>
    <p>Región de fruta con segmentación heurística. Si falla: no evaluable. Sin validación externa; Kent no acreditado. Revisión humana obligatoria.</p>
    {!available && <p>Sin modelo V2 instalado para este producto.</p>}
    {available && isOperatorAuthenticated() && <button type="button" className="action-button action-button--secondary" disabled={busy} onClick={() => void analyze()}>
      {busy ? 'Procesando V2…' : 'Analizar V2 E0/E1/E2'}</button>}
    <ul>{rows.filter(r => r.status === 'experimental_e0e1e2_v2').map(row => <li key={row.id}>
      {v2Views(row.details).map(view => <div key={view.imageId}>
        <p><strong>{view.evaluable ? `Propuesta ${view.label} · NO confirmada` : 'No evaluable · requiere revisión'}</strong> · {view.imageId} · {view.modelVersion}</p>
        {view.evaluable ? <p>Puntuación {((view.confidence ?? 0)*100).toFixed(1)}%. Confianza no calibrada. Scores: {Object.entries(view.scoresUncalibrated).map(([g,s]) => `${g}: ${s.toFixed(4)}`).join(' · ')}</p> : <p>Motivo técnico: {view.reason}</p>}
        <p>{view.sampleUse === 'training_photo' ? 'Fotografía de entrenamiento: solo diagnóstico interno.' : 'Independencia física sin verificar.'}</p>
        {view.segmentation?.partialCoverage && <p>Cobertura parcial: revisar el encuadre y la superficie visible.</p>}
        {isOperatorAuthenticated() && <button type="button" className="action-button action-button--secondary" onClick={() => setSelected({ predictionId: row.id, view })}>Revisar V2 {view.imageId}</button>}
      </div>)}
    </li>)}</ul>
    {selected && <HumanReviewPanel key={`${selected.predictionId}-${selected.view.imageId}`} evaluationId={evaluationId} {...selected} />}
    {error && <p role="alert">{error}</p>}
  </section>
}
