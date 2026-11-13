import { useEffect, useRef, useState } from 'react'
import { ExploratoryPanel } from './ExploratoryPanel'
import { PilotQualityPanel } from './PilotQualityPanel'
import { V2QualityPanel } from './V2QualityPanel'
import {
  getQualityModelStatus, getQualityProposals, analyzeQualityProposal,
  isOperatorAuthenticated, type QualityProposal, type QualityModelStatus,
} from '../../services/agroscanApi'

/** AG-055 I01: propuestas exploratorias. No confirma un grado ni cierra evaluación. */
export function QualityProposalPanel({ evaluationId, autoAnalyze = false }: { evaluationId: string; autoAnalyze?: boolean }) {
  return <QualityProposalContent key={evaluationId} evaluationId={evaluationId} autoAnalyze={autoAnalyze} />
}

function QualityProposalContent({ evaluationId, autoAnalyze }: { evaluationId: string; autoAnalyze: boolean }) {
  const autoTriggered = useRef(false)
  const [status, setStatus] = useState<QualityModelStatus | null>(null)
  const [rows, setRows] = useState<QualityProposal[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([getQualityModelStatus(evaluationId), getQualityProposals(evaluationId)])
      .then(([model, results]) => {
        if (active) { setStatus(model); setRows(results); setError(null) }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'No fue posible consultar los resultados de calidad.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluationId])

  async function analyze() {
    if (running || !status?.modelAvailable || !isOperatorAuthenticated()) return
    setRunning(true); setError(null)
    try {
      const result = await analyzeQualityProposal(evaluationId)
      if (result.status === 'blocked_no_eligible_model') {
        setError('No existe un clasificador experimental elegible instalado para este producto.')
      } else if ('id' in result) {
        setRows(previous => previous.some(row => row.id === result.id) ? previous : [...previous, result])
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No fue posible procesar las fotografías.')
    } finally { setRunning(false) }
  }

  useEffect(() => {
    if (!autoAnalyze || loading || !status?.modelAvailable || rows.length > 0
        || !isOperatorAuthenticated() || autoTriggered.current) return
    autoTriggered.current = true
    void analyze()
    // Iniciar solo una vez por evaluación; no repetir por renderizaciones.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAnalyze, loading, status?.modelAvailable, rows.length])

  return (
    <section className="ag055-panel" aria-label="AG-055 evaluación de calidad externa experimental"
      style={{ border: '1px solid #a7aea8', borderRadius: 10, padding: 16, marginTop: 14 }}>
      <h3>AG-055 · Calidad externa asistida por IA</h3>
      <p>YOLOE identifica la fruta. La clasificación E0/E1/E2 requiere un modelo independiente,
        datos etiquetados por humanos y validación por producto.</p>
      {loading && <p role="status">Consultando modelo y propuestas…</p>}
      {!loading && status && (
        <p role="status"><strong>{status.modelAvailable ? 'Modelo experimental instalado' : 'Sin modelo E0/E1/E2 elegible'}</strong>
          {' · '}{status.reason}</p>
      )}
      {status?.modelAvailable && isOperatorAuthenticated() && (
        <button type="button" className="action-button action-button--secondary"
          disabled={running} onClick={() => void analyze()}>
          {running ? 'Analizando vistas…' : 'Analizar calidad de las dos vistas'}
        </button>
      )}
      {rows.length > 0 && <ul>
        {rows.filter(row => !['exploratory_original_labels','experimental_e0e1e2_pilot'].includes(row.status)).map(row => <li key={row.id}>
          <strong>{row.proposedGrade ? `Propuesta ${row.proposedGrade} (NO confirmada)` : 'Sin grado sugerido'}</strong>
          {' · '}{row.reason} · {row.modelVersion}
          <p>Estado: {row.status}. Revisión humana obligatoria. No modifica la categoría oficial.</p>
        </li>)}
      </ul>}
      {error && <p role="alert">{error}</p>}
      <PilotQualityPanel key={`pilot-${evaluationId}`} evaluationId={evaluationId} />
      <V2QualityPanel key={`v2-${evaluationId}`} evaluationId={evaluationId} />
      <ExploratoryPanel key={evaluationId} evaluationId={evaluationId} />
      <p><small>Sin precisión acreditada ni decisión automática. Para entrenamiento se necesitan
        clases E0/E1/E2 representadas y fotografías independientes por producto.</small></p>
    </section>
  )
}
