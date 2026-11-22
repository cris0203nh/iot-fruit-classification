
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiConnectionError,
  ApiResponseError,
  getSessionRole,
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
import { analyzeFruitGeometry, listFruitGeometries, type FruitGeometryResult } from '../../services/agroscanApi'
import { GeometryOrOriginal } from '../geometry/GeometryEvidence'
import { QualityProposalPanel } from '../quality/QualityProposalPanel'
import { AutoV2QualityPanel } from '../quality/AutoV2QualityPanel'
import { A4DimensionPanel } from '../geometry/A4DimensionPanel'
import { ApproxA4Panel } from '../geometry/ApproxA4Panel'
import './EvaluationImageCapture.css'

type Props = {
  evaluationId: string
  autoStart?: boolean
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
  autoStart = false,
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
  const fileInputRef = useRef<HTMLInputElement>(null)
  const autoStartAttemptedId = useRef<string | null>(null)

  const [candidate, setCandidate] = useState<Candidate | null>(null)
const [saved, setSaved] = useState<Saved[]>([])
  const [loadState, setLoadState] = useState<LoadedState>('loading')
  const [revision, setRevision] = useState(0)
  const [geometry, setGeometry] = useState<FruitGeometryResult[]>([])
  const geometryRequests = useRef(new Set<string>())
  const [geometryPending, setGeometryPending] = useState<ReadonlySet<string>>(new Set())
  const [geometryError, setGeometryError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void listFruitGeometries(evaluationId).then(rows => {
      if (active) setGeometry(previous => [...rows, ...previous.filter(row =>
        row.evaluationId === evaluationId && !rows.some(saved => saved.id === row.id))])
    })
      .catch(() => { if (active) setGeometryError('No se pudieron consultar las mediciones guardadas.') })
    return () => { active = false }
  }, [evaluationId, revision])

  async function analyzeSavedImage(imageId: string) {
    const key = `${evaluationId}:${imageId}`
    if (geometryRequests.current.has(key)) return
    geometryRequests.current.add(key)
    setGeometryPending(previous => new Set([...previous, imageId]))
    setGeometryError(null)
    try {
      const result = await analyzeFruitGeometry(evaluationId, imageId)
      setGeometry(previous => [...previous.filter(row => row.id !== result.id), result])
    } catch (cause) {
      setGeometryError(cause instanceof Error ? `No se pudo analizar la geometría: ${cause.message}` : 'No se pudo analizar la geometría.')
    } finally {
      geometryRequests.current.delete(key)
      setGeometryPending(previous => new Set([...previous].filter(id => id !== imageId)))
    }
  }

  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [checkingFile, setCheckingFile] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [cameraStarting, setCameraStarting] = useState(false)
  const [cameraLabel, setCameraLabel] = useState('Webcam USB')

  const [, setVisionDetection] =
    useState<FruitDetectionResult | null>(null)

  const [visionMessage, setVisionMessage] =
    useState('Esperando detección de fruta.')

  const nextView = nextCaptureView(saved.map(item => item.view))

  const canCapture = loadState === 'ready' && !uploading

  // El guardado no requiere confirmaciones manuales en pantalla.
  const canSave = Boolean(candidate) && canCapture && !checkingFile

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
            ? 'No se pudo conectar para consultar las fotografías.'
            : failure instanceof ApiResponseError
              ? failure.message
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

  // ==================================================
  // ABRIR WEBCAM USB COMO CÁMARA PREDETERMINADA
  // ==================================================

  const openCamera = useCallback(async () => {
    if (!canCapture || cameraStarting) return

    setError(null)

    if (
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      !navigator.mediaDevices?.enumerateDevices
    ) {
      setError(
        'Abre AgroScan mediante localhost o HTTPS y permite el acceso a la cámara.'
      )
      return
    }

    setCameraStarting(true)

    let permissionStream: MediaStream | null = null

    try {
      // 1. Solicitar permiso temporal para identificar las cámaras.
      permissionStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: true,
      })

      permissionStream.getTracks().forEach(track => track.stop())
      permissionStream = null

      // 2. Enumerar los dispositivos disponibles.
      const devices = await navigator.mediaDevices.enumerateDevices()

      const cameras = devices.filter(
        device => device.kind === 'videoinput'
      )

      if (cameras.length === 0) {
        throw new Error('No se encontraron cámaras conectadas.')
      }

      const storageKey = 'agroscan_preferred_usb_camera_id'

      const savedDeviceId = localStorage.getItem(storageKey)

      // 3. Identificar cámaras integradas.
      const isInternalCamera = (label: string) =>
        /(integrated|built.?in|internal|facetime|laptop|front.?camera|user.?facing)/i.test(label)

      // 4. Identificar cámaras USB externas.
      const isUsbCamera = (label: string) =>
        /(usb|uvc|webcam|external|2k|hd.?camera)/i.test(label)

      // 5. Recuperar la webcam USB seleccionada anteriormente.
      let selectedCamera = cameras.find(
        camera =>
          camera.deviceId === savedDeviceId &&
          !isInternalCamera(camera.label)
      )

      // 6. Priorizar una cámara USB.
      if (!selectedCamera) {
        selectedCamera = cameras.find(
          camera =>
            isUsbCamera(camera.label) &&
            !isInternalCamera(camera.label)
        )
      }

      // 7. Buscar una cámara externa si Chrome usa otro nombre.
      if (!selectedCamera) {
        const externalCandidates = cameras.filter(
          camera => !isInternalCamera(camera.label)
        )

        if (externalCandidates.length === 1) {
          selectedCamera = externalCandidates[0]
        } else if (cameras.length === 1) {
          selectedCamera = cameras[0]
        }
      }

      // 8. No seleccionar silenciosamente la cámara integrada.
      if (!selectedCamera) {
        const detectedNames = cameras
          .map(camera => camera.label || 'Cámara sin nombre')
          .join(', ')

        throw new Error(
          `No se pudo identificar automáticamente la webcam USB. Cámaras detectadas: ${detectedNames}. Comprueba que esté conectada.`
        )
      }

      // 9. Guardar la selección para próximas evaluaciones.
      localStorage.setItem(storageKey, selectedCamera.deviceId)

      setCameraLabel(selectedCamera.label || 'Webcam USB')

      // 10. Abrir exclusivamente la webcam seleccionada.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          deviceId: { exact: selectedCamera.deviceId },
          width: { ideal: 2560 },
          height: { ideal: 1440 },
        },
      })

      streamRef.current = stream
      setCameraOpen(true)

    } catch (failure) {
      permissionStream?.getTracks().forEach(track => track.stop())

      const name = failure instanceof Error ? failure.name : ''

      setError(
        name === 'NotAllowedError'
          ? 'Permite el acceso a la webcam en Chrome.'
          : name === 'NotFoundError'
            ? 'La webcam USB seleccionada ya no está conectada.'
            : name === 'NotReadableError'
              ? 'La webcam está ocupada por otra aplicación. Cierra Cámara de Windows y vuelve a intentar.'
              : failure instanceof Error
                ? failure.message
                : 'No se pudo iniciar la webcam USB.'
      )

    } finally {
      setCameraStarting(false)
    }
  }, [canCapture, cameraStarting])

  // Apertura opcional y única por evaluación: se agenda fuera del efecto
  // para no provocar actualizaciones de estado durante su ejecución.
  // Los reintentos posteriores quedan en el botón manual de captura.
  useEffect(() => {
    if (
      !autoStart ||
      loadState !== 'ready' ||
      cameraOpen ||
      cameraStarting ||
      candidate ||
      saved.length >= 2 ||
      autoStartAttemptedId.current === evaluationId
    ) {
      return
    }

    let cancelled = false
    void Promise.resolve().then(() => {
      if (cancelled || autoStartAttemptedId.current === evaluationId) return
      autoStartAttemptedId.current = evaluationId
      void openCamera()
    })
    return () => { cancelled = true }
  }, [
    autoStart,
    loadState,
    cameraOpen,
    cameraStarting,
    candidate,
    saved.length,
    evaluationId,
    openCamera,
  ])

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

  setError(null)

    closeCamera()
  }

  // La referencia se sincroniza tras el render, nunca durante él.
  // El bucle de detección utiliza siempre la implementación confirmada más reciente.
  useEffect(() => {
    capturePhotoRef.current = capturePhoto
  })

  // Descartar fotografía.
  function discard() {
    if (!canCapture) return

    setCandidate(null)

    setError(null)
  }

  // Admite una fotografía JPG/PNG como vista adicional de la MISMA evaluación.
  // No crea una evaluación, no salta el control de calidad ni confirma un grado.
  async function chooseFile(file: File) {
    if (!canCapture || checkingFile) return
    const validation = captureFileError(file)
    if (validation) {
      setError(validation)
      return
    }
    setCheckingFile(true)
    setCandidate(null)
    setError(null)
    closeCamera()
    try {
      const quality = await analyzeCaptureQuality(file)
      if (quality.status === 'invalid') {
        setError(`Fotografía rechazada: ${quality.issues.join(' ')}`)
        return
      }
      setCandidate({ file, url: URL.createObjectURL(file), quality })
    } catch {
      setError('No se pudo revisar la imagen seleccionada. Elige otro JPG o PNG.')
    } finally {
      setCheckingFile(false)
    }
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

      setSaved(previous => previous.some(old => old.id === item.id) ? previous : [...previous, item])
      void analyzeSavedImage(item.id)

    setCandidate(null)

    } catch (failure) {
      setError(
        failure instanceof ApiConnectionError
          ? 'No se pudo confirmar el envío. Consulta las imágenes guardadas antes de reintentar.'
          : failure instanceof ApiResponseError
            ? failure.message
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
            setLoadState('loading')
            setRevision(value => value + 1)
          }}
        >
          Consultar nuevamente
        </button>
      )}

      <p className="capture__progress" role="status">
        {saved.length >= 2
          ? `${saved.length} fotografías guardadas. Ya puedes continuar al peso de confirmación.`
          : `${saved.length} de 2 fotografías guardadas. ${saved.length === 1
            ? 'Gira la misma fruta y registra la segunda vista.'
            : 'Toma o sube la primera fotografía.'}`}
      </p>

      <div className="capture__workspace">
        <div className="capture__operation">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,.jpg,.jpeg,.png"
            className="capture__input"
            aria-label="Elegir fotografía JPG o PNG"
            onChange={event => {
              const file = event.currentTarget.files?.[0]
              event.currentTarget.value = ''
              if (file) void chooseFile(file)
            }}
          />

          {canCapture && !candidate && !cameraOpen && (
            <div className="capture__actions capture__actions--primary">
              <button type="button" className="action-button action-button--primary"
                disabled={cameraStarting || checkingFile} onClick={() => void openCamera()}>
                {cameraStarting ? 'Abriendo cámara…' : saved.length === 1
                  ? 'Tomar segunda fotografía' : 'Tomar fotografía con cámara'}
              </button>
              <button type="button" className="action-button action-button--secondary"
                disabled={cameraStarting || checkingFile} onClick={() => fileInputRef.current?.click()}>
                {checkingFile ? 'Revisando imagen…' : 'Subir imagen JPG/PNG'}
              </button>
            </div>
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
                Webcam seleccionada: {cameraLabel}. Coloca el mango o tomate frente a ella.
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
                <button type="button" className="action-button action-button--secondary"
                  disabled={checkingFile} onClick={() => fileInputRef.current?.click()}>
                  Subir imagen JPG/PNG
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

              <p className="capture__hint" role="status">
                {candidate.quality.status === 'valid'
                  ? 'Calidad visual preliminarmente aceptable.'
                  : candidate.quality.issues.length > 0
                    ? candidate.quality.issues.join(' ')
                    : 'La fotografía requiere revisión visual.'}
              </p>

              <details className="capture__advanced">
                <summary>Detalles de calidad de la fotografía</summary>
              <p className="capture__hint">
                Nitidez:{' '}
                {candidate.quality.metrics.laplacianVariance ?? 'No disponible'}
                {' | '}
                Brillo:{' '}
                {candidate.quality.metrics.meanBrightness ?? 'No disponible'}

              </p>
              </details>

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

          {error && (
            <p className="capture__error" role="alert">
              {error}
            </p>
          )}

        </div>
        <aside className="capture__evidence" aria-label="Vistas de la pieza">
          <section aria-label="Fotografías guardadas">

            <p className="capture__hint">
              Fotografías guardadas de esta pieza.
            </p>

            <ul className="capture__gallery">
              {saved.map(item => (
                <li key={item.id}>

                  <strong>{item.view} · {item.id}</strong>
                  <GeometryOrOriginal path={item.imageUrl} alt={`Fotografía ${item.view}`}
                    result={geometry.filter(row => row.imageId === item.id).at(-1)} />
                  {geometryPending.has(item.id) && <p role="status">Calculando geometría en píxeles…</p>}
                  {['administrador', 'operador'].includes(getSessionRole() ?? '') && !geometry.some(row => row.imageId === item.id) && (
                    <button type="button" className="action-button action-button--secondary"
                      disabled={geometryPending.has(item.id)} onClick={() => void analyzeSavedImage(item.id)}>
                      {geometryPending.has(item.id) ? 'Analizando YOLOE…' : 'Analizar o reintentar geometría de esta foto'}
                    </button>
                  )}


                </li>
              ))}
              {Array.from({ length: Math.max(0, 2 - saved.length) }, (_, index) => (
                <li className="capture__pending-view" key={`pending-${index}`}>
                  <strong>Vista {saved.length + index + 1}</strong>
                  <span>Pendiente de guardar</span>
                </li>
              ))}
            </ul>

          </section>


        </aside>
      </div>
      {saved.length >= 2 && (
        <AutoV2QualityPanel
          key={`${evaluationId}:${saved.map(item => item.id).join('|')}`}
          evaluationId={evaluationId}
          evidence={saved}
        />
      )}

      {/* Estimación automática A4 para operador y administrador. */}
      {saved.length >= 2 &&
        (getSessionRole() === 'operador' ||
          getSessionRole() === 'administrador') && (
          <ApproxA4Panel
            key={`approx:${evaluationId}:${saved.map(item => item.id).join('|')}`}
            evaluationId={evaluationId}
            evidence={saved}
          />
        )}

      {/* La homografía A4 estricta permanece disponible como herramienta avanzada. */}
      {saved.length >= 2 && getSessionRole() === 'administrador' && (
        <details className="capture__advanced">
          <summary>Calibración de medidas (opcional)</summary>
          <A4DimensionPanel
            key={`a4:${evaluationId}:${saved.map(item => item.id).join('|')}`}
            evaluationId={evaluationId}
            evidence={saved}
          />
        </details>
      )}

      {geometryError && <p role="status" className="capture__hint">{geometryError}</p>}

      {saved.length >= 2 && getSessionRole() === 'administrador' && (
        <details className="capture__advanced"
          onToggle={event => setAdvancedOpen(event.currentTarget.open)}>
          <summary>Herramientas técnicas de clasificación</summary>
          {advancedOpen && <QualityProposalPanel evaluationId={evaluationId} />}
        </details>
      )}

      <p className="capture__hint">
        La clasificación analiza las dos vistas guardadas.
        El peso sigue siendo obligatorio para confirmar la adquisición. Revisión humana requerida.
      </p>

    </div>
  )
}
