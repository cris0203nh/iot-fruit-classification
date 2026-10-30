import { useEffect, useState } from 'react'
import { Icon } from '../../components/layout/Icon'
import { getIotStatus, type IotStatus } from '../../services/agroscanApi'
import { deriveWeightView, weightConnectionError, type WeightView } from './weightReading'
import './WeightStatusCard.css'

const POLL_MS = 2000

type ReadingState = { status: IotStatus | null; fetchedAt: number; failed: boolean }

function formatTime(iso: string | null): string {
  if (iso === null) return 'Sin lectura recibida'
  return new Date(iso).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'medium' })
}

function formatWeight(value: number | null): string {
  if (value === null) return '— g'
  return `${new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 }).format(value)} g`
}

export function WeightStatusCard() {
  const [reading, setReading] = useState<ReadingState>({ status: null, fetchedAt: 0, failed: false })
  const [clock, setClock] = useState(() => Date.now())

  useEffect(() => {
    let active = true
    let timeout: ReturnType<typeof setTimeout> | undefined
    const clockTimer = setInterval(() => setClock(Date.now()), 1000)

    async function refresh() {
      try {
        const status = await getIotStatus()
        if (active) setReading({ status, fetchedAt: Date.now(), failed: false })
      } catch {
        // Fail closed: nunca conservar el peso anterior al perder la conexión.
        if (active) setReading({ status: null, fetchedAt: Date.now(), failed: true })
      } finally {
        // Un solo request activo a la vez; la limpieza evita actualizaciones tras desmontar.
        if (active) timeout = setTimeout(refresh, POLL_MS)
      }
    }
    void refresh()
    return () => { active = false; clearTimeout(timeout); clearInterval(clockTimer) }
  }, [])

  const view: WeightView = reading.failed
    ? weightConnectionError()
    : deriveWeightView(reading.status, clock - reading.fetchedAt)
  const canUse = view.state === 'stable'

  return (
    <div className="evaluation-acquisition__card weight-card" aria-label="Peso actual desde la API IoT">
      <div className="evaluation-acquisition__top"><Icon name="scale" size={21} /><strong>Pesaje ESP32</strong></div>
      <div className={`weight-card__state weight-card__state--${view.state}`} role="status" aria-live="polite">
        <strong className="weight-card__value">{formatWeight(view.weightG)}</strong>
        <span className="weight-card__badge">{view.label}</span>
      </div>
      <p className="weight-card__description">{view.description}</p>
      <dl className="weight-card__meta">
        <div><dt>Recibida por la API</dt><dd>{formatTime(view.receivedAt)}</dd></div>
        <div><dt>Dispositivo</dt><dd>{view.deviceId ?? 'Sin dispositivo vigente'}</dd></div>
      </dl>
      <p className="weight-card__notice">
        {canUse
          ? 'Estado estable: apto únicamente para pruebas de visualización. No se registra automáticamente en la pieza.'
          : 'Peso no apto para registro. Revisa la lectura y reintenta cuando sea estable y reciente.'}
      </p>
      <p className="weight-card__origin">La API actual no indica si el dato proviene de simulación o del sensor real. No se acredita pesaje físico ni calibración.</p>
    </div>
  )
}
