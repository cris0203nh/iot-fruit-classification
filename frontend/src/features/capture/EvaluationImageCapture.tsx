import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import {
  ApiConnectionError, ApiResponseError, getEvaluationById, resolveEvidenceUrl,
  uploadEvaluationPhoto, type CapturedEvidence,
} from '../../services/agroscanApi'
import { captureFileError } from './captureValidation'
import { nextCaptureView } from './captureViews'
import './EvaluationImageCapture.css'

type Props = { evaluationId: string }
type Saved = CapturedEvidence & { url: string }
type LoadedState = 'loading' | 'ready' | 'closed' | 'failed'

function asSaved(evidence: CapturedEvidence[]): Saved[] {
  return evidence.map((item) => {
    const url = resolveEvidenceUrl(item.imageUrl)
    if (!url) throw new Error('El servidor devolvió una ruta de imagen no válida.')
    return { ...item, url }
  })
}

/** AGROP-27: varias vistas, siempre ligadas al mismo identificador de evaluación. */
export function EvaluationImageCapture({ evaluationId }: Props) {
  const cameraInput = useRef<HTMLInputElement>(null)
  const galleryInput = useRef<HTMLInputElement>(null)
  const sending = useRef(false)
  const [candidate, setCandidate] = useState<{ file: File; url: string } | null>(null)
  const [saved, setSaved] = useState<Saved[]>([])
  const [loadState, setLoadState] = useState<LoadedState>('loading')
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [rotationConfirmed, setRotationConfirmed] = useState(false)
  const nextView = nextCaptureView(saved.map((item) => item.view))
  const canCapture = loadState === 'ready' && !uploading
  const canSave = canCapture && (saved.length === 0 || rotationConfirmed)

  useEffect(() => {
    let active = true
    getEvaluationById(evaluationId).then(
      (detail) => {
        if (!active) return
        if (!detail) {
          setLoadState('failed')
          setError('No se encontró la evaluación. No es posible agregar fotografías.')
          return
        }
        try {
          setSaved(asSaved(detail.evidence))
          setLoadState(detail.status === 'processing' ? 'ready' : 'closed')
          setError(null)
        } catch (failure) {
          setLoadState('failed')
          setError(failure instanceof Error ? failure.message : 'Respuesta de imágenes no válida.')
        }
      },
      (failure: unknown) => {
        if (!active) return
        setLoadState('failed')
        setError(failure instanceof ApiConnectionError
          ? 'Sin conexión al consultar las vistas. Reintenta antes de enviar una imagen.'
          : failure instanceof ApiResponseError
            ? `No se pudieron consultar las vistas (HTTP ${failure.status}).`
            : 'No fue posible comprobar las imágenes guardadas.')
      },
    )
    return () => { active = false }
  }, [evaluationId, revision])

  useEffect(() => {
    return () => { if (candidate) URL.revokeObjectURL(candidate.url) }
  }, [candidate])

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = ''
    if (!file || !canCapture) return
    const validationError = captureFileError(file)
    setError(validationError)
    setCandidate(validationError ? null : { file, url: URL.createObjectURL(file) })
  }

  function discard() {
    if (!canCapture) return
    setCandidate(null)
    setError(null)
  }

  async function save() {
    if (!candidate || !canSave || sending.current) return
    sending.current = true
    setUploading(true)
    setError(null)
    try {
      const result = await uploadEvaluationPhoto(evaluationId, candidate.file, nextView)
      const [item] = asSaved([result])
      setSaved((previous) => [...previous, item])
      setRotationConfirmed(false)
      setCandidate(null)
    } catch (failure) {
      const message = failure instanceof ApiConnectionError
        ? 'No se pudo confirmar el envío. Comprueba el detalle o actualiza las vistas antes de reintentar para evitar duplicados.'
        : failure instanceof ApiResponseError
          ? `No se guardó la fotografía (HTTP ${failure.status}): ${failure.message}`
          : 'No se pudo confirmar el guardado. Consulta el detalle antes de reintentar.'
      setError(message)
      // Si el POST fue recibido pero la respuesta se perdió, no repetirlo a ciegas.
      setLoadState('failed')
    } finally {
      sending.current = false
      setUploading(false)
    }
  }

  return (
    <div className="capture" aria-label="Captura de vistas RGB">
      <p className="capture__reference">Evaluación actual: <strong>{evaluationId}</strong></p>
      <p className="capture__hint">Todas las fotografías deben corresponder a la misma fruta. Gira manualmente la pieza entre tomas, sin iniciar otra evaluación.</p>
      {loadState === 'loading' && <p role="status">Consultando vistas guardadas…</p>}
      {loadState === 'closed' && <p role="status">La evaluación ya no está en proceso. Las vistas se muestran solo para consulta.</p>}
      {loadState === 'failed' && (
        <button className="action-button action-button--secondary" type="button" disabled={uploading} onClick={() => { setCandidate(null); setRotationConfirmed(false); setLoadState('loading'); setRevision((value) => value + 1) }}>
          Verificar vistas guardadas
        </button>
      )}
      {saved.length > 0 && (
        <section aria-label="Vistas asociadas a esta evaluación">
          <p className="capture__hint">{saved.length} {saved.length === 1 ? 'vista guardada' : 'vistas guardadas'} en <strong>{evaluationId}</strong></p>
          <ul className="capture__gallery">
            {saved.map((item) => (
              <li key={item.id}>
                <img src={item.url} alt={`${item.view} de la evaluación ${evaluationId}`} loading="lazy" />
                <strong>{item.view}</strong>
                <span>{item.id}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {loadState === 'ready' && saved.length > 0 && !candidate && (
        <p className="capture__rotation" role="status">Para {nextView}, gira manualmente la misma fruta y comprueba que permanezca asociada a {evaluationId}.</p>
      )}
      {loadState === 'ready' && saved.length > 0 && (
        <label className="capture__rotation-check">
          <input type="checkbox" checked={rotationConfirmed} onChange={(event) => setRotationConfirmed(event.target.checked)} disabled={uploading} />
          Confirmo que giré manualmente la misma fruta para esta vista.
        </label>
      )}
      <input className="capture__input" ref={cameraInput} type="file" accept="image/jpeg,image/png" capture="environment" onChange={selectFile} aria-label="Tomar fotografía con cámara" disabled={!canCapture} />
      <input className="capture__input" ref={galleryInput} type="file" accept="image/jpeg,image/png" onChange={selectFile} aria-label="Seleccionar imagen de galería" disabled={!canCapture} />
      {candidate && (
        <div className="capture__result">
          <img src={candidate.url} alt={`Vista previa de ${nextView} antes del envío`} />
          <p>Vista previa: <strong>{candidate.file.name}</strong> · <strong>{nextView}</strong></p>
          <div className="capture__actions">
            <button className="action-button action-button--secondary" type="button" disabled={!canCapture} onClick={() => cameraInput.current?.click()}>Repetir toma</button>
            <button className="action-button action-button--secondary" type="button" disabled={!canCapture} onClick={discard}>Descartar</button>
            <button className="action-button action-button--primary" type="button" disabled={!canSave} onClick={save}>{uploading ? 'Enviando…' : `Guardar ${nextView}`}</button>
          </div>
        </div>
      )}
      {canCapture && !candidate && <div className="capture__actions">
        <button className="action-button action-button--secondary" type="button" onClick={() => cameraInput.current?.click()}>{saved.length ? 'Tomar otra vista' : 'Tomar fotografía'}</button>
        <button className="action-button action-button--secondary" type="button" onClick={() => galleryInput.current?.click()}>Elegir JPG/PNG</button>
      </div>}
      {error && <p className="capture__error" role="alert">{error}</p>}
      <p className="capture__hint">Una fotografía guardada no genera clasificación automática. Para cambiar de pieza, crea una evaluación diferente.</p>
    </div>
  )
}
