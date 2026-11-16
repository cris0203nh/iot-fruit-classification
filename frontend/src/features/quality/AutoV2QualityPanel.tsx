import { useEffect, useState } from 'react'
import {
  analyzeV2Quality, getQualityProposals, getV2QualityStatus, isOperatorAuthenticated,
} from '../../services/agroscanApi.ts'
import { analyzeStoredV2, type V2Evidence, type V2Preview } from './autoV2Preview.ts'

type Props = { evaluationId: string; evidence: readonly V2Evidence[] }

/** Análisis preliminar automático al haber dos fotos persistidas.
 * No representa confirmación de adquisición ni clasificación oficial. */
export function AutoV2QualityPanel({ evaluationId, evidence }: Props) {
  const [preview, setPreview] = useState<V2Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const permitted = isOperatorAuthenticated()

  useEffect(() => {
    if (!permitted || evidence.length < 2) return
    let active = true
    void analyzeStoredV2(evaluationId, evidence, {
      getV2QualityStatus, getQualityProposals, analyzeV2Quality,
    }).then(result => {
      if (active) { setPreview(result); setError(null) }
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : 'Falló la inferencia V2.')
    })
    return () => { active = false }
  }, [evaluationId, evidence, attempt, permitted])

  return <section className="capture__v2-preview" aria-label="Clasificación automática preliminar V2" aria-live="polite">
    <h4>Calidad externa · análisis V2 preliminar</h4>
    {!permitted ? <p>Se requiere sesión de operador para ejecutar V2.</p> :
      error ? <>
        <p role="alert">No se completó el análisis automático: {error}</p>
        <button className="action-button action-button--secondary" type="button"
          onClick={() => { setPreview(null); setError(null); setAttempt(n => n + 1) }}>Reintentar análisis V2</button>
      </> : !preview ? <p role="status">Analizando automáticamente las fotografías guardadas…</p>
        : <>
          <p><strong>{preview.grade ? `Sugerencia experimental: ${preview.grade}` :
            preview.status === 'no_model' ? 'Modelo V2 no disponible' : 'Revisión necesaria'}</strong></p>
          <p>{preview.message}</p>
          {preview.views.length > 0 && <ul>{preview.views.map((view, index) => <li key={view.id}>
            Vista {index + 1} ({view.id}): {view.grade ?? 'no evaluable'}
          </li>)}</ul>}
          {preview.modelVersion && <small>Modelo: {preview.modelVersion}</small>}
        </>}
    <p className="capture__hint">No es una clasificación confirmada ni una probabilidad de acierto.
      El peso inicial y final siguen siendo obligatorios para confirmar la adquisición.</p>
  </section>
}
