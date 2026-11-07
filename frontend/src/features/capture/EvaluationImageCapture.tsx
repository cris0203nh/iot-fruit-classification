import { useEffect, useRef, useState } from 'react'
import {
  ApiConnectionError,
  ApiResponseError,
  getEvaluationById,
  resolveEvidenceUrl,
  uploadEvaluationPhoto,
  type CapturedEvidence,
} from '../../services/agroscanApi'
import { captureFileError } from './captureValidation'
import { nextCaptureView } from './captureViews'
import { ProtectedEvidenceImage } from './ProtectedEvidenceImage'
import './EvaluationImageCapture.css'

type Props = {
  evaluationId: string
  onSavedCountChange?: (count: number) => void
  onEvidenceChange?: (count: number) => void
}
type Saved = CapturedEvidence & { url: string }
type LoadedState = 'loading' | 'ready' | 'closed' | 'failed'

function asSaved(evidence: CapturedEvidence[]): Saved[] {
  return evidence.map((item) => {
    const url = resolveEvidenceUrl(item.imageUrl)
    if (!url) throw new Error('Ruta de imagen no válida.')
    return { ...item, url }
  })
}

export function EvaluationImageCapture({
  evaluationId,
  onSavedCountChange,
  onEvidenceChange,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const sending = useRef(false)

  const [candidate, setCandidate] = useState<{ file: File; url: string } | null>(null)
  const [saved, setSaved] = useState<Saved[]>([])
  const [loadState, setLoadState] = useState<LoadedState>('loading')
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [rotationConfirmed, setRotationConfirmed] = useState(false)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [cameraStarting, setCameraStarting] = useState(false)

  const nextView = nextCaptureView(saved.map(item => item.view))
  const canCapture = loadState === 'ready' && !uploading
  const canSave = canCapture && (saved.length === 0 || rotationConfirmed)

  useEffect(() => {
    onSavedCountChange?.(saved.length)
    onEvidenceChange?.(saved.length)
  }, [saved.length, onSavedCountChange, onEvidenceChange])

  useEffect(() => {
    let active = true

    getEvaluationById(evaluationId).then(
      detail => {
        if (!active) return
        if (!detail) {
          setLoadState('failed')
          setError('No se encontró la evaluación.')
          return
        }
        try {
          setSaved(asSaved(detail.evidence))
          setLoadState(detail.status === 'processing' ? 'ready' : 'closed')
          setError(null)
        } catch (failure) {
          setLoadState('failed')
          setError(failure instanceof Error ? failure.message : 'Error al consultar imágenes.')
        }
      },
      (failure: unknown) => {
        if (!active) return
        setLoadState('failed')
        setError(
          failure instanceof ApiConnectionError
            ? 'No hay conexión con FastAPI.'
            : failure instanceof ApiResponseError
              ? `Error HTTP ${failure.status} al consultar imágenes.`
              : 'No se pudieron consultar las imágenes.'
        )
      }
    )

    return () => { active = false }
  }, [evaluationId, revision])

  useEffect(() => {
    return () => {
      if (candidate) URL.revokeObjectURL(candidate.url)
    }
  }, [candidate])

  useEffect(() => {
    if (!cameraOpen) return

    const video = videoRef.current
    const stream = streamRef.current

    if (!video || !stream) return

    video.srcObject = stream
    void video.play().catch(() => {
      setError('No se pudo iniciar la vista previa de la cámara.')
    })

    return () => {
      video.srcObject = null
    }
  }, [cameraOpen])

  function closeCamera() {
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    setCameraOpen(false)
    setCameraReady(false)
  }

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }, [])

  async function openCamera() {
    if (!canCapture || cameraStarting) return

    setError(null)

    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('Abre AgroScan mediante localhost o HTTPS para utilizar la cámara.')
      return
    }

    setCameraStarting(true)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      })

      streamRef.current = stream
      setCameraOpen(true)
    } catch (failure) {
      const name = failure instanceof Error ? failure.name : ''

      setError(
        name === 'NotAllowedError'
          ? 'Permite el acceso a la cámara en Chrome.'
          : name === 'NotFoundError'
            ? 'No se encontró la cámara integrada de la laptop.'
            : name === 'NotReadableError'
              ? 'La cámara está ocupada por otra aplicación. Cierra Cámara de Windows.'
              : 'No se pudo iniciar la cámara.'
      )
    } finally {
      setCameraStarting(false)
    }
  }

  async function capturePhoto() {
    const video = videoRef.current

    if (!video || !cameraReady || !video.videoWidth) {
      setError('Espera a que aparezca la imagen de la cámara.')
      return
    }

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    const context = canvas.getContext('2d')

    if (!context) {
      setError('No se pudo procesar la fotografía.')
      return
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>(resolve => {
      canvas.toBlob(resolve, 'image/jpeg', 0.85)
    })

    if (!blob) {
      setError('No se pudo generar la fotografía.')
      return
    }

    const file = new File(
      [blob],
      `AgroScan-${evaluationId}-${Date.now()}.jpg`,
      { type: 'image/jpeg', lastModified: Date.now() }
    )

    const validation = captureFileError(file)

    if (validation) {
      setError(validation)
      return
    }

    setCandidate({
      file,
      url: URL.createObjectURL(file),
    })

    setError(null)
    closeCamera()
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
      const result = await uploadEvaluationPhoto(
        evaluationId,
        candidate.file,
        nextView
      )

      const [item] = asSaved([result])
      setSaved(previous => [...previous, item])
      setRotationConfirmed(false)
      setCandidate(null)
    } catch (failure) {
      setError(
        failure instanceof ApiConnectionError
          ? 'No se pudo confirmar el envío. Consulta las imágenes guardadas antes de reintentar.'
          : failure instanceof ApiResponseError
            ? `Error HTTP ${failure.status}: ${failure.message}`
            : 'No se pudo confirmar el almacenamiento.'
      )
      setLoadState('failed')
    } finally {
      sending.current = false
      setUploading(false)
    }
  }

  return (
    <div className="capture" aria-label="Captura RGB">
      <p className="capture__reference">
        Evaluación actual: <strong>{evaluationId}</strong>
      </p>

      <p className="capture__hint">
        Fotografía una sola fruta. Mantén el fruto quieto y comprueba el enfoque.
      </p>

      {loadState === 'loading' && <p role="status">Consultando evaluación...</p>}

      {loadState === 'closed' && (
        <p role="status">La evaluación está cerrada. Solo puedes consultar sus imágenes.</p>
      )}

      {loadState === 'failed' && (
        <button
          className="action-button action-button--secondary"
          type="button"
          disabled={uploading}
          onClick={() => {
            setCandidate(null)
            setLoadState('loading')
            setRevision(value => value + 1)
          }}
        >
          Consultar nuevamente
        </button>
      )}

      {saved.length > 0 && (
        <section aria-label="Fotografías guardadas">
          <p className="capture__hint">
            {saved.length} fotografía(s) guardada(s) en {evaluationId}
          </p>
          <ul className="capture__gallery">
            {saved.map(item => (
              <li key={item.id}>
                <ProtectedEvidenceImage
                  path={item.imageUrl}
                  alt={`Fotografía ${item.view}`}
                />
                <strong>{item.view}</strong>
                <span>{item.id}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {loadState === 'ready' && saved.length > 0 && !candidate && (
        <>
          <p className="capture__rotation">
            Para la siguiente vista, gira manualmente la misma fruta.
          </p>
          <label className="capture__rotation-check">
            <input
              type="checkbox"
              checked={rotationConfirmed}
              onChange={event => setRotationConfirmed(event.target.checked)}
              disabled={uploading}
            />
            Confirmo que giré manualmente la misma fruta.
          </label>
        </>
      )}

      {cameraOpen && (
        <section className="capture__camera">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            onCanPlay={() => setCameraReady(true)}
            className="capture__video"
          />
          <p className="capture__hint">
            Cámara integrada de la laptop. Coloca el mango o tomate frente a ella.
          </p>
          <div className="capture__actions">
            <button
              className="action-button action-button--primary"
              type="button"
              disabled={!cameraReady}
              onClick={() => void capturePhoto()}
            >
              Capturar fotografía
            </button>
            <button
              className="action-button action-button--secondary"
              type="button"
              onClick={closeCamera}
            >
              Cancelar
            </button>
          </div>
        </section>
      )}

      {candidate && (
        <div className="capture__result">
          <img src={candidate.url} alt="Vista previa de la fotografía" />
          <p>
            Fotografía: <strong>{candidate.file.name}</strong>
          </p>
          <div className="capture__actions">
            <button
              className="action-button action-button--secondary"
              type="button"
              disabled={!canCapture}
              onClick={() => {
                setCandidate(null)
                void openCamera()
              }}
            >
              Repetir fotografía
            </button>
            <button
              className="action-button action-button--secondary"
              type="button"
              onClick={discard}
            >
              Descartar
            </button>
            <button
              className="action-button action-button--primary"
              type="button"
              disabled={!canSave}
              onClick={() => void save()}
            >
              {uploading ? 'Guardando...' : 'Guardar fotografía'}
            </button>
          </div>
        </div>
      )}

      {canCapture && !candidate && !cameraOpen && (
        <div className="capture__actions">
          <button
            className="action-button action-button--primary"
            type="button"
            disabled={cameraStarting}
            onClick={() => void openCamera()}
          >
            {cameraStarting ? 'Abriendo cámara...' : 'Tomar fotografía'}
          </button>
        </div>
      )}

      {error && <p className="capture__error" role="alert">{error}</p>}

      <p className="capture__hint">
        La fotografía se guarda en la evaluación actual. Guardarla no genera clasificación automática.
      </p>
    </div>
  )
}
