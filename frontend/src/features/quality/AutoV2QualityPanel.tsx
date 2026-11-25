import { useEffect, useState } from 'react'
import {
  analyzeV2Quality, getQualityProposals, getV2QualityStatus, isOperatorAuthenticated,
} from '../../services/agroscanApi.ts'
import { analyzeStoredV2, type V2Evidence, type V2Preview } from './autoV2Preview.ts'
import { v2Reason } from './v2Policy.ts'

type Props = { evaluationId: string; evidence: readonly V2Evidence[] }

export function ClassificationResult({ preview }: { preview: V2Preview }) {
  return <>
    <p><strong>{preview.status === 'suggested' && preview.grade ? `Resultado preliminar: ${preview.grade}` :
      preview.status === 'no_model' ? 'Clasificación no disponible' : 'Revisión requerida'}</strong></p>
    <p>{preview.message}</p>
    {preview.views.length > 0 && <ul>{preview.views.map((view, index) => <li key={view.id}>
      Vista {index + 1} ({view.id}): {view.grade ?? 'no evaluable'}
      {!view.evaluable && view.reason && <> · {v2Reason(view.reason)}</>}
    </li>)}</ul>}
  </>
}

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
      console.warn('Quality analysis failed', cause)
      if (active) setError(cause instanceof Error ? cause.message : 'No se pudo completar la clasificación. Las fotografías permanecen guardadas. Reintenta o solicita ayuda al administrador.')
    })
    return () => { active = false }
  }, [evaluationId, evidence, attempt, permitted])

  return <section className="capture__v2-preview" aria-label="Clasificación preliminar" aria-live="polite">
    <h4>Clasificación</h4>
    {!permitted ? <p>Se requiere una sesión de operador para ejecutar la clasificación.</p> :
      error ? <>
        <p role="alert">No se completó el análisis automático: {error}</p>
        <button className="action-button action-button--secondary" type="button"
          onClick={() => { setPreview(null); setError(null); setAttempt(n => n + 1) }}>Reintentar clasificación</button>
      </> : !preview ? <p role="status">Analizando automáticamente las fotografías guardadas…</p>
        : <ClassificationResult preview={preview} />}
    {preview?.status === 'no_model' && !error && <button type="button" className="action-button action-button--secondary"
      onClick={() => { setPreview(null); setAttempt(n => n + 1) }}>Reintentar clasificación</button>}
    <p className="capture__hint">Resultado pendiente de revisión humana; su precisión no está validada para uso comercial.
      El peso inicial y final siguen siendo obligatorios para confirmar la adquisición.</p>
  </section>
}
