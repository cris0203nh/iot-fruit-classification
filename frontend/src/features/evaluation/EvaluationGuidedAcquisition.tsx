
import { useCallback, useEffect, useRef, useState } from 'react'
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
  getEvaluationById, getV2QualityStatus, analyzeV2Quality,
  getQualityModelStatus, analyzeQualityProposal,
  type AcquisitionConfirmation,
  type WeightStep,
} from '../../services/agroscanApi'
import type { EvaluationDetail } from '../history/historyService'
import { runAutomaticQuality, type AutomaticQualityResult } from '../quality/automaticQuality.ts'
import {
  acquisitionOutcome,
  hasConfirmedImages,
  MIN_CONFIRMED_IMAGES,
  resolveAcquisitionProcessStatus,
  type GuidedStep,
} from './evaluationFlow'
import './EvaluationGuidedAcquisition.css'

type AcquisitionStep = 2 | 3 | 4 | 5

type Props = {
  evaluation: EvaluationDetail | null
  onStepChange: (value: GuidedStep) => void
  onNextEvaluation: () => void
}

function operationError(failure: unknown): string {
  if (failure instanceof ApiConnectionError) {
    return 'No se confirmó la operación por falta de conexión. Reintenta o solicita ayuda al administrador.'
  }

  if (failure instanceof ApiResponseError) {
    if (failure.status === 401 || failure.status === 403) {
      return 'Acceso no autorizado o sesión vencida. Inicia sesión nuevamente.'
    }

    return failure.message
  }

  return failure instanceof Error
    ? failure.message
    : 'No se pudo confirmar la operación.'
}

function WeightResult({
  result,
  name,
}: {
  result: WeightStep
  name: string
}) {
  return (
    <p className="guided-acquisition__success" role="status">
      <Icon name="info" size={17} /> {name} confirmado:{' '}
      <strong>{result.weightG} g</strong>
      <span> · {result.deviceId}</span>
    </p>
  )
}

/**
 * AGROP-50:
 * Coordina el procedimiento de adquisición de una pieza.
 * Los estados de confirmación se muestran únicamente cuando FastAPI
 * devuelve una respuesta válida. Este componente no genera clasificaciones.
 */
export function EvaluationGuidedAcquisition({
  evaluation,
  onStepChange,
  onNextEvaluation,
}: Props) {
  const [step, setStep] = useState<AcquisitionStep>(2)
  const [pre, setPre] = useState<WeightStep | null>(null)
  const [post, setPost] = useState<WeightStep | null>(null)
  const [imageCount, setImageCount] = useState(
    evaluation?.evidence.length ?? 0,
  )
  const [processing, setProcessing] = useState(false)
  const [serverConfirmation, setServerConfirmation] =
    useState<AcquisitionConfirmation | null>(null)

  const busy = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [retired, setRetired] = useState(false)
  const [qualityRunning, setQualityRunning] = useState(false)
  const [automaticQuality, setAutomaticQuality] = useState<AutomaticQualityResult | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (evaluation) headingRef.current?.focus()
  }, [evaluation, step])

  const onEvidenceChange = useCallback((count: number) => {
    setImageCount(count)
    setServerConfirmation(null)
    setAutomaticQuality(null)

  }, [])

  function goTo(next: AcquisitionStep) {
    if (processing || busy.current) return

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

  // AGROP-50: estado coherente del procedimiento.
  const status = resolveAcquisitionProcessStatus({
    hasError: Boolean(error),
    processing,
    confirmed: acquisitionConfirmed,
    capturing: step === 3,
  })

  const statusLabels = {
    ready: readyToConfirm ? 'Listo para confirmar' : 'Listo',
    capturing: 'Capturando',
    processing: 'Procesando',
    pending: 'Pendiente de revisión',
    error: 'Error',
  }

  const processStatus = statusLabels[status]

  const processStatusClass =
    status === 'error'
      ? 'guided-acquisition__error'
      : status === 'pending' || status === 'processing'
        ? 'guided-acquisition__notice'
        : 'guided-acquisition__success'

  async function confirmAcquisitionWithBackend() {
    if (!evaluation || busy.current) return

    if (!pre || !post || !hasConfirmedImages(imageCount)) {
      setError(
        'No se puede confirmar: se requieren ambos pesajes válidos y al menos dos fotografías guardadas.',
      )
      return
    }

    busy.current = true
    setProcessing(true)
    setError(null)
    setServerConfirmation(null)

    try {
      const result = await confirmEvaluationAcquisition(evaluation.id)

      if (
        result.evaluationId !== evaluation.id ||
        result.pieceId !== evaluation.pieceId ||
        result.product !== evaluation.product
      ) {
        throw new Error(
          'La confirmación del backend no corresponde a la evaluación, pieza y producto seleccionados.',
        )
      }

      setServerConfirmation(result)
      // I02: ejecutar la inferencia solo DESPUÉS de confirmar dos fotos y el peso.
      // El backend conserva snapshots idempotentes; este flujo nunca registra un grado final.
      setAutomaticQuality(null)
      setQualityRunning(true)
      try {
        const outcome = await runAutomaticQuality(evaluation.id, {
          getEvaluationById, getV2QualityStatus, analyzeV2Quality,
          getQualityModelStatus, analyzeQualityProposal,
        })
        setAutomaticQuality(outcome)
      } finally {
        setQualityRunning(false)
      }

    } catch (failure) {
      setServerConfirmation(null)
      setError(operationError(failure))
    } finally {
      setProcessing(false)
      busy.current = false
    }
  }

  return (
    <section
      className="panel evaluation-acquisition"
      aria-labelledby="acquisition-heading"
    >
      <div className="evaluation-section-heading">
        <span
          className="evaluation-step evaluation-step--muted"
          aria-hidden="true"
        >
          {evaluation ? step : 2}
        </span>

        <div>
          <h2 id="acquisition-heading" ref={headingRef} tabIndex={-1}>{evaluation ? 'Evaluar la pieza' : 'Dos vistas de la misma fruta'}</h2>
        </div>
      </div>

      {!evaluation ? (
        <div className="guided-acquisition__start">
          <div className="guided-acquisition__views" aria-label="Dos fotografías obligatorias, pendientes de registro">
            <div><Icon name="camera" size={24} /><strong>Vista 1</strong><span>Frente de la fruta</span></div>
            <div><Icon name="camera" size={24} /><strong>Vista 2</strong><span>Otra cara de la misma fruta</span></div>
          </div>
          <p>Primero identifica la fruta y selecciona su lote. Después registra el peso y completa las dos vistas.</p>
          <p className="guided-acquisition__notice">Mantén la misma pieza durante el pesaje y las fotografías. Solo cuentan las vistas guardadas.</p>
        </div>
      ) : (
        <>
          <div className="guided-acquisition__identity">
            <span className={processStatusClass} role="status">
              {processStatus} · {imageCount} de {MIN_CONFIRMED_IMAGES} vistas · Peso inicial: {pre ? 'confirmado' : 'pendiente'}
            </span>
          </div>

          {step === 2 && (
            <div className="guided-acquisition__stage">
              <h3>2. Colocar la pieza y verificar el peso</h3>

              <p>
                Coloca la fruta en la balanza y espera una lectura estable. Se validan calibración y tara al registrar.
              </p>

              <div className="guided-acquisition__weighing">
                <WeightStatusCard />
                <div className="guided-acquisition__weight-actions">

                  {pre ? (
                    <WeightResult result={pre} name="Peso inicial" />
                  ) : (
                    <button
                      type="button"
                      className="action-button action-button--primary"
                      onClick={() => void confirmWeight('pre')}
                      disabled={processing}
                    >
                      {processing
                        ? 'Consultando peso…'
                        : 'Registrar peso inicial'}
                    </button>
                  )}

                  {!pre && (
                    <p className="guided-acquisition__notice">
                      Si no hay sensor válido, puedes continuar para guardar
                      fotografías; el pesaje permanecerá pendiente y no podrá
                      confirmarse la adquisición.
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
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="guided-acquisition__stage">
              <h3>3. Capturar fotografías RGB</h3>

              <p>
                Toma o sube dos fotografías de la misma fruta. Gírala para mostrar otra cara;
                no es necesario calibrar las medidas para continuar.
              </p>

              <div className="guided-acquisition__actions">
                <button
                  type="button"
                  className="action-button action-button--secondary"
                  onClick={() => goTo(2)}
                  disabled={processing}
                >
                  Volver a peso
                </button>

                <button
                  type="button"
                  className="action-button action-button--primary"
                  disabled={!hasConfirmedImages(imageCount) || processing}
                  onClick={() => goTo(4)}
                >
                  Continuar a confirmar peso
                  <Icon name="arrow-right" size={17} />
                </button>
              </div>

              <EvaluationImageCapture
                evaluationId={evaluation.id}
                onEvidenceChange={onEvidenceChange}
              />
            </div>
          )}

          {step === 4 && (
            <div className="guided-acquisition__stage">
              <h3>4. Confirmar peso y fotografías de la misma pieza</h3>

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
                  <dd>
                    {pre ? `${pre.weightG} g · confirmado` : 'Pendiente'}
                  </dd>
                </div>

                <div>
                  <dt>Peso final</dt>
                  <dd>
                    {post ? `${post.weightG} g · confirmado` : 'Pendiente'}
                  </dd>
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
                    {processing
                      ? 'Consultando peso…'
                      : 'Registrar peso de confirmación'}
                  </button>
                </>
              )}

              {post && (
                <WeightResult
                  result={post}
                  name="Peso de confirmación"
                />
              )}

              <p
                className={
                  acquisitionConfirmed
                    ? 'guided-acquisition__success'
                    : 'guided-acquisition__notice'
                }
                role="status"
              >
                {acquisitionConfirmed && serverConfirmation
                  ? `Se confirmó que el peso y las ${serverConfirmation.imageCount} fotografías pertenecen a la pieza ${serverConfirmation.pieceId} (${serverConfirmation.product}). Peso validado: ${serverConfirmation.weightGrams} g.`
                  : readyToConfirm
                    ? 'Los dos pesajes y las fotografías están disponibles. Falta confirmar su asociación con la pieza.'
                    : 'No se puede confirmar la adquisición hasta tener peso inicial, peso final y al menos dos fotografías guardadas.'}
              </p>

              <button
                type="button"
                className="action-button action-button--primary"
                disabled={
                  !readyToConfirm || processing || acquisitionConfirmed
                }
                onClick={() => void confirmAcquisitionWithBackend()}
              >
                {processing
                  ? 'Confirmando evaluación…'
                  : acquisitionConfirmed
                    ? 'Adquisición confirmada'
                    : 'Confirmar peso y fotografías'}
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
                Retira físicamente la fruta de la zona de captura y deja
                disponible la estación para la siguiente pieza.
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
                  ? 'Captura confirmada. Consulta la evaluación para ver resultados y revisiones.'
                  : 'Falta confirmar el pesaje y las fotografías.'}
              </p>

              <div className="guided-acquisition__actions">
                <button
                  type="button"
                  className="action-button action-button--secondary"
                  onClick={() => goTo(4)}
                  disabled={processing}
                >
                  Volver a confirmación
                </button>

                <button
                  type="button"
                  className="action-button action-button--primary"
                  disabled={
                    !retired || !acquisitionConfirmed || processing
                  }
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

          {acquisitionConfirmed && qualityRunning && (
            <p className="guided-acquisition__notice" role="status">Analizando las dos vistas con el clasificador disponible…</p>
          )}
          {acquisitionConfirmed && !qualityRunning && automaticQuality && (
            <p className={automaticQuality.status === 'suggested'
              ? 'guided-acquisition__success' : 'guided-acquisition__notice'} role="status">
              <strong>{automaticQuality.status === 'suggested'
                ? `Resultado preliminar: ${automaticQuality.grade}`
                : automaticQuality.status === 'no_model' ? 'Modelo E0/E1/E2 no disponible'
                : automaticQuality.status === 'needs_review' ? 'Revisión de calidad requerida'
                : 'No se pudo completar el análisis'}</strong>
              {' · '}{automaticQuality.message}
              {' '}<Link to={`/historial/${encodeURIComponent(evaluation.id)}`}>Ver resultado</Link>
            </p>
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
