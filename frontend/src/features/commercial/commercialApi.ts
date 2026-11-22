import { ApiDataError, request } from '../../services/agroscanApi.ts'

export const DEMO_NOTICE = 'Pago simulado — No se realizó ningún cobro'
export type Plan = { id: number; code: string; version: number; name: string; description: string;
  amountCents: number; currency: 'PEN'; period: 'monthly' | 'annual'; benefits: string[];
  limits: Record<string, number>; isActive: boolean; recommended: boolean; demo: true;
  displayOrder?: number; state?: 'draft' | 'active' | 'inactive'; createdAt?: string | null;
  publishedAt?: string | null; createdBy?: number | null; changeNote?: string }
export type Order = { id: string; organizationId: number; plan: Plan; amountCents: number;
  status: 'pending' | 'demo_approved' | 'demo_rejected' | 'cancelled'; action: 'subscribe' | 'change' | 'renew';
  createdAt: string; notice: string; expiresAt?: string; isExpired?: boolean }
export type Subscription = { id: number; organizationId: number; plan: Plan; status: 'active' | 'cancelled' | 'expired';
  startsAt: string; endsAt: string; notice: string; graceEndsAt?: string | null; inGracePeriod?: boolean; cancellationEffect?: 'immediate' }
export type CommerceOnboarding = { applicationId: string; organizationId: number; stage: 'awaiting_admin' | 'awaiting_demo_order' | 'completed';
  approvedPlan: Plan; approvedPlanAvailable: boolean; invitationId: number | null; orderId: string | null; subscriptionId: number | null }
export type Transaction = { id: number; organizationId: number; orderId: string | null; outcome: string;
  amountCents: number; createdAt: string; notice: string }
export type CompanyCommerce = { subscription: Subscription | null; orders: Order[]; transactions: Transaction[];
  simulatorEnabled: boolean; notice: string; onboarding?: CommerceOnboarding | null }
export type CommercialOverview = { activeDemoSubscriptions: number; expiringSoon: number; activePlans: number;
  simulatedTotalCents: number; subscriptions: Subscription[]; orders: Order[]; transactions: Transaction[]; notice: string; onboardings?: CommerceOnboarding[] }
export type PlanInput = Pick<Plan, 'code' | 'name' | 'description' | 'amountCents' | 'currency' | 'period' | 'benefits' | 'limits' | 'recommended'> & {
  displayOrder?: number; publish?: boolean; expectedVersion?: number; idempotencyKey?: string; changeNote?: string }
export type Scenario = 'approve' | 'reject' | 'cancel'

function object(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null }
export function parsePlan(value: unknown): Plan {
  if (!object(value) || !Number.isSafeInteger(value.id) || (value.id as number) < 1
    || !Number.isSafeInteger(value.version) || (value.version as number) < 1
    || !Number.isSafeInteger(value.amountCents) || (value.amountCents as number) < 0
    || value.currency !== 'PEN' || !['monthly', 'annual'].includes(String(value.period))
    || !['code', 'name', 'description'].every(key => typeof value[key] === 'string')
    || !Array.isArray(value.benefits) || !value.benefits.every(v => typeof v === 'string')
    || !object(value.limits) || !Object.values(value.limits).every(v => Number.isSafeInteger(v) && (v as number) >= 0)
    || typeof value.isActive !== 'boolean' || typeof value.recommended !== 'boolean' || value.demo !== true
    || (value.displayOrder !== undefined && (!Number.isSafeInteger(value.displayOrder) || (value.displayOrder as number) < 0))
    || (value.state !== undefined && !['draft', 'active', 'inactive'].includes(String(value.state)))
    || ['createdAt', 'publishedAt'].some(key => value[key] !== undefined && value[key] !== null &&
      (typeof value[key] !== 'string' || !Number.isFinite(Date.parse(value[key] as string))))) throw new ApiDataError()
  return value as Plan
}
function parseOrder(value: unknown): Order {
  if (!object(value) || typeof value.id !== 'string' || !Number.isSafeInteger(value.organizationId)
    || !['pending', 'demo_approved', 'demo_rejected', 'cancelled'].includes(String(value.status))
    || !['subscribe', 'change', 'renew'].includes(String(value.action)) || value.notice !== DEMO_NOTICE
    || typeof value.createdAt !== 'string') throw new ApiDataError()
  const plan = parsePlan(value.plan)
  if ((value.expiresAt !== undefined && typeof value.expiresAt !== 'string') || (value.isExpired !== undefined && typeof value.isExpired !== 'boolean')) throw new ApiDataError()
  if (value.amountCents !== plan.amountCents) throw new ApiDataError()
  return { ...value, plan } as Order
}
function parseSubscription(value: unknown): Subscription | null {
  if (value === null) return null
  if (!object(value) || !['active', 'cancelled', 'expired'].includes(String(value.status))
    || !Number.isSafeInteger(value.organizationId) || typeof value.startsAt !== 'string'
    || typeof value.endsAt !== 'string' || value.notice !== DEMO_NOTICE) throw new ApiDataError()
  if ((value.graceEndsAt !== undefined && value.graceEndsAt !== null && typeof value.graceEndsAt !== 'string')
    || (value.inGracePeriod !== undefined && typeof value.inGracePeriod !== 'boolean')
    || (value.cancellationEffect !== undefined && value.cancellationEffect !== 'immediate')) throw new ApiDataError()
  if (value.inGracePeriod === true && (value.status !== 'expired' || typeof value.graceEndsAt !== 'string')) throw new ApiDataError()
  return { ...value, plan: parsePlan(value.plan) } as Subscription
}
function parseOnboarding(value: unknown): CommerceOnboarding | null {
  if (value === null) return null
  if (!object(value) || typeof value.applicationId !== 'string' || !Number.isSafeInteger(value.organizationId)
    || !['awaiting_admin','awaiting_demo_order','completed'].includes(String(value.stage)) || typeof value.approvedPlanAvailable !== 'boolean'
    || !['invitationId','subscriptionId'].every(k => value[k] === null || Number.isSafeInteger(value[k]))
    || (value.orderId !== null && typeof value.orderId !== 'string')) throw new ApiDataError()
  if (value.stage === 'completed' && (!value.orderId || !value.subscriptionId || !value.invitationId)) throw new ApiDataError()
  return { ...value, approvedPlan: parsePlan(value.approvedPlan) } as CommerceOnboarding
}
function parseTransactions(value: unknown): Transaction[] {
  if (!Array.isArray(value) || value.some(v => !object(v) || v.notice !== DEMO_NOTICE
    || !Number.isSafeInteger(v.amountCents) || typeof v.outcome !== 'string')) throw new ApiDataError()
  return value as Transaction[]
}
const body = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })
export const money = (cents: number) => new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(cents / 100)
export async function getCatalog() {
  const data = await request('/api/commercial/plans')
  if (!object(data) || !Array.isArray(data.plans) || typeof data.simulatorEnabled !== 'boolean' || data.notice !== DEMO_NOTICE) throw new ApiDataError()
  return { plans: data.plans.map(parsePlan), simulatorEnabled: data.simulatorEnabled }
}
export async function getCompanyCommerce(): Promise<CompanyCommerce> {
  const data = await request('/api/commercial/subscription')
  if (!object(data) || !Array.isArray(data.orders) || typeof data.simulatorEnabled !== 'boolean' || data.notice !== DEMO_NOTICE) throw new ApiDataError()
  return { subscription: parseSubscription(data.subscription), orders: data.orders.map(parseOrder),
    transactions: parseTransactions(data.transactions), simulatorEnabled: data.simulatorEnabled, notice: DEMO_NOTICE,
    ...(data.onboarding !== undefined ? { onboarding: parseOnboarding(data.onboarding) } : {}) }
}
export async function createDemoOrder(planId: number, action: Order['action'], idempotencyKey: string, acceptUpdatedPlan = false) {
  return parseOrder(await request('/api/commercial/orders', body({ planId, action, idempotencyKey, ...(acceptUpdatedPlan ? { acceptUpdatedPlan: true } : {}) })))
}
export async function confirmDemoOrder(id: string, scenario: Scenario) {
  return parseOrder(await request(`/api/commercial/orders/${encodeURIComponent(id)}/confirm`, body({ scenario })))
}
export async function cancelDemoSubscription() {
  return parseSubscription(await request('/api/commercial/subscription/cancel', body({})))
}
export async function listCommercialPlans() {
  const data = await request('/api/platform/commercial/plans')
  if (!Array.isArray(data)) throw new ApiDataError()
  return data.map(parsePlan)
}
export async function saveCommercialPlan(input: PlanInput) {
  return parsePlan(await request('/api/platform/commercial/plans', body(input)))
}
export async function getCommercialPlanVersions(id: number) {
  const data = await request(`/api/platform/commercial/plans/${id}/versions`)
  if (!Array.isArray(data)) throw new ApiDataError()
  return data.map(parsePlan)
}
export async function setCommercialPlanStatus(id: number, isActive: boolean) {
  return parsePlan(await request(`/api/platform/commercial/plans/${id}/status`, { ...body({ isActive }), method: 'PATCH' }))
}
export async function getCommercialOverview(): Promise<CommercialOverview> {
  const data = await request('/api/platform/commercial/overview')
  if (!object(data) || !Array.isArray(data.orders) || !Array.isArray(data.subscriptions) || data.notice !== DEMO_NOTICE
    || !['activeDemoSubscriptions', 'expiringSoon', 'activePlans', 'simulatedTotalCents'].every(k => Number.isSafeInteger(data[k]))) throw new ApiDataError()
  if (data.onboardings !== undefined && !Array.isArray(data.onboardings)) throw new ApiDataError()
  return { ...data, orders: data.orders.map(parseOrder), subscriptions: data.subscriptions.map(parseSubscription),
    transactions: parseTransactions(data.transactions), ...(Array.isArray(data.onboardings) ? { onboardings: data.onboardings.map(v => { const item = parseOnboarding(v); if (!item) throw new ApiDataError(); return item }) } : {}) } as CommercialOverview
}
