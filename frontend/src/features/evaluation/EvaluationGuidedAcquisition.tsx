import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/layout/Icon'
import { EvaluationImageCapture } from '../capture/EvaluationImageCapture'
import { WeightStatusCard } from '../iot/WeightStatusCard'
import {
  ApiConnectionError, ApiResponseError, captureWeightPost, captureWeightPre, type WeightStep,
} from '../../services/agroscanApi'
import type { EvaluationDetail } from '../history/historyService'
import { acquisitionOutcome, hasConfirmedImages, type GuidedStep } from './evaluationFlow'
import './EvaluationGuidedAcquisition.css'

type AcquisitionStep = 2 | 3 | 4 | 5

type Props = {
  evaluation: EvaluationDetail | null
  onStepChange: (value: GuidedStep) => void
  onNextEvaluation: () => void
}

function operationError(failure: unknown): string {
  if (failure instanceof ApiConnectionError) {
    return 'No se confirmó la operación por falta de conexión. Verifica el backend antes de repetirla.'
  }
  if (failure instanceof ApiResponseError) {
    if (failure.status === 401 || failure.status === 403) {
      return 'Acceso no autorizado o sesión vencida. Inicia sesión nuevamente.'
    }
    return `FastAPI rechazó la operación (HTTP ${failure.status}): ${failure.message}`
  }
  return failure instanceof Error ? failure.message : 'No se pudo confirmar la operación.'
}

function WeightResult({ result, name }: { result: WeightStep; name: string }) {
  return (
    <p className="guided-acquisition__success" role="status">
      <Icon name="info" size={17} /> {name} confirmado por FastAPI: <strong>{result.weightG} g</strong>
      <span> · {result.deviceId}</span>
    </p>
  )
}

/** Guía de UI; no crea estados de evaluación ni registra clasificaciones inexistentes. */
export function EvaluationGuidedAcquisition({ evaluation, onStepChange, onNextEvaluation }: Props) {
  const [step, setStep] = useState<AcquisitionStep>(2)
  const [pre, setPre] = useState<WeightStep | null>(null)
  const [post, setPost] = useState<WeightStep | null>(null)
  const [imageCount, setImageCount] = useState(evaluation?.evidence.length ?? 0)
  const [processing, setProcessing] = useState(false)
  const busy = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [retired, setRetired] = useState(false)
  const onEvidenceChange = useCallback((count: number) => {
    setImageCount(count)
  }, [])

  function goTo(next: AcquisitionStep) {
    if (processing) return
    setStep(next)
    setError(null)
    onStepChange(next)
  }

  async function confirmWeight(kind: 'pre' | 'post') {
    if (!evaluation || busy.current) return
    busy.current = true
    setProcessing(true)
    setError(null)
    try {
      if (kind === 'pre') {
        const result = await captureWeightPre(evaluation.id)
        setPre(result)
      } else {
        const result = await captureWeightPost(evaluation.id)
        setPost(result)
      }
    } catch (failure) {
      setError(operationError(failure))
    } finally {
      setProcessing(false)
      busy.current = false
    }
  }

  const outcome = acquisitionOutcome({
    imageCount,
    initialWeightConfirmed: pre !== null,
    finalWeightConfirmed: post !== null,
  })

  return (
    <section className="panel evaluation-acquisition" aria-labelledby="acquisition-heading">
      <div className="evaluation-section-heading">
        <span className="evaluation-step evaluation-step--muted" aria-hidden="true">{evaluation ? step : 2}</span>
        <div>
          <h2 id="acquisition-heading">Procedimiento guiado</h2>
          <p>Una pieza por evaluación. Cada confirmación corresponde a una operación real del backend.</p>
        </div>
      </div>

      {!evaluation ? (
        <div className="evaluation-camera-empty">
          <Icon name="clipboard" size={27} />
          <span>Paso 1: selecciona un lote e identifica la pieza para continuar.</span>
        </div>
      ) : (
        <>
          <div className="guided-acquisition__identity">
            <strong>Evaluación {evaluation.id}</strong>
            <span>Lote: {evaluation.lotId} · Pieza: {evaluation.pieceId}</span>
            <span>Estado en backend al crear: En proceso</span>
          </div>

          {step === 2 && (
            <div className="guided-acquisition__stage">
              <h3>2. Colocar la pieza y verificar el peso</h3>
              <p>Coloca una sola fruta sobre la balanza y espera una lectura reciente y estable. FastAPI validará además la calibración y la tara.</p>
              <WeightStatusCard />
              {pre ? <WeightResult result={pre} name="Peso inicial" /> : (
                <button type="button" className="action-button action-button--primary" onClick={() => void confirmWeight('pre')} disabled={processing}>
                  {processing ? 'Consultando FastAPI…' : 'Registrar peso inicial'}
                </button>
              )}
              {!pre && <p className="guided-acquisition__notice">Si no hay sensor válido, puedes continuar para guardar fotografías; el pesaje permanecerá pendiente.</p>}
              <button type="button" className="action-button action-button--secondary" onClick={() => goTo(3)} disabled={processing}>
                Continuar a imágenes <Icon name="arrow-right" size={17} />
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="guided-acquisition__stage">
              <h3>3. Capturar fotografías RGB</h3>
              <p>Fotografía la misma fruta. Si necesitas otra perspectiva, gírala manualmente sin crear otra evaluación.</p>
              <EvaluationImageCapture evaluationId={evaluation.id} onEvidenceChange={onEvidenceChange} />
              <div className="guided-acquisition__actions">
                <button type="button" className="action-button action-button--secondary" onClick={() => goTo(2)}>Volver a peso</button>
                <button type="button" className="action-button action-button--primary" disabled={!hasConfirmedImages(imageCount)} onClick={() => goTo(4)}>
                  Continuar con {imageCount} {imageCount === 1 ? 'imagen guardada' : 'imágenes guardadas'} <Icon name="arrow-right" size={17} />
                </button>
              </div>
              {!hasConfirmedImages(imageCount) && <p className="guided-acquisition__notice">Para continuar, FastAPI debe confirmar al menos una fotografía.</p>}
            </div>
          )}

          {step === 4 && (
            <div className="guided-acquisition__stage">
              <h3>4. Confirmar la adquisición</h3>
              <dl className="guided-acquisition__review">
                <div><dt>Evaluación</dt><dd>{evaluation.id}</dd></div>
                <div><dt>Fotografías almacenadas</dt><dd>{imageCount}</dd></div>
                <div><dt>Peso inicial</dt><dd>{pre ? `${pre.weightG} g · confirmado` : 'Pendiente'}</dd></div>
                <div><dt>Peso final</dt><dd>{post ? `${post.weightG} g · confirmado` : 'Pendiente'}</dd></div>
              </dl>
              {pre && !post ? (
                <>
                  <p>La pieza debe permanecer en la balanza para registrar una nueva lectura de confirmación.</p>
                  <WeightStatusCard />
                  <button type="button" className="action-button action-button--primary" disabled={processing} onClick={() => void confirmWeight('post')}>
                    {processing ? 'Consultando FastAPI…' : 'Registrar peso de confirmación'}
                  </button>
                </>
              ) : null}
              {post && <WeightResult result={post} name="Peso de confirmación" />}
              <p className={outcome === 'confirmed' ? 'guided-acquisition__success' : 'guided-acquisition__notice'} role="status">
                {outcome === 'confirmed'
                  ? 'Adquisición de fotografías y ambos pesajes confirmados. No equivale a una evaluación completada ni clasificada.'
                  : 'Fotografías confirmadas. El pesaje sigue pendiente o incompleto: no se declara evaluación finalizada.'}
              </p>
              <div className="guided-acquisition__actions">
                <button type="button" className="action-button action-button--secondary" onClick={() => goTo(3)} disabled={processing}>Volver a imágenes</button>
                <button type="button" className="action-button action-button--primary" disabled={processing || !hasConfirmedImages(imageCount)} onClick={() => goTo(5)}>
                  {outcome === 'confirmed' ? 'Continuar a retiro' : 'Retiro con pesaje pendiente'} <Icon name="arrow-right" size={17} />
                </button>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="guided-acquisition__stage">
              <h3>5. Retirar la pieza</h3>
              <p>Retira físicamente la fruta de la zona de captura y deja disponible la estación para la siguiente pieza.</p>
              <label className="guided-acquisition__check">
                <input type="checkbox" checked={retired} onChange={(event) => setRetired(event.target.checked)} />
                Confirmo que retiré manualmente la pieza.
              </label>
              <p className="guided-acquisition__notice" role="status">
                {outcome === 'confirmed' ? 'Adquisición confirmada' : 'Adquisición parcial'}.
                Esta guía no cambia el estado «En proceso» en SQLite ni genera resultados de clasificación.
              </p>
              <div className="guided-acquisition__actions">
                <button type="button" className="action-button action-button--secondary" onClick={() => goTo(4)}>Volver a confirmación</button>
                <button type="button" className="action-button action-button--primary" disabled={!retired} onClick={onNextEvaluation}>Terminar recorrido e iniciar otra pieza</button>
                <Link className="action-button action-button--secondary" to={`/historial/${encodeURIComponent(evaluation.id)}`}>Ver registro en historial</Link>
              </div>
            </div>
          )}

          {error && <p className="guided-acquisition__error" role="alert">{error}</p>}
        </>
      )}
    </section>
  )
}
