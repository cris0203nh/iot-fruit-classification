
import { useEffect, useState } from 'react'
import { Icon } from '../../components/layout/Icon'
import {
  ApiResponseError,
  captureWeightPre,
  captureWeightPost,
  getIotStatus,
  type IotStatus,
  type WeightStep,
} from '../../services/agroscanApi'
import {
  deriveWeightView,
  weightConnectionError,
  type WeightView,
} from './weightReading'
import './WeightCaptureCard.css'

const POLL_MS = 2000

type ReadingState = {
  status: IotStatus | null
  fetchedAt: number
  failed: boolean
}

type Props = {
  evaluationId: string
  onComplete?: (complete: boolean) => void
}

function formatWeight(value: number | null): string {
  if (value === null) return 'â€” g'

  return `${new Intl.NumberFormat('es-PE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)} g`
}

function formatTime(value: string | null): string {
  if (!value) return 'Sin registro'

  return new Date(value).toLocaleString('es-PE', {
    dateStyle: 'short',
    timeStyle: 'medium',
  })
}

export function WeightCaptureCard({ evaluationId, onComplete }: Props) {
  const [reading, setReading] = useState<ReadingState>({
    status: null,
    fetchedAt: 0,
    failed: false,
  })

  const [clock, setClock] = useState(() => Date.now())
  const [preStep, setPreStep] = useState<WeightStep | null>(null)
  const [postStep, setPostStep] = useState<WeightStep | null>(null)
  const [working, setWorking] = useState<'pre' | 'post' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    onComplete?.(Boolean(preStep && postStep))
  }, [preStep, postStep, onComplete])

  useEffect(() => {
    let active = true
    let timeout: ReturnType<typeof setTimeout> | undefined

    const clockTimer = setInterval(() => {
      setClock(Date.now())
    }, 1000)

    async function refresh() {
      try {
        const status = await getIotStatus()

        if (active) {
          setReading({
            status,
            fetchedAt: Date.now(),
            failed: false,
          })
        }
      } catch {
        if (active) {
          setReading({
            status: null,
            fetchedAt: Date.now(),
            failed: true,
          })
        }
      } finally {
        if (active) {
          timeout = setTimeout(refresh, POLL_MS)
        }
      }
    }

    void refresh()

    return () => {
      active = false
      clearTimeout(timeout)
      clearInterval(clockTimer)
    }
  }, [])

  const view: WeightView = reading.failed
    ? weightConnectionError()
    : deriveWeightView(
        reading.status,
        clock - reading.fetchedAt,
      )

  const hasNewReading = Boolean(
    preStep
    && view.receivedAt
    && Date.parse(view.receivedAt) > Date.parse(preStep.receivedAt),
  )

  const sameDevice = Boolean(
    preStep
    && view.deviceId === preStep.deviceId,
  )

  const canCapturePre =
    view.state === 'stable'
    && preStep === null
    && working === null

  const canCapturePost =
    view.state === 'stable'
    && preStep !== null
    && postStep === null
    && hasNewReading
    && sameDevice
    && working === null

  async function registerPre() {
    if (!canCapturePre) return

    setWorking('pre')
    setError(null)

    try {
      const result = await captureWeightPre(evaluationId)
      setPreStep(result)
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'No fue posible registrar el peso inicial.',
      )
    } finally {
      setWorking(null)
    }
  }

  async function registerPost() {
    if (!canCapturePost) return

    setWorking('post')
    setError(null)

    try {
      const result = await captureWeightPost(evaluationId)
      setPostStep(result)
    } catch (failure) {
      setError(
        failure instanceof ApiResponseError
          ? failure.message
          : failure instanceof Error
            ? failure.message
            : 'No fue posible confirmar el peso final.',
      )
    } finally {
      setWorking(null)
    }
  }

  return (
    <div className="evaluation-acquisition__card weight-card weight-capture">

      <div className="evaluation-acquisition__top">
        <Icon name="scale" size={21} />
        <strong>Pesaje ESP32 + HX711</strong>
      </div>

      <div
        className={`weight-card__state weight-card__state--${view.state}`}
        role="status"
        aria-live="polite"
      >
        <strong className="weight-card__value">
          {formatWeight(view.weightG)}
        </strong>

        <span className="weight-card__badge">
          {view.label}
        </span>
      </div>

      <p className="weight-card__description">
        {view.description}
      </p>

      <dl className="weight-card__meta">
        <div>
          <dt>Ãšltima lectura</dt>
          <dd>{formatTime(view.receivedAt)}</dd>
        </div>

        <div>
          <dt>Dispositivo</dt>
          <dd>{view.deviceId ?? 'Sin dispositivo vigente'}</dd>
        </div>
      </dl>

      <div className="weight-capture__steps">

        <section className="weight-capture__step">
          <div className="weight-capture__step-heading">
            <strong>1. Peso inicial</strong>

            {preStep ? (
              <span className="weight-capture__success">
                <Icon name="info" size={15} />
                Registrado
              </span>
            ) : (
              <span className="weight-capture__pending">
                Pendiente
              </span>
            )}
          </div>

          <strong className="weight-capture__registered">
            {formatWeight(preStep?.weightG ?? null)}
          </strong>

          <button
            type="button"
            className="action-button action-button--primary"
            onClick={registerPre}
            disabled={!canCapturePre}
          >
            {working === 'pre'
              ? 'Registrando...'
              : 'Registrar peso inicial'}
          </button>
        </section>

        <section className="weight-capture__step">
          <div className="weight-capture__step-heading">
            <strong>2. Peso de confirmaciÃ³n</strong>

            {postStep ? (
              <span className="weight-capture__success">
                <Icon name="info" size={15} />
                Registrado
              </span>
            ) : (
              <span className="weight-capture__pending">
                Pendiente
              </span>
            )}
          </div>

          <strong className="weight-capture__registered">
            {formatWeight(postStep?.weightG ?? null)}
          </strong>

          <button
            type="button"
            className="action-button action-button--primary"
            onClick={registerPost}
            disabled={!canCapturePost}
          >
            {working === 'post'
              ? 'Confirmando...'
              : 'Confirmar peso final'}
          </button>

          {preStep && !postStep && !hasNewReading && (
            <p className="weight-capture__hint">
              Esperando una nueva lectura posterior al peso inicial.
            </p>
          )}

          {preStep && !postStep && !sameDevice && (
            <p className="weight-capture__hint">
              Verifica que siga conectado el mismo dispositivo.
            </p>
          )}
        </section>

      </div>

      {error && (
        <div className="weight-capture__error" role="alert">
          <Icon name="alert" size={17} />
          <span>{error}</span>
        </div>
      )}

      {postStep && (
        <div className="weight-capture__completed" role="status">
          <Icon name="info" size={18} />
          <div>
            <strong>Ambas etapas de pesaje registradas.</strong>
            <p>Los dos registros fueron confirmados por FastAPI.</p>
          </div>
        </div>
      )}

      <p className="weight-card__notice">
        El registro requiere una lectura estable, vigente y con
        cero confirmado por el backend.
      </p>

      <p className="weight-card__origin">
        La lectura mostrada no acredita por sÃ­ sola que el sensor
        fÃ­sico estÃ© calibrado ni que la mediciÃ³n provenga del hardware real.
      </p>

    </div>
  )
}
