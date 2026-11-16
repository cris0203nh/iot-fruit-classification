import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/layout/Icon'
import {
  ApiConnectionError,
  ApiResponseError,
  createAutomaticEvaluation,
  getEvaluationById,
  precheckFruit,
  uploadEvaluationPhoto,
  type FruitPrecheck,
  type LotRecord,
} from '../../services/agroscanApi'
import type { EvaluationDetail } from '../history/historyService'
import { GeometryEvidence } from '../geometry/GeometryEvidence'
import { analyzeFruitGeometry } from '../../services/agroscanApi'
import './AutoRegistrationPanel.css'

type Props = {
  lots: LotRecord[]
  lotsLoading: boolean
  lotsError: string | null
  preferredLot: string
  registered: EvaluationDetail | null
  onRefreshLots: () => void
  onRegistered: (value: EvaluationDetail) => void
  onManual: () => void
}

const MAX_INPUT_BYTES = 12 * 1024 * 1024

async function toNormalizedJpeg(source: Blob): Promise<File> {
  if (source.size <= 0 || source.size > MAX_INPUT_BYTES) {
    throw new Error('Selecciona una imagen válida de hasta 12 MiB.')
  }
  const bitmap = await createImageBitmap(source)
  try {
    if (Math.min(bitmap.width, bitmap.height) < 128) {
      throw new Error('La fotografía debe tener como mínimo 128 px por lado.')
    }
    const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('No se pudo preparar la fotografía.')
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const jpg = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.80))
    if (!jpg) throw new Error('No se pudo comprimir la fotografía.')
    if (jpg.size > 2 * 1024 * 1024) {
      throw new Error('La fotografía sigue superando 2 MiB; selecciona otra.')
    }
    return new File([jpg], 'AG053-deteccion.jpg', { type: 'image/jpeg' })
  } finally {
    bitmap.close()
  }
}

export function AutoRegistrationPanel({
  lots, lotsLoading, lotsError, preferredLot, registered,
  onRefreshLots, onRegistered, onManual,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraBusy, setCameraBusy] = useState(false)
  const [running, setRunning] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [precheck, setPrecheck] = useState<FruitPrecheck | null>(null)
  const [jpg, setJpg] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [lot, setLot] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  useEffect(() => {
    if (!cameraOpen || !videoRef.current || !streamRef.current) return
    const video = videoRef.current
    video.srcObject = streamRef.current
    void video.play().catch(() => setError('No se pudo reproducir la cámara.'))
    return () => { video.srcObject = null }
  }, [cameraOpen])

  useEffect(() => {
    return () => { streamRef.current?.getTracks().forEach((track) => track.stop()) }
  }, [])

  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }
  }, [previewUrl])

  const productLots = lots.filter((item) => item.status === 'open' && item.product === precheck?.product)
  const selectedLot = productLots.find((item) => item.code === lot) ?? null

  function closeCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCameraOpen(false)
  }

  async function openCamera() {
    if (cameraBusy || running || registering) return
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('La cámara requiere localhost o HTTPS. Puedes cargar una fotografía desde el equipo.')
      return
    }
    setCameraBusy(true)
    setError(null)
    try {
      closeCamera()
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: false, video: { facingMode: 'environment' },
      })
      setCameraOpen(true)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo abrir la cámara.')
    } finally {
      setCameraBusy(false)
    }
  }

  async function analyze(source: Blob) {
    if (registered || running || registering) return
    setRunning(true)
    setError(null)
    setWarning(null)
    setPrecheck(null)
    setLot('')
    setJpg(null)
    setPreviewUrl(null)
    try {
      const prepared = await toNormalizedJpeg(source)
      const result = await precheckFruit(prepared)
      setJpg(prepared)
      setPreviewUrl(URL.createObjectURL(prepared))
      setPrecheck(result)
      if (result.readyToRegister && result.product) {
        const preferred = lots.find((item) => item.code === preferredLot && item.product === result.product && item.status === 'open')
        if (preferred) setLot(preferred.code)
      }
      closeCamera()
    } catch (failure) {
      setError(failure instanceof ApiResponseError
        ? failure.message
        : failure instanceof ApiConnectionError
          ? 'No se pudo conectar. Reintenta o solicita ayuda al administrador.'
          : failure instanceof Error ? failure.message : 'No se pudo analizar la fotografía.')
    } finally {
      setRunning(false)
    }
  }

  async function takeFrame() {
    const video = videoRef.current
    if (!video || !video.videoWidth) {
      setError('Espera a que la cámara muestre imagen.')
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) return
    context.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.8))
    if (blob) await analyze(blob)
  }

  async function register() {
    if (!selectedLot || !precheck?.readyToRegister || !precheck.detectionToken || !jpg || registering) return
    setRegistering(true)
    setError(null)
    setWarning(null)
    try {
      const saved = await createAutomaticEvaluation({
        lotId: selectedLot.code,
        detectionToken: precheck.detectionToken,
      })
      // Si se pierde la respuesta de subida, la evaluación YA existe: jamás
      // crear otra pieza. La carga posterior usa idempotencia por imagen.
      let detail = saved
      try {
        const photo = await uploadEvaluationPhoto(saved.id, jpg, 'vista-1')
        detail = (await getEvaluationById(saved.id)) ?? saved
        try {
          await analyzeFruitGeometry(saved.id, photo.id)
        } catch {
          setWarning('La pieza y la fotografía están guardadas; la geometría quedó pendiente. Puedes reanalizar la evidencia en el paso de imágenes.')
        }
      } catch {
        setWarning('La pieza fue registrada, pero la primera fotografía no se confirmó. Revísala en el paso de imágenes.')
      }
      onRegistered(detail)
    } catch (failure) {
      setError(failure instanceof ApiResponseError
        ? `No se registró la pieza: ${failure.message}`
        : failure instanceof ApiConnectionError
          ? 'No se confirmó el registro. Reintenta con esta misma detección: el sistema evitará duplicar la pieza.'
          : failure instanceof Error ? failure.message : 'No se confirmó el registro.')
    } finally {
      setRegistering(false)
    }
  }

  return (
    <section className="evaluation-form ag053" aria-labelledby="ag053-title">
      <div className="evaluation-section-heading">
        <span className="evaluation-step" aria-hidden="true">01</span>
        <div>
          <h2 id="ag053-title">{registered ? 'Pieza registrada' : 'Identificación y lote'}</h2>
        </div>
      </div>

      {registered ? (
        <div className="ag053__done" role="status">
          <strong>Identificación y registro confirmados</strong>
          <dl className="ag053__record">
            <div><dt>Producto</dt><dd>{registered.product === 'mango' ? 'Mango' : 'Tomate'}</dd></div>
            <div><dt>Lote</dt><dd>{registered.lotId}</dd></div>
            <div><dt>Pieza</dt><dd>{registered.pieceId}</dd></div>
            <div><dt>Evaluación</dt><dd>{registered.id}</dd></div>
          </dl>
          <p>La identificación no es una clasificación de calidad.</p>
          {warning && <p className="ag053__warning">{warning}</p>}
          <Link to={`/trazabilidad/${encodeURIComponent(registered.id)}`}>Consultar trazabilidad</Link>
        </div>
      ) : (
        <div className="ag053__workspace">
          <div className="ag053__visual">
            <div className="ag053__source">
              <label className="ag053__file">
                <Icon name="camera" size={17} /> Seleccionar fotografía
                <input type="file" accept="image/jpeg,image/png" onChange={(event) => {
                  const selected = event.currentTarget.files?.[0]
                  event.currentTarget.value = ''
                  if (selected) void analyze(selected)
                }} disabled={running || registering} />
              </label>
              <button className="action-button action-button--secondary" type="button" onClick={() => void openCamera()} disabled={running || registering || cameraBusy}>
                {cameraBusy ? 'Abriendo…' : 'Usar cámara'}
              </button>
          </div>
          {cameraOpen && (
            <div className="ag053__camera">
              <video ref={videoRef} autoPlay playsInline muted aria-label="Vista previa de la fruta" />
              <div className="ag053__source">
                <button type="button" className="action-button action-button--primary" disabled={running} onClick={() => void takeFrame()}>Analizar fotograma</button>
                <button type="button" className="action-button action-button--secondary" onClick={closeCamera}>Cerrar cámara</button>
              </div>
            </div>
          )}
          {running && <p role="status">Analizando la fotografía…</p>}
          {!cameraOpen && !previewUrl && <div className="ag053__placeholder">
            <Icon name="camera" size={28} />
            <strong>Fotografía de identificación</strong>
            <span>Una sola fruta, quieta y enfocada.</span>
          </div>}
          {previewUrl && <GeometryEvidence previewUrl={previewUrl} result={precheck} alt="Fotografía enviada a detección preliminar" compact />}
          </div>
          <div className="ag053__registration">
            {precheck && (
              <div className="ag053__result" role="status">
                {precheck.readyToRegister && precheck.product ? (
                  <>
                    <strong>Producto identificado: {precheck.product === 'mango' ? 'Mango' : 'Tomate'}</strong>
                    <details className="operational-help">
                      <summary>Detalles de identificación</summary>
                      <span>Comprueba que el producto identificado coincide con la fruta de la fotografía.</span>
                    </details>
                    <p>Identificación preliminar, sujeta a la comprobación del operador. No es un grado de calidad.</p>
                  </>
                ) : (
                  <p>No se pudo identificar una única fruta con seguridad. Repite la fotografía o utiliza el registro manual.</p>
                )}
              </div>
            )}
              <div className="ag053__lots">
                <label htmlFor="ag053-lot">Lote abierto{precheck?.product ? ` de ${precheck.product}` : ''}</label>
                <select id="ag053-lot" value={lot} onChange={(event) => setLot(event.target.value)} disabled={!precheck?.readyToRegister || registering || lotsLoading} aria-describedby="ag053-lot-help">
                  <option value="">{lotsLoading ? 'Cargando lotes…' : precheck?.readyToRegister ? 'Selecciona un lote compatible' : 'Primero identifica la fruta'}</option>
                  {productLots.map((item) => <option value={item.code} key={item.id}>{item.code}</option>)}
                </select>
                <p id="ag053-lot-help">La referencia de pieza se asigna al registrar. La foto se guarda como primera vista si se confirma la carga.</p>
                {precheck?.readyToRegister && !lotsLoading && productLots.length === 0 && <p>No hay lotes compatibles. <Link to="/lotes">Crear lote</Link></p>}
                {lotsError && <p role="alert">{lotsError}</p>}
                <div className="ag053__source">
                  <button type="button" className="action-button action-button--secondary" onClick={onRefreshLots} disabled={lotsLoading}>Actualizar lotes</button>
                  <button type="button" className="action-button action-button--primary" onClick={() => void register()} disabled={!selectedLot || registering}>
                    {registering ? 'Registrando…' : 'Registrar pieza'}
                  </button>
                </div>
              </div>
            {error && <p className="ag053__warning" role="alert">{error}</p>}
            <div className="ag053__manual">
              <p>¿No se reconoce la fruta? Puedes registrarla manualmente.</p>
              <button type="button" className="action-button action-button--secondary" onClick={() => { closeCamera(); onManual() }} disabled={registering}>Registro manual / excepción</button>
          </div>
          </div>
        </div>
      )}
    </section>
  )
}
