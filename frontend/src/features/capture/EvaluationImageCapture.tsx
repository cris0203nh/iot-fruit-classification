import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { ApiConnectionError, ApiResponseError, resolveEvidenceUrl, uploadEvaluationPhoto } from '../../services/agroscanApi'
import { captureFileError } from './captureValidation'
import './EvaluationImageCapture.css'

type Props = { evaluationId: string }
type Saved = { id: string; url: string }

/** Una sola toma inicial. Las vistas adicionales pertenecen a AGROP-27. */
export function EvaluationImageCapture({ evaluationId }: Props) {
  const cameraInput = useRef<HTMLInputElement>(null)
  const galleryInput = useRef<HTMLInputElement>(null)
  const sending = useRef(false)
  const [candidate, setCandidate] = useState<{ file: File; url: string } | null>(null)
  const [saved, setSaved] = useState<Saved | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    return () => { if (candidate) URL.revokeObjectURL(candidate.url) }
  }, [candidate])

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = '' // permite repetir incluso con el mismo archivo
    if (!file) return
    const validationError = captureFileError(file)
    setError(validationError)
    setCandidate(validationError ? null : { file, url: URL.createObjectURL(file) })
  }

  function discard() {
    if (uploading) return
    setCandidate(null)
    setError(null)
  }

  async function save() {
    if (!candidate || saved || sending.current) return
    sending.current = true
    setUploading(true)
    setError(null)
    try {
      const result = await uploadEvaluationPhoto(evaluationId, candidate.file)
      const url = resolveEvidenceUrl(result.imageUrl)
      if (!url) throw new Error('El servidor devolvió una ruta de imagen no válida.')
      setSaved({ id: result.id, url })
      setCandidate(null)
    } catch (failure) {
      const message = failure instanceof ApiConnectionError
        ? 'No se pudo confirmar el envío. Consulta el detalle de la evaluación antes de reintentar para evitar duplicados.'
        : failure instanceof ApiResponseError
          ? `No se guardó la imagen (HTTP ${failure.status}): ${failure.message}`
          : failure instanceof Error ? failure.message : 'No se pudo guardar la imagen.'
      setError(message)
    } finally {
      sending.current = false
      setUploading(false)
    }
  }

  return (
    <div className="capture" aria-label="Captura de fotografía RGB">
      <p className="capture__reference">Evaluación actual: <strong>{evaluationId}</strong></p>
      <p className="capture__hint">Fotografía de una sola pieza, completa y enfocada. Revisa la imagen antes de enviarla.</p>
      <input className="capture__input" ref={cameraInput} type="file" accept="image/jpeg,image/png" capture="environment" onChange={selectFile} aria-label="Tomar fotografía con cámara" disabled={uploading || !!saved} />
      <input className="capture__input" ref={galleryInput} type="file" accept="image/jpeg,image/png" onChange={selectFile} aria-label="Seleccionar imagen de galería" disabled={uploading || !!saved} />
      {saved ? (
        <div className="capture__result" role="status">
          <img src={saved.url} alt={`Fotografía guardada para la evaluación ${evaluationId}`} />
          <p>Imagen vinculada a <strong>{evaluationId}</strong> · Archivo <strong>{saved.id}</strong></p>
          <p>La imagen fue recibida; esto no implica clasificación automática.</p>
        </div>
      ) : candidate ? (
        <div className="capture__result">
          <img src={candidate.url} alt="Vista previa de la fotografía antes del envío" />
          <p>Vista previa: <strong>{candidate.file.name}</strong></p>
          <div className="capture__actions">
            <button className="action-button action-button--secondary" type="button" disabled={uploading} onClick={() => cameraInput.current?.click()}>Repetir toma</button>
            <button className="action-button action-button--secondary" type="button" disabled={uploading} onClick={discard}>Descartar</button>
            <button className="action-button action-button--primary" type="button" disabled={uploading} onClick={save}>{uploading ? 'Enviando…' : 'Guardar en evaluación'}</button>
          </div>
        </div>
      ) : (
        <div className="capture__placeholder">Sin fotografía seleccionada</div>
      )}
      {!saved && <div className="capture__actions">
        <button className="action-button action-button--secondary" type="button" disabled={uploading} onClick={() => cameraInput.current?.click()}>Tomar fotografía</button>
        <button className="action-button action-button--secondary" type="button" disabled={uploading} onClick={() => galleryInput.current?.click()}>Elegir JPG/PNG</button>
      </div>}
      {error && <p className="capture__error" role="alert">{error}</p>}
    </div>
  )
}
