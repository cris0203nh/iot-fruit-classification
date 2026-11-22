import { ApiDataError, request } from '../../services/agroscanApi.ts'
import { parsePlan, type Plan } from './commercialApi.ts'

export const APPLICATION_MESSAGE = 'Solicitud recibida, pendiente de revisión'
export type ApplicationStatus = 'pending' | 'under_review' | 'approved' | 'rejected'
export const APPLICATION_STATES: Record<ApplicationStatus, string> = { pending: 'Pendiente', under_review: 'En revisión', approved: 'Aprobada', rejected: 'Rechazada' }
export type ApplicationInput = { companyName: string; contactName: string; contactEmail: string;
  requestedPlanId: number; requestedPeriod: 'monthly' | 'annual'; idempotencyKey: string }
export type NotificationStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'disabled' | 'not_requested'
export const NOTIFICATION_MESSAGES: Record<NotificationStatus, string> = {
  disabled: 'El correo al propietario está deshabilitado. Tu solicitud está guardada y visible en su panel.',
  pending: 'Tu solicitud está guardada. La notificación al propietario está pendiente.',
  sending: 'Tu solicitud está guardada. El resultado de la notificación aún no está confirmado; no envíes otra solicitud.',
  sent: 'El servidor de correo aceptó la notificación al propietario. Esto no confirma su recepción en el buzón.',
  failed: 'Tu solicitud está guardada y visible en el panel, pero no se pudo confirmar la notificación por correo. No envíes otra solicitud.',
  not_requested: 'Solicitud conservada en el panel. No se generó un aviso de correo para este registro anterior.',
}
export type ApplicationReceipt = { id: string; status: 'pending'; message: string; ownerNotification?: NotificationStatus }
export type ApplicationDecision = { id: number; action: 'review' | 'approve' | 'reject'; reason: string; actorUserId: number; createdAt: string; organizationId: number | null }
export type DecisionInput = { action: ApplicationDecision['action']; reason: string; idempotencyKey: string; approvedPlanId?: number; existingOrganizationId?: number; identityConfirmed?: boolean }
export type InitialInvitation = { id: number; email: string; role: 'administrador'; source: 'platform_owner'; status: 'pending' | 'accepted' | 'expired' | 'revoked'; expiresAt: string; createdAt: string; acceptedAt: string | null; acceptedBy: number | null; revokedAt: string | null; revokedBy: number | null }
export type CommercialApplication = Omit<ApplicationInput, 'idempotencyKey'> & { id: string; status: ApplicationStatus; createdAt: string; source: string; plan: Plan;
  organizationId?: number | null; provisioningState?: 'not_provisioned' | 'awaiting_admin' | 'awaiting_demo_order' | 'completed'; decisions?: ApplicationDecision[];
  commercialOrderId?: string | null; commercialSubscriptionId?: number | null;
  initialInvitation?: InitialInvitation | null; administratorActive?: boolean; ownerNotification?: NotificationStatus }
function object(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null }
function parseInitialInvitation(value: unknown): InitialInvitation {
  if (!object(value) || !Number.isSafeInteger(value.id) || typeof value.email !== 'string' || value.role !== 'administrador'
    || value.source !== 'platform_owner' || !['pending','accepted','expired','revoked'].includes(String(value.status))
    || typeof value.expiresAt !== 'string' || typeof value.createdAt !== 'string'
    || !['acceptedAt','revokedAt'].every(k => value[k] === null || typeof value[k] === 'string')
    || !['acceptedBy','revokedBy'].every(k => value[k] === null || Number.isSafeInteger(value[k]))) throw new ApiDataError()
  return value as InitialInvitation
}
function parseApplication(value: unknown): CommercialApplication {
  if (!object(value) || !['id','companyName','contactName','contactEmail','createdAt','source'].every(k => typeof value[k] === 'string')
    || !Object.hasOwn(APPLICATION_STATES, String(value.status)) || !Number.isSafeInteger(value.requestedPlanId)
    || !['monthly','annual'].includes(String(value.requestedPeriod))) throw new ApiDataError()
  if (value.provisioningState !== undefined && !['not_provisioned','awaiting_admin','awaiting_demo_order','completed'].includes(String(value.provisioningState))) throw new ApiDataError()
  if (value.initialInvitation !== undefined && value.initialInvitation !== null) parseInitialInvitation(value.initialInvitation)
  if (value.administratorActive !== undefined && typeof value.administratorActive !== 'boolean') throw new ApiDataError()
  if (value.ownerNotification !== undefined && !Object.hasOwn(NOTIFICATION_MESSAGES,String(value.ownerNotification))) throw new ApiDataError()
  if (value.organizationId !== undefined && value.organizationId !== null && !Number.isSafeInteger(value.organizationId)) throw new ApiDataError()
  if (value.decisions !== undefined && (!Array.isArray(value.decisions) || !value.decisions.every(d => object(d)
    && Number.isSafeInteger(d.id) && Number.isSafeInteger(d.actorUserId) && ['review','approve','reject'].includes(String(d.action))
    && typeof d.reason === 'string' && typeof d.createdAt === 'string' && (d.organizationId === null || Number.isSafeInteger(d.organizationId))))) throw new ApiDataError()
  return { ...value, plan: parsePlan(value.plan) } as CommercialApplication
}
export async function submitApplication(input: ApplicationInput): Promise<ApplicationReceipt> {
  const result = await request('/api/commercial/applications', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
  if (!object(result) || typeof result.id !== 'string' || result.status !== 'pending' || result.message !== APPLICATION_MESSAGE) throw new ApiDataError()
  if (result.ownerNotification !== undefined && !Object.hasOwn(NOTIFICATION_MESSAGES,String(result.ownerNotification))) throw new ApiDataError()
  return result as ApplicationReceipt
}
export async function listApplications(filters: { status?: ApplicationStatus; planId?: number; offset?: number } = {}) {
  const query = new URLSearchParams({ limit: '20', offset: String(filters.offset ?? 0) })
  if (filters.status) query.set('status', filters.status)
  if (filters.planId) query.set('plan_id', String(filters.planId))
  const result = await request('/api/platform/commercial/applications?' + query)
  if (!object(result) || !Array.isArray(result.items) || !Number.isSafeInteger(result.total)
    || !Number.isSafeInteger(result.offset) || result.limit !== 20) throw new ApiDataError()
  const items = result.items.map(parseApplication)
  return { items, total: result.total as number, offset: result.offset as number, limit: 20 }
}

export async function decideApplication(id: string, input: DecisionInput) {
  const result = parseApplication(await request(`/api/platform/commercial/applications/${encodeURIComponent(id)}/decision`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  }))
  const expected = { review: 'under_review', approve: 'approved', reject: 'rejected' }[input.action]
  if (result.id !== id || result.status !== expected || !result.decisions?.some(d => d.action === input.action)
    || (input.action === 'approve' && (!['awaiting_admin','awaiting_demo_order','completed'].includes(result.provisioningState ?? '') || !result.organizationId))) throw new ApiDataError()
  return result
}

export async function applicationOrganizations() {
  const result = await request('/api/platform/organizations')
  if (!Array.isArray(result) || !result.every(o => object(o) && Number.isSafeInteger(o.id) && typeof o.name === 'string' && typeof o.isActive === 'boolean')) throw new ApiDataError()
  return result as { id: number; name: string; isActive: boolean }[]
}

export async function manageInitialInvitation(applicationId: string, input: { action: 'issue' | 'reissue' | 'revoke'; idempotencyKey: string }) {
  const result = await request(`/api/platform/commercial/applications/${encodeURIComponent(applicationId)}/administrator-invitation`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  })
  if (!object(result) || (result.token !== undefined && (typeof result.token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(result.token)))) throw new ApiDataError()
  if (input.action === 'revoke' && result.token !== undefined) throw new ApiDataError()
  return { invitation: parseInitialInvitation(result.invitation), token: result.token as string | undefined }
}
