import type { IotStatus } from '../../services/agroscanApi'

/** El backend utiliza 10 segundos para determinar si la lectura sigue vigente. */
export const WEIGHT_FRESH_MS = 10_000

export type WeightView = {
  state: 'waiting' | 'stable' | 'unstable' | 'stale' | 'offline' | 'error'
  label: string
  description: string
  weightG: number | null
  receivedAt: string | null
  deviceId: string | null
}

const emptyView = (state: WeightView['state'], label: string, description: string, receivedAt: string | null = null): WeightView =>
  ({ state, label, description, weightG: null, receivedAt, deviceId: null })

export function weightConnectionError(): WeightView {
  return emptyView('error', 'Sin conexión con la API', 'No hay lectura actual verificable. Revisa FastAPI o la red local.')
}

/**
 * No retiene pesos anteriores. Una desconexión o falta de muestras anula inmediatamente
 * el dato mostrado. También aplica un vencimiento local mientras se espera el próximo poll.
 */
export function deriveWeightView(status: IotStatus | null, elapsedSinceFetchMs = 0): WeightView {
  if (status === null) return emptyView('waiting', 'Consultando sensor', 'Esperando el estado del backend local.')
  if (!status.online) {
    return status.receivedAt
      ? emptyView('stale', 'Lectura vencida o sensor sin datos', 'No hay peso vigente; la lectura anterior no se reutiliza.', status.receivedAt)
      : emptyView('offline', 'Sin lecturas', 'Todavía no se ha recibido una muestra del ESP32.', null)
  }
  // Defensa adicional por si el servidor no vuelve a responder durante la siguiente consulta.
  const elapsed = Math.max(0, elapsedSinceFetchMs)
  if (status.ageSeconds === null || status.ageSeconds * 1000 + elapsed >= WEIGHT_FRESH_MS) {
    return emptyView('stale', 'Lectura vencida', 'No llegó una nueva muestra dentro de la ventana de 10 segundos.', status.receivedAt)
  }
  if (status.weightG === null || status.stable === null) {
    return emptyView('error', 'Lectura inválida', 'La API no proporcionó un peso vigente interpretable.')
  }
  return {
    state: status.stable ? 'stable' : 'unstable',
    label: status.stable ? 'Estable' : 'Inestable',
    description: status.stable
      ? 'Lectura reciente de la API. La calibración física aún debe verificarse.'
      : 'Lectura reciente, pero no estable. No debe registrarse como peso válido.',
    weightG: status.weightG,
    receivedAt: status.receivedAt,
    deviceId: status.deviceId,
  }
}
