
import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/layout/Icon'
import { EvaluationImageCapture } from '../capture/EvaluationImageCapture'
import { WeightStatusCard } from '../iot/WeightStatusCard'
import {
  ApiConnectionError,
  ApiResponseError,
  captureWeightPost,
  captureWeightPre,
  confirmEvaluationAcquisition,
  type AcquisitionConfirmation,
  type WeightStep,
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
export function EvaluationGuidedAcquisition({
  evaluation,
  onStepChange,
  onNextEvaluation,
}: Props) {
  const [step, setStep] = useState<AcquisitionStep>(2)
  const [pre, setPre] = useState<WeightStep | null>(null)
  const [post, setPost] = useState<WeightStep | null>(null)
  const [imageCount, setImageCount] = useState(evaluation?.evidence.length ?? 0)
  const [processing, setProcessing] = useState(false)
  const [serverConfirmation, setServerConfirmation] =
    useState<AcquisitionConfirmation | null>(null)

  const busy = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [retired, setRetired] = useState(false)

  const onEvidenceChange = useCallback((count: number) => {
    setImageCount(count)
    setServerConfirmation(null)
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
    setServerConfirmation(null)

    try {
      if (kind === 'pre') {
        const result = await captureWeightPre(evaluation.id)
        setPre(result)

        // Avanzar automaticamente al paso de fotografias.
        setStep(3)
        onStepChange(3)
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

  const readyToConfirm =
    outcome === 'confirmed' &&
    pre !== null &&
    post !== null &&
    hasConfirmedImages(imageCount)

  const acquisitionConfirmed =
    evaluation !== null &&
    serverConfirmation !== null &&
    serverConfirmation.evaluationId === evaluation.id &&
    serverConfirmation.pieceId === evaluation.pieceId &&
    serverConfirmation.product === evaluation.product

  /**
   * AGROP-34:
   * El frontend solicita la confirmación conjunta a FastAPI.
   * No muestra éxito hasta recibir y validar la respuesta real.
   */
  async function confirmAcquisitionWithBackend() {
    if (!evaluation || busy.current) return

    if (!pre || !post || !hasConfirmedImages(imageCount)) {
      setError(
        'No se puede confirmar: se requieren ambos pesajes válidos y al menos una fotografía guardada.',
      )
      return
    }

    busy.current = true
    setProcessing(true)
    setError(null)

    try {
      const result = await confirmEvaluationAcquisition(evaluation.id)

      if (
        result.pieceId !== evaluation.pieceId ||
        result.product !== evaluation.product
      ) {
        throw new Error(
          'La confirmación del backend no corresponde a la pieza y producto seleccionados.',
        )
      }

      setServerConfirmation(result)
    } catch (failure) {
      setServerConfirmation(null)
      setError(operationError(failure))
    } finally {
      setProcessing(false)
      busy.current = false
    }
  }

  return (
    <section className="panel evaluation-acquisition" aria-labelledby="acquisition-heading">
      <div className="evaluation-section-heading">
        <span className="evaluation-step evaluation-step--muted" aria-hidden="true">
          {evaluation ? step : 2}
        </span>
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
              <p>
                Coloca una sola fruta sobre la balanza y espera una lectura reciente y estable.
                FastAPI validará además la calibración y la tara.
              </p>

              <WeightStatusCard />

              {pre ? (
                <WeightResult result={pre} name="Peso inicial" />
              ) : (
                <button
                  type="button"
                  className="action-button action-button--primary"
                  onClick={() => void confirmWeight('pre')}
                  disabled={processing}
                >
                  {processing ? 'Consultando FastAPI…' : 'Registrar peso inicial'}
                </button>
              )}

              {!pre && (
                <p className="guided-acquisition__notice">
                  Si no hay sensor válido, puedes continuar para guardar fotografías;
                  el pesaje permanecerá pendiente y no podrá confirmarse la adquisición.
                </p>
              )}

              <button
                type="button"
                className="action-button action-button--secondary"
                onClick={() => goTo(3)}
                disabled={processing}
              >
                Continuar a imágenes <Icon name="arrow-right" size={17} />
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="guided-acquisition__stage">
              <h3>3. Capturar fotografías RGB</h3>
              <p>
                Fotografía la misma fruta. Si necesitas otra perspectiva,
                gírala manualmente sin crear otra evaluación.
              </p>

              <EvaluationImageCapture
                evaluationId={evaluation.id}
                autoStart={pre !== null}
                onEvidenceChange={onEvidenceChange}
              />

              <div className="guided-acquisition__actions">
                <button
                  type="button"
                  className="action-button action-button--secondary"
                  onClick={() => goTo(2)}
                >
                  Volver a peso
                </button>

                <button
                  type="button"
                  className="action-button action-button--primary"
                  disabled={!hasConfirmedImages(imageCount)}
                  onClick={() => goTo(4)}
                >
                  Continuar con {imageCount}{' '}
                  {imageCount === 1 ? 'imagen guardada' : 'imágenes guardadas'}
                  <Icon name="arrow-right" size={17} />
                </button>
              </div>

              {!hasConfirmedImages(imageCount) && (
                <p className="guided-acquisition__notice">
                  Para continuar, FastAPI debe confirmar al menos una fotografía.
                </p>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="guided-acquisition__stage">
              <h3>4. Confirmar peso y fotografía de la misma pieza</h3>

              <dl className="guided-acquisition__review">
                <div>
                  <dt>Evaluación</dt>
                  <dd>{evaluation.id}</dd>
                </div>
                <div>
                  <dt>Fotografías almacenadas</dt>
                  <dd>{imageCount}</dd>
                </div>
                <div>
                  <dt>Peso inicial</dt>
                  <dd>{pre ? `${pre.weightG} g · confirmado` : 'Pendiente'}</dd>
                </div>
                <div>
                  <dt>Peso final</dt>
                  <dd>{post ? `${post.weightG} g · confirmado` : 'Pendiente'}</dd>
                </div>
              </dl>

              {pre && !post && (
                <>
                  <p>
                    La pieza debe permanecer en la balanza para registrar
                    una nueva lectura de confirmación.
                  </p>

                  <WeightStatusCard />

                  <button
                    type="button"
                    className="action-button action-button--primary"
                    disabled={processing}
                    onClick={() => void confirmWeight('post')}
                  >
                    {processing ? 'Consultando FastAPI…' : 'Registrar peso de confirmación'}
                  </button>
                </>
              )}

              {post && (
                <WeightResult result={post} name="Peso de confirmación" />
              )}

              <p
                className={
                  acquisitionConfirmed
                    ? 'guided-acquisition__success'
                    : 'guided-acquisition__notice'
                }
                role="status"
              >
                {acquisitionConfirmed
                  ? `FastAPI confirmó que el peso y las ${serverConfirmation.imageCount} fotografías pertenecen a la pieza ${serverConfirmation.pieceId} (${serverConfirmation.product}). Peso validado: ${serverConfirmation.weightGrams} g.`
                  : readyToConfirm
                    ? 'Los dos pesajes y las fotografías están disponibles. Falta confirmar su asociación con FastAPI.'
                    : 'No se puede confirmar la adquisición hasta tener peso inicial, peso final y al menos una fotografía válida.'}
              </p>

              <button
                type="button"
                className="action-button action-button--primary"
                disabled={!readyToConfirm || processing || acquisitionConfirmed}
                onClick={() => void confirmAcquisitionWithBackend()}
              >
                {processing
                  ? 'Confirmando con FastAPI…'
                  : acquisitionConfirmed
                    ? 'Adquisición confirmada'
                    : 'Confirmar peso y fotografía'}
              </button>

              <div className="guided-acquisition__actions">
                <button
                  type="button"
                  className="action-button action-button--secondary"
                  onClick={() => goTo(3)}
                  disabled={processing}
                >
                  Volver a imágenes
                </button>

                <button
                  type="button"
                  className="action-button action-button--primary"
                  disabled={processing || !acquisitionConfirmed}
                  onClick={() => goTo(5)}
                >
                  Continuar a retiro <Icon name="arrow-right" size={17} />
                </button>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="guided-acquisition__stage">
              <h3>5. Retirar la pieza</h3>

              <p>
                Retira físicamente la fruta de la zona de captura
                y deja disponible la estación para la siguiente pieza.
              </p>

              <label className="guided-acquisition__check">
                <input
                  type="checkbox"
                  checked={retired}
                  onChange={(event) => setRetired(event.target.checked)}
                />
                Confirmo que retiré manualmente la pieza.
              </label>

              <p
                className={
                  acquisitionConfirmed
                    ? 'guided-acquisition__success'
                    : 'guided-acquisition__notice'
                }
                role="status"
              >
                {acquisitionConfirmed
                  ? 'Adquisición confirmada por FastAPI. Esta confirmación no genera resultados de clasificación.'
                  : 'La adquisición todavía no ha sido confirmada por el backend.'}
              </p>

              <div className="guided-acquisition__actions">
                <button
                  type="button"
                  className="action-button action-button--secondary"
                  onClick={() => goTo(4)}
                >
                  Volver a confirmación
                </button>

                <button
                  type="button"
                  className="action-button action-button--primary"
                  disabled={!retired || !acquisitionConfirmed}
                  onClick={onNextEvaluation}
                >
                  Terminar recorrido e iniciar otra pieza
                </button>

                <Link
                  className="action-button action-button--secondary"
                  to={`/historial/${encodeURIComponent(evaluation.id)}`}
                >
                  Ver registro en historial
                </Link>
              </div>
            </div>
          )}

          {error && (
            <p className="guided-acquisition__error" role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </section>
  )
}
