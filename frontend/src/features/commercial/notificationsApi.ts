import { ApiDataError, request } from '../../services/agroscanApi.ts'

export const notificationEvents: Record<string, string> = {
  application_received: 'Solicitud recibida', application_approved: 'Solicitud aprobada', application_rejected: 'Solicitud rechazada',
  administrator_invited: 'Invitación preparada', administrator_activated: 'Acceso incorporado', subscription_activated: 'Activación DEMO',
  subscription_renewed: 'Renovación DEMO', subscription_changed: 'Cambio de plan DEMO', subscription_expiring: 'Próximo vencimiento',
  subscription_expired: 'Vencimiento', subscription_cancelled: 'Cancelación DEMO',
}
export const notificationStates: Record<string, string> = { pending: 'Pendiente', processing: 'Procesando / resultado por confirmar',
  smtp_accepted: 'Aceptada por SMTP', retry_pending: 'Pendiente de reintento', failed: 'Fallida', omitted: 'Omitida' }
export type Notification = { id: string; organizationId: number | null; event: string; reference: string; recipient: string | null;
  subject: string; status: string; attempts: number; createdAt: string; lastAttemptAt: string | null;
  nextAttemptAt: string | null; smtpAcceptedAt: string | null; errorCode: string | null }
export type NotificationOverview = { items: Notification[]; total: number; statistics: Record<string, number>;
  smtp: { enabled: boolean; configured: boolean; reason: string | null }; maxAttempts: number; organizations: { id: number; name: string }[] }
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
function parseNotification(value: unknown): Notification {
  if (!object(value) || !['id', 'reference', 'subject', 'createdAt'].every(k => typeof value[k] === 'string')
    || !Object.hasOwn(notificationEvents, String(value.event)) || !Object.hasOwn(notificationStates, String(value.status))
    || !Number.isSafeInteger(value.attempts) || (value.attempts as number) < 0
    || !(value.organizationId === null || Number.isSafeInteger(value.organizationId))
    || !['recipient', 'errorCode'].every(k => value[k] === null || typeof value[k] === 'string')
    || !['lastAttemptAt', 'nextAttemptAt', 'smtpAcceptedAt'].every(k => value[k] === null || typeof value[k] === 'string' && Number.isFinite(Date.parse(value[k] as string)))
    || !Number.isFinite(Date.parse(value.createdAt as string))) throw new ApiDataError()
  return value as Notification
}
export async function getNotifications(filters: URLSearchParams): Promise<NotificationOverview> {
  const data = await request('/api/platform/notifications?' + filters.toString())
  if (!object(data) || !Array.isArray(data.items) || !Number.isSafeInteger(data.total) || (data.total as number) < 0
    || !object(data.smtp) || typeof data.smtp.enabled !== 'boolean' || typeof data.smtp.configured !== 'boolean'
    || !object(data.statistics) || !Object.values(data.statistics).every(v => Number.isSafeInteger(v) && (v as number) >= 0)
    || !Number.isSafeInteger(data.maxAttempts) || !Array.isArray(data.organizations) || !data.organizations.every(v => object(v) && Number.isSafeInteger(v.id) && typeof v.name === 'string')) throw new ApiDataError()
  return { ...data, items: data.items.map(parseNotification) } as NotificationOverview
}
export async function retryNotification(id: string) {
  return parseNotification(await request(`/api/platform/notifications/${encodeURIComponent(id)}/retry`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
  }, 40000))
}
export function notificationRetryEligible(row: Notification, maximum: number, current = Date.now()) {
  return ['pending', 'retry_pending'].includes(row.status) && row.attempts < maximum && (!row.nextAttemptAt || Date.parse(row.nextAttemptAt) <= current)
}
