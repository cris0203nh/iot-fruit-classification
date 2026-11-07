
import { useEffect, useRef, useState } from 'react'
import {
  ApiConnectionError,
  ApiResponseError,
  getEvaluationById,
  resolveEvidenceUrl,
  uploadEvaluationPhoto,
  detectEvaluationFrame,
  type FruitDetectionResult,
  type CapturedEvidence,
} from '../../services/agroscanApi'
import {
  analyzeCaptureQuality,
  captureFileError,
  type CaptureQualityResult,
} from './captureValidation'
import { nextCaptureView } from './captureViews'
import { ProtectedEvidenceImage } from './ProtectedEvidenceImage'
import './EvaluationImageCapture.css'

type Props = {
  evaluationId: string
  onSavedCountChange?: (count: number) => void
  onEvidenceChange?: (count: number) => void
}

type Saved = CapturedEvidence & { url: string }

type Candidate = {
  file: File
  url: string
  quality: CaptureQualityResult
}

type LoadedState = 'loading' | 'ready' | 'closed' | 'failed'

function asSaved(evidence: CapturedEvidence[]): Saved[] {
  return evidence.map(item => {
    const url = resolveEvidenceUrl(item.imageUrl)

    if (!url) {
      throw new Error('Ruta de imagen no válida.')
    }

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
  const detecting = useRef(false)
  const stableFrames = useRef(0)
  const autoCaptureTriggered = useRef(false)
  const capturePhotoRef = useRef<() => Promise<void>>(async () => {})

  const [candidate, setCandidate] = useState<Candidate | null>(null)

  // AGROP-28: verificaciones manuales de composición.
  const [singleFruitConfirmed, setSingleFruitConfirmed] =
    useState(false)

  const [framingConfirmed, setFramingConfirmed] =
    useState(false)

  const [saved, setSaved] = useState<Saved[]>([])
  const [loadState, setLoadState] = useState<LoadedState>('loading')
  const [revision, setRevision] = useState(0)

  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  // AGROP-27: giro manual para las vistas adicionales.
  const [rotationConfirmed, setRotationConfirmed] = useState(false)

  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [cameraStarting, setCameraStarting] = useState(false)
  const [, setVisionDetection] = useState<FruitDetectionResult | null>(null)
  const [visionMessage, setVisionMessage] =
    useState("Esperando detecci?n de fruta.")

  const nextView = nextCaptureView(saved.map(item => item.view))

  const canCapture = loadState === 'ready' && !uploading

  // AGROP-28: no guardar una fotografía pendiente de revisión
  // hasta confirmar individualmente la cantidad de frutas
  // y la integridad del encuadre.
  const compositionConfirmed =
    singleFruitConfirmed && framingConfirmed

  const canSave =
    Boolean(candidate) &&
    canCapture &&
    (saved.length === 0 || rotationConfirmed) &&
    (
      candidate?.quality.status !== 'review' ||
      compositionConfirmed
    )

  // Restablecer verificaciones manuales.
  function resetCompositionChecks() {
    setSingleFruitConfirmed(false)
    setFramingConfirmed(false)
  }

  // Notificar cantidad de fotografías guardadas.
  useEffect(() => {
    onSavedCountChange?.(saved.length)
    onEvidenceChange?.(saved.length)
  }, [saved.length, onSavedCountChange, onEvidenceChange])

  // Consultar la evaluación y sus fotografías.
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

          setLoadState(
            detail.status === 'processing' ? 'ready' : 'closed'
          )

          setError(null)
        } catch (failure) {
          setLoadState('failed')

          setError(
            failure instanceof Error
              ? failure.message
              : 'Error al consultar imágenes.'
          )
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

    return () => {
      active = false
    }
  }, [evaluationId, revision])

  // Liberar URL temporal de la fotografía.
  useEffect(() => {
    if (!candidate) return

    return () => {
      URL.revokeObjectURL(candidate.url)
    }
  }, [candidate])

  // Conectar la cámara con el elemento de vídeo.
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


  // AGROP-42: detección automática de mango y tomate en vivo.
  useEffect(() => {
    if (!cameraOpen || !cameraReady) return

    let active = true
    let timer: number | undefined

    const video = videoRef.current
    const canvas = document.createElement('canvas')

    async function detectFrame() {
      if (!active) return

      if (!video || video.readyState < 2 || detecting.current) {
        timer = window.setTimeout(detectFrame, 300)
        return
      }

      detecting.current = true

      try {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight

        const context = canvas.getContext('2d')
        if (!context) throw new Error('Canvas no disponible')

        context.drawImage(video, 0, 0, canvas.width, canvas.height)

        const blob = await new Promise<Blob | null>(resolve => {
          canvas.toBlob(resolve, 'image/jpeg', 0.75)
        })

        if (!blob) throw new Error('Fotograma no disponible')

        const result = await detectEvaluationFrame(evaluationId, blob)

        if (!active) return

        setVisionDetection(result)

        if (result.readyToCapture) {
          stableFrames.current += 1

          setVisionMessage(
            `Fruta detectada: ${((result.confidence ?? 0) * 100).toFixed(1)} %. Estabilizando...`
          )

          if (
            stableFrames.current >= 3 &&
            !autoCaptureTriggered.current
          ) {
            autoCaptureTriggered.current = true

            setVisionMessage('Fruta identificada. Capturando fotografía...')

            await capturePhotoRef.current()
            return
          }
        } else {
          stableFrames.current = 0
          autoCaptureTriggered.current = false

          setVisionMessage(
            result.candidateCount > 1
              ? 'Se detectaron varias frutas. Deja solamente una.'
              : 'Buscando mango o tomate frente a la cámara...'
          )
        }
      } catch {
        if (active) {
          stableFrames.current = 0
          setVisionMessage('Error de detección. Reintentando...')
        }
      } finally {
        detecting.current = false
      }

      if (active) {
        timer = window.setTimeout(detectFrame, 700)
      }
    }

    void detectFrame()

    return () => {
      active = false

      if (timer !== undefined) {
        window.clearTimeout(timer)
      }

      stableFrames.current = 0
      detecting.current = false
    }
  }, [cameraOpen, cameraReady, evaluationId])
  // Liberar cámara al desmontar el componente.
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }, [])

  // Abrir cámara.
  async function openCamera() {
    if (!canCapture || cameraStarting) return

    setError(null)

    if (
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      setError(
        'Abre AgroScan mediante localhost o HTTPS para utilizar la cámara.'
      )
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

  // Capturar y analizar fotografía.
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
      {
        type: 'image/jpeg',
        lastModified: Date.now(),
      }
    )

    // Primera validación: formato, tamaño y archivo.
    const validation = captureFileError(file)

    if (validation) {
      setError(validation)
      return
    }

    // Segunda validación: calidad visual AGROP-28.
    let quality: CaptureQualityResult

    try {
      quality = await analyzeCaptureQuality(file)
    } catch {
      setError(
        'No se pudo analizar la calidad de la fotografía. Repite la captura.'
      )
      return
    }

    // Rechazar fotografías con problemas graves de calidad.
    if (quality.status === 'invalid') {
      setCandidate(null)
      resetCompositionChecks()

      setError(
        `Fotografía rechazada: ${quality.issues.join(' ')}`
      )

      return
    }

    // Crear fotografía candidata.
    setCandidate({
      file,
      url: URL.createObjectURL(file),
      quality,
    })

    resetCompositionChecks()
    setError(null)

    closeCamera()
  }

  // Referencia actual para la captura automática.
  capturePhotoRef.current = capturePhoto

  // Descartar fotografía.
  function discard() {
    if (!canCapture) return

    setCandidate(null)
    resetCompositionChecks()
    setError(null)
  }

  // Guardar fotografía en la evaluación actual.
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
      resetCompositionChecks()
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

      {loadState === 'loading' && (
        <p role="status">Consultando evaluación...</p>
      )}

      {loadState === 'closed' && (
        <p role="status">
          La evaluación está cerrada. Solo puedes consultar sus imágenes.
        </p>
      )}

      {loadState === 'failed' && (
        <button
          className="action-button action-button--secondary"
          type="button"
          disabled={uploading}
          onClick={() => {
            setCandidate(null)
            resetCompositionChecks()
            setLoadState('loading')
            setRevision(value => value + 1)
          }}
        >
          Consultar nuevamente
        </button>
      )}

      {/* Fotografías ya guardadas. */}
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

      {/* Confirmación de giro manual para vistas adicionales. */}
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

      {/* Cámara. */}
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

          <p className="capture__hint" role="status">
            {visionMessage}
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

      {/* Resultado del análisis visual AGROP-28. */}
      {candidate && (
        <div className="capture__result">

          <img
            src={candidate.url}
            alt="Vista previa de la fotografía"
          />

          <p>
            Fotografía: <strong>{candidate.file.name}</strong>
          </p>

          {candidate.quality.status === 'valid' ? (
            <p className="capture__hint" role="status">
              Calidad visual preliminarmente aceptable.
            </p>
          ) : (
            <div className="capture__hint" role="status">

              <strong>Verificación manual de composición requerida</strong>

              {candidate.quality.issues.length > 0 && (
                <ul>
                  {candidate.quality.issues.map((issue, index) => (
                    <li key={index}>{issue}</li>
                  ))}
                </ul>
              )}

              <p>
                El sistema no dispone de un detector entrenado de frutas.
                Comprueba visualmente la cantidad de piezas y el encuadre.
              </p>

              <label className="capture__rotation-check">

                <input
                  type="checkbox"
                  checked={singleFruitConfirmed}
                  onChange={event =>
                    setSingleFruitConfirmed(event.target.checked)
                  }
                  disabled={uploading}
                />

                Confirmo que aparece exactamente una fruta y que no hay otras piezas.

              </label>

              <label className="capture__rotation-check">

                <input
                  type="checkbox"
                  checked={framingConfirmed}
                  onChange={event =>
                    setFramingConfirmed(event.target.checked)
                  }
                  disabled={uploading}
                />

                Confirmo que la fruta está completa y dentro del encuadre.

              </label>

              <p>
                Si aparecen dos o más frutas, o alguna está cortada,
                no confirmes estos criterios y repite la fotografía.
              </p>

            </div>
          )}

          <p className="capture__hint">
            Nitidez:{' '}
            {candidate.quality.metrics.laplacianVariance ?? 'No disponible'}
            {' | '}
            Brillo:{' '}
            {candidate.quality.metrics.meanBrightness ?? 'No disponible'}
          </p>

          {candidate.quality.status === 'review' && (
            <p className="capture__hint">
              Verificación de composición: {
                compositionConfirmed
                  ? 'Confirmada por el operador.'
                  : 'Pendiente de confirmación.'
              }
            </p>
          )}

          <div className="capture__actions">

            <button
              className="action-button action-button--secondary"
              type="button"
              disabled={!canCapture}
              onClick={() => {
                setCandidate(null)
                resetCompositionChecks()
                void openCamera()
              }}
            >
              Repetir fotografía
            </button>

            <button
              className="action-button action-button--secondary"
              type="button"
              disabled={uploading}
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

      {/* Botón inicial para abrir cámara. */}
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

      {error && (
        <p className="capture__error" role="alert">
          {error}
        </p>
      )}

      <p className="capture__hint">
        La fotografía se guarda en la evaluación actual.
        Guardarla no genera clasificación automática.
      </p>

    </div>
  )
}
