import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getSessionRole, isPlatformOwner } from '../../services/agroscanApi'
import { DEMO_NOTICE, money, getCatalog, getCompanyCommerce, createDemoOrder, confirmDemoOrder,
  cancelDemoSubscription, getCommercialOverview, listCommercialPlans, saveCommercialPlan, setCommercialPlanStatus, getCommercialPlanVersions,
  type CompanyCommerce, type CommercialOverview, type Order, type Plan, type PlanInput, type Scenario, type Subscription } from './commercialApi.ts'
import './Commercial.css'
import { MetricCard } from '../../components/MetricCard'
import { PublicHeader } from '../../components/layout/PublicHeader'
import { Icon } from '../../components/layout/Icon'
import { PlanRequestLink } from './PlanRequestLink'

const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la operación. Reintenta.'
const date = (value: string) => new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(value))
const deadline = (value: string) => new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(value))
const states: Record<string, string> = { active: 'Activa DEMO', expired: 'Vencida', cancelled: 'Cancelada', pending: 'Pendiente de simulación',
  demo_approved: 'Simulación aprobada', demo_rejected: 'Simulación rechazada', subscription_cancelled: 'Suscripción cancelada' }
function Notice() { return <p className="commerce-notice" role="note">{DEMO_NOTICE}. Precios ilustrativos, no son tarifas comerciales aprobadas.</p> }
export function SubscriptionSummary() {
  const [data, setData] = useState<CompanyCommerce | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; getCompanyCommerce().then(data => { if (active) setData(data) },
    error => { if (active) setError(message(error)) }); return () => { active = false } }, [])
  return <section className="panel commerce-admin-link" aria-label="Resumen de suscripción"><div><h2>Plan de tu empresa</h2>
    {error ? <p role="alert">{error}</p> : !data ? <p role="status">Consultando plan…</p> : data.subscription
      ? <p>{data.subscription.plan.name} · {states[data.subscription.status]} · Vence {date(data.subscription.endsAt)}</p>
      : <p>Sin plan DEMO contratado. Tu operación continúa disponible.</p>}</div>
    <Link className="action-button action-button--secondary" to="/suscripcion">Gestionar suscripción DEMO</Link></section>
}
function ErrorNotice({ error }: { error: string }) { return error ? <p role="alert" className="commerce-error">{error}</p> : null }
export function PlanCard({ plan, children, headingAs: Heading = 'h2' }: { plan: Plan; children?: React.ReactNode; headingAs?: 'h2' | 'h3' }) {
  return <article className={`commerce-card ${plan.recommended ? 'commerce-card--recommended' : ''}`}>
    <p className="eyebrow">{plan.recommended ? 'Recomendado · DEMO' : 'Plan DEMO'} · v{plan.version}</p>
    <Heading>{plan.name}</Heading><p>{plan.description}</p>
    <p className="commerce-price">{money(plan.amountCents)} <small>/ {plan.period === 'annual' ? 'año' : 'mes'}</small></p>
    <ul>{plan.benefits.map((benefit, i) => <li key={i}>{benefit}</li>)}</ul>
    {Object.keys(plan.limits).length > 0 && <dl>{Object.entries(plan.limits).map(([key, limit]) => <div key={key}><dt>{key}</dt><dd>{limit}</dd></div>)}</dl>}
    <p className="commerce-muted">Límites referenciales: no restringen las operaciones existentes durante la demostración.</p>{children}
  </article>
}

export function PlanActions({ plan, enabled }: { plan: Plan; enabled: boolean }) {
  return <><PlanRequestLink plan={plan} />
    {isPlatformOwner() ? <Link to="/plataforma" className="action-button action-button--secondary">Administrar catálogo</Link>
      : enabled && getSessionRole() === 'administrador' ? <Link to={`/suscripcion?plan=${plan.id}`} className="action-button action-button--secondary">Gestionar contratación DEMO</Link> : null}</>
}

export function PlansPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => { let active = true; getCatalog().then(data => { if (active) { setPlans(data.plans); setEnabled(data.simulatorEnabled); setError('') } },
    error => { if (active) setError(message(error)) }); return () => { active = false } }, [retry])
  return <div className="commerce-public"><PublicHeader /><main className="commerce-page commerce-page--public" id="plans-content">
    <header className="commerce-public__hero">
      <div><p className="commerce-public__eyebrow">AgroScan / Catálogo para empresas</p>
        <h1>Un mejor control comienza con <em>un primer paso.</em></h1>
        <p>Explora las condiciones publicadas y encuentra el punto de partida para tu equipo. Puedes solicitar un plan sin iniciar sesión.</p>
        <Link to="/" className="commerce-public__back"><Icon name="arrow-right" size={17} /> Volver a la experiencia AgroScan</Link>
      </div>
      <div className="commerce-public__visual" aria-label="Capacidades de AgroScan">
        <span><Icon name="scan" size={21} /> Visión asistida</span>
        <span><Icon name="network" size={21} /> Información IoT</span>
        <span><Icon name="boxes" size={21} /> Trazabilidad por lotes</span>
        <p>Capacidades de la plataforma · Sin resultados experimentales implícitos</p>
      </div>
    </header>
    <section className="commerce-public__content" aria-label="Planes disponibles">
      <div className="commerce-public__title"><div><p className="commerce-public__eyebrow">PLANES DEMO</p><h2>Opciones para explorar AgroScan.</h2></div>
        <p>El catálogo y sus condiciones se consultan directamente en el backend.</p></div>
      <Notice /><ErrorNotice error={error} />
      {error && <button type="button" className="commerce-public__retry" onClick={() => { setPlans(null); setRetry(v => v + 1) }}>Reintentar consulta</button>}
      {!plans && !error && <p role="status">Consultando planes disponibles…</p>}
      {plans?.length === 0 && <section className="commerce-public__empty"><h3>Catálogo en preparación</h3><p>El propietario todavía no ha publicado planes DEMO. Tu acceso operativo continúa disponible.</p></section>}
      {!enabled && plans && <p role="status" className="commerce-public__state">La contratación simulada está deshabilitada. Puedes consultar las condiciones.</p>}
      <div className="commerce-grid commerce-public__grid">{plans?.map(plan => <PlanCard key={plan.id} plan={plan}>
        <PlanActions plan={plan} enabled={enabled} />
      </PlanCard>)}</div>
      <p className="commerce-public__footnote">Precios ilustrativos en PEN. Sin cargos reales. Solicitar un plan no activa una empresa ni crea acceso privilegiado: toda alta requiere revisión e invitación.</p>
    </section>
  </main></div>
}

export function SubscriptionPage() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<CompanyCommerce | null>(null)
  const [plans, setPlans] = useState<Plan[]>([])
  const [order, setOrder] = useState<Order | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [scenario, setScenario] = useState<Scenario>('approve')
  const [cancel, setCancel] = useState(false)
  const [acceptUpdated, setAcceptUpdated] = useState(false)
  const inFlight = useRef(false)
  const key = useRef({ selection: '', value: crypto.randomUUID() })
  const admin = getSessionRole() === 'administrador'
  useEffect(() => {
    if (!admin) return
    let active = true
    Promise.all([getCompanyCommerce(), getCatalog()]).then(([company, catalog]) => {
      if (active) { setData(company); setPlans(catalog.plans) }
    }, error => { if (active) setError(message(error)) })
    return () => { active = false }
  }, [revision, admin])
  const first = !data?.subscription && data?.onboarding?.stage === 'awaiting_demo_order'
  const eligible = first && data?.onboarding?.approvedPlanAvailable ? plans.filter(p => p.id === data.onboarding!.approvedPlan.id) : plans
  const chosen = eligible.find(p => p.id === Number(params.get('plan') ?? (first && data?.onboarding?.approvedPlanAvailable ? data.onboarding.approvedPlan.id : '')))
  const action: Order['action'] = params.get('action') === 'renew' && data?.subscription ? 'renew' : data?.subscription ? 'change' : 'subscribe'
  async function act(operation: () => Promise<void>) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setError(''); setSuccess('')
    try { await operation(); setRevision(v => v + 1) } catch (error) { setError(message(error)) } finally { inFlight.current = false; setBusy(false) }
  }
  async function prepare() {
    if (!chosen) return
    const selection = `${chosen.id}:${action}:${acceptUpdated}`
    if (key.current.selection !== selection) key.current = { selection, value: crypto.randomUUID() }
    setOrder(await createDemoOrder(chosen.id, action, key.current.value, acceptUpdated))
  }
  if (!admin) return <section className="panel"><h1>Suscripción empresarial</h1><p>Solo el administrador de tu empresa puede gestionar su suscripción. Tus funciones operativas siguen disponibles.</p><Link to="/planes">Consultar planes</Link></section>
  return <div className="commerce-page">
    <header className="section-heading"><div><p className="eyebrow">Tu empresa · Suscripción</p><h1>Un plan claro, sin cargos reales.</h1></div><Link to="/planes" className="action-button action-button--secondary">Comparar planes</Link></header>
    <Notice /><ErrorNotice error={error} />
    {success && <p role="status" className="commerce-success">{success}</p>}
    {!data && !error && <p role="status">Consultando suscripción…</p>}
    {error && <button type="button" disabled={busy} onClick={() => { setError(''); setRevision(v => v + 1) }}>Actualizar datos</button>}
    {data && <>
      {!data.simulatorEnabled && <p role="status">La simulación está deshabilitada. El historial sigue disponible.</p>}
      {data.onboarding && <section className="panel"><h2>Incorporación de tu empresa</h2>
        <p>Solicitud: <span className="commerce-reference">{data.onboarding.applicationId}</span> · {data.onboarding.stage === 'completed' ? 'Alta DEMO completada' : data.onboarding.stage === 'awaiting_demo_order' ? 'Administrador incorporado; primera contratación DEMO pendiente' : 'Incorporación del administrador pendiente'}.</p>
        {data.onboarding.stage !== 'completed' && <p>Propuesta: {data.onboarding.approvedPlan.name} · v{data.onboarding.approvedPlan.version}. La aprobación del alta no es una compra ni activa una suscripción.</p>}
        {first && !data.onboarding.approvedPlanAvailable && <p role="status">La propuesta ya no está vigente. Selecciona un plan actual y confirma expresamente sus nuevas condiciones.</p>}
        {data.onboarding.orderId && <p>Primera orden: {data.onboarding.orderId} · Suscripción #{data.onboarding.subscriptionId}.</p>}
      </section>}
      <section className="panel"><h2>Plan actual</h2>{data.subscription ? <>
        <p><strong>{data.subscription.plan.name} · v{data.subscription.plan.version}</strong> <span className="commerce-badge">{states[data.subscription.status]}</span></p>
        <p>{data.subscription.status === 'cancelled' ? 'Periodo contratado registrado' : 'Vigencia'}: desde {date(data.subscription.startsAt)} hasta {date(data.subscription.endsAt)} (UTC)</p>
        <p>Periodo {data.subscription.plan.period === 'annual' ? 'anual' : 'mensual'} · {money(data.subscription.plan.amountCents)} PEN referencial DEMO.</p>
        <SubscriptionLifecycle subscription={data.subscription} />
        <ul>{data.subscription.plan.benefits.map((b, i) => <li key={i}>{b}</li>)}</ul>
        {!plans.some(p => p.id === data.subscription!.plan.id) && <p>Esta versión ya no admite nuevas contrataciones. Compara los planes vigentes para cambiar de plan.</p>}
        <div className="commerce-actions"><button className="action-button action-button--primary" disabled={busy || !data.simulatorEnabled || !plans.some(p => p.id === data.subscription!.plan.id)}
          onClick={() => { setOrder(null); setParams({ plan: String(data.subscription!.plan.id), action: 'renew' }) }}>Renovar en DEMO</button>
          <button className="action-button action-button--secondary" disabled={busy || !data.simulatorEnabled || data.subscription.status === 'cancelled'} onClick={() => setCancel(true)}>Cancelar suscripción DEMO</button></div>
        {cancel && <div className="commerce-confirm" role="group" aria-label="Confirmar cancelación"><p>¿Cancelar inmediatamente la suscripción DEMO? No se aplica gracia tras cancelar. El historial se conserva y tus operaciones continúan disponibles.</p>
          <button disabled={busy} onClick={() => { void act(async () => { await cancelDemoSubscription(); setCancel(false); setSuccess(`Suscripción cancelada. ${DEMO_NOTICE}`) }) }}>Confirmar cancelación</button>
          <button disabled={busy} onClick={() => setCancel(false)}>Volver</button></div>}
      </> : <p>Sin suscripción comercial. Las funciones existentes de tu empresa siguen disponibles.</p>}</section>
      {!order && <section className="panel commerce-form"><h2>{data.subscription ? 'Cambiar de plan DEMO' : 'Elegir plan para la primera contratación'}</h2>
        <label>Plan vigente<select value={chosen?.id ?? ''} disabled={busy || !data.simulatorEnabled} onChange={e => { setAcceptUpdated(false); setParams(e.target.value ? { plan: e.target.value } : {}) }}><option value="">Selecciona un plan</option>{eligible.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version} · {money(p.amountCents)} / {p.period === 'annual' ? 'año' : 'mes'}</option>)}</select></label>
        {data.subscription && <p>El cambio se aplica al aprobar la simulación: reinicia la vigencia sin prorrateos, descuentos ni cobros. Antes de confirmar se conservan las condiciones actuales. No requiere otra aprobación del propietario.</p>}
      </section>}
      {params.has('plan') && !chosen && <p role="status">El plan seleccionado ya no está disponible. Consulta el catálogo vigente.</p>}
      {chosen && !order && <section className="panel commerce-checkout" aria-labelledby="checkout-title"><h2 id="checkout-title">Resumen de contratación DEMO</h2>
        <PlanCard plan={chosen} /><p>Operación: {action === 'renew' ? 'renovación' : action === 'change' ? 'cambio de plan' : 'alta'} · Empresa activa de tu sesión.</p>
        <p>El importe y las condiciones se validarán en el servidor. No solicitamos datos financieros.</p>
        {first && !data.onboarding!.approvedPlanAvailable && <label><input type="checkbox" checked={acceptUpdated} onChange={e => setAcceptUpdated(e.target.checked)} />He revisado y confirmo las condiciones de este plan vigente, diferentes de la propuesta inicial.</label>}
        <button className="action-button action-button--primary" disabled={busy || !data.simulatorEnabled || (first && !data.onboarding!.approvedPlanAvailable && !acceptUpdated)} onClick={() => { void act(prepare) }}>{busy ? 'Preparando…' : 'Preparar orden DEMO'}</button></section>}
      {order && <section className="panel commerce-checkout" aria-live="polite"><h2>Orden DEMO · {states[order.status]}</h2>
        <p className="commerce-reference">Referencia: {order.id}</p><p>{order.plan.name} · v{order.plan.version} · {money(order.amountCents)} / {order.plan.period === 'annual' ? 'año' : 'mes'}</p><Notice />
        {order.isExpired && <p role="status">Esta orden venció para confirmación. Prepara otra orden; no se ha activado una suscripción por este intento.</p>}
        {order.expiresAt && order.status === 'pending' && <p>Confirmar antes de {deadline(order.expiresAt)} (UTC). Vigencia de la orden: 24 horas.</p>}
        {order.status === 'pending' ? <form onSubmit={event => { event.preventDefault(); void act(async () => {
          const result = await confirmDemoOrder(order.id, scenario); setOrder(result); setParams({}); setAcceptUpdated(false); key.current = { selection: '', value: crypto.randomUUID() }; setSuccess(`${states[result.status]}. ${DEMO_NOTICE}`)
        }) }}><label htmlFor="demo-scenario">Resultado a ensayar</label><select id="demo-scenario" value={scenario} disabled={busy} onChange={event => setScenario(event.target.value as Scenario)}>
          <option value="approve">Aprobación simulada</option><option value="reject">Rechazo simulado</option><option value="cancel">Cancelación simulada</option></select>
          <p>Al confirmar, el backend determina y registra el resultado de este escenario de prueba.</p>
          <button className="action-button action-button--primary" disabled={busy || !data.simulatorEnabled || order.isExpired}>{busy ? 'Confirmando…' : 'Confirmar simulación — sin cobro'}</button>
          <button type="button" disabled={busy} onClick={() => { key.current = { selection: '', value: crypto.randomUUID() }; setParams({ plan: String(order.plan.id), ...(order.action === 'renew' ? { action: 'renew' } : {}) }); setOrder(null) }}>Preparar otra orden DEMO</button>
        </form> : <button onClick={() => { setOrder(null); setParams({}) }}>Volver a mi suscripción</button>}</section>}
      <section className="panel"><h2>Historial de contrataciones</h2><OrderHistory orders={data.orders} onResume={o => { setOrder(o); setParams({}) }} /></section>
      <section className="panel"><h2>Transacciones DEMO</h2>{data.transactions.length ? <ul>{data.transactions.map(tx => <li key={tx.id}>{date(tx.createdAt)} · {states[tx.outcome] ?? tx.outcome} · {money(tx.amountCents)} · {DEMO_NOTICE}</li>)}</ul> : <p>Aún no hay transacciones simuladas.</p>}</section>
    </>}
  </div>
}

export function SubscriptionLifecycle({ subscription }: { subscription: Subscription }) {
  return <div className="commerce-muted"><p>{subscription.status === 'cancelled' ? 'Cancelación inmediata. Sin periodo de gracia tras la cancelación expresa.'
    : subscription.inGracePeriod ? `Suscripción vencida. Gracia informativa hasta ${date(subscription.graceEndsAt!)} (UTC).`
      : subscription.status === 'expired' ? subscription.graceEndsAt ? 'Suscripción vencida; el periodo de gracia informativa de siete días terminó.' : 'Suscripción vencida.' : 'Vigencia activa DEMO.'}</p>
    <p>La gracia no reactiva la suscripción. No se borran históricos ni se bloquean las operaciones por vencimiento o cancelación.</p></div>
}

export function OrderHistory({ orders, onResume }: { orders: Order[]; onResume?: (order: Order) => void }) {
  return orders.length ? <div className="commerce-table" role="region" aria-label="Órdenes DEMO" tabIndex={0}><table><caption>Contrataciones simuladas · No se realizaron cobros</caption>
    <thead><tr><th scope="col">Referencia / fecha</th><th scope="col">Empresa</th><th scope="col">Plan</th><th scope="col">Importe DEMO</th><th scope="col">Estado</th></tr></thead>
    <tbody>{orders.map(o => <tr key={o.id}><td><span className="commerce-reference">{o.id}</span><br />{date(o.createdAt)}</td><td>{o.organizationId}</td><td>{o.plan.name} · v{o.plan.version}</td><td>{money(o.amountCents)}</td><td>{o.isExpired ? 'Vencida para confirmación' : states[o.status]}
      {onResume && <button type="button" onClick={() => onResume(o)}>{o.status === 'pending' ? 'Continuar orden' : 'Ver comprobante DEMO'}</button>}</td></tr>)}</tbody></table></div> : <p>Aún no hay contrataciones. Las operaciones reales no se contabilizan como ventas.</p>
}

export function CommercialDashboard() {
  const [parameters, setParameters] = useSearchParams()
  const view = parameters.get('vista') === 'suscripciones' ? 'subscriptions' : parameters.get('vista') === 'operaciones' ? 'operations' : 'catalog'
  const [overview, setOverview] = useState<CommercialOverview | null>(null)
  const [plans, setPlans] = useState<Plan[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null)
  const [versions, setVersions] = useState<Plan[] | null>(null)
  const creation = useRef({ payload: '', key: '' })
  const saving = useRef(false)
  const formRef = useRef<HTMLFormElement>(null)
  const editorButton = useRef<HTMLButtonElement>(null)
  const editorOpener = useRef<HTMLButtonElement | null>(null)
  const editorWasOpen = useRef(false)
  useEffect(() => {
    if (editing) formRef.current?.querySelector<HTMLInputElement>('input:not([readonly])')?.focus()
    else if (editorWasOpen.current) (editorOpener.current?.isConnected ? editorOpener.current : editorButton.current)?.focus()
    editorWasOpen.current = editing
  }, [editing])
  useEffect(() => { let active = true; Promise.all([getCommercialOverview(), listCommercialPlans()]).then(([data, catalog]) => {
    if (active) { setOverview(data); setPlans(catalog) }
  }, error => { if (active) setError(message(error)) }); return () => { active = false } }, [revision])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || saving.current) return
    const form = new FormData(event.currentTarget)
    const price = String(form.get('price'))
    if (!/^\d+(\.\d{1,2})?$/.test(price)) { setError('Indica un precio PEN con hasta dos decimales.'); return }
    const [whole, fraction = ''] = price.split('.')
    let limits: Record<string, number>
    try { limits = JSON.parse(String(form.get('limits') || '{}')) as Record<string, number> } catch { setError('Los límites deben ser un objeto JSON de nombres y cantidades.'); return }
    if (!limits || Array.isArray(limits) || typeof limits !== 'object' || Object.entries(limits).some(([key, value]) => !key.trim() || key.length > 60 || !Number.isSafeInteger(value) || value < 0)) { setError('Los límites deben tener nombres y cantidades enteras no negativas.'); return }
    const input: PlanInput = { code: String(form.get('code')), name: String(form.get('name')).trim(), description: String(form.get('description')).trim(),
      amountCents: Number(whole) * 100 + Number(fraction.padEnd(2, '0')), currency: 'PEN', period: form.get('period') as 'monthly' | 'annual',
      benefits: String(form.get('benefits')).split('\n').map(b => b.trim()).filter(Boolean), limits, recommended: form.get('recommended') === 'on',
      displayOrder: Number(form.get('displayOrder')), publish: false, expectedVersion: selectedPlan?.version ?? 0, changeNote: String(form.get('changeNote')).trim() }
    if (input.name.length < 2 || input.description.length < 2 || input.benefits.length < 1 || input.benefits.length > 15 || input.benefits.some(b => b.length > 160)) { setError('Completa nombre, descripción y entre 1 y 15 beneficios de hasta 160 caracteres.'); return }
    const payload = JSON.stringify(input)
    if (creation.current.payload !== payload) creation.current = { payload, key: crypto.randomUUID() }
    input.idempotencyKey = creation.current.key
    saving.current = true
    setBusy(true); setError(''); setSuccess('')
    try { await saveCommercialPlan(input); formRef.current?.reset(); setEditing(false); setSuccess('Borrador DEMO guardado. Revisa sus condiciones y pulsa «Publicar versión» para ofrecerlo.'); setRevision(v => v + 1) }
    catch (error) { setError(message(error)) } finally { saving.current = false; setBusy(false) }
  }
  async function togglePlan(plan: Plan) {
    if (busy) return
    const verb = plan.state === 'draft' ? 'Publicar versión' : plan.isActive ? 'Desactivar' : 'Activar'
    if (!window.confirm(`${verb} ${plan.name} v${plan.version}? Las condiciones contratadas se conservan.`)) return
    setBusy(true); setError('')
    try {
      await setCommercialPlanStatus(plan.id, !plan.isActive)
      setVersions(null); setRevision(v => v + 1)
      setSuccess(`${verb}: operación completada. Las contrataciones existentes no cambian.`)
    } catch (error) { setError(message(error)) } finally { setBusy(false) }
  }
  return <section className="commerce-page commerce-owner" aria-labelledby="commercial-heading"><header className="section-heading"><div><p className="eyebrow">Plataforma / Comercial DEMO</p><h1 id="commercial-heading">Planes y contrataciones DEMO</h1><p className="owner-page-copy">Condiciones claras por empresa. Todas las operaciones de esta sección son simuladas.</p></div>
    {view === 'catalog' && <button ref={editorButton} className="action-button action-button--primary" disabled={busy} onClick={event => { editorOpener.current = event.currentTarget; setSelectedPlan(null); setEditing(v => !v); setVersions(null); creation.current = { payload: '', key: '' } }} aria-expanded={editing} aria-controls="owner-plan-editor">{editing ? 'Cerrar formulario' : 'Nuevo plan'}</button>}</header><Notice /><ErrorNotice error={error} />
    {success && <p role="status" className="commerce-success">{success}</p>}{!overview && !error && <p role="status">Consultando métricas DEMO…</p>}
    {busy && view === 'catalog' && <p role="status" aria-live="polite">Procesando catálogo DEMO…</p>}
    {error && <button onClick={() => { setError(''); setRevision(v => v + 1) }}>Reintentar</button>}
    {overview && <div className="summary-grid">{([
      ['Empresas con plan DEMO activo', overview.activeDemoSubscriptions, 'boxes'], ['Planes activos', overview.activePlans, 'clipboard'], ['Vencen en 30 días', overview.expiringSoon, 'clock'],
      ['Contrataciones simuladas', overview.orders.length, 'history'], ['Importe aprobado DEMO acumulado', money(overview.simulatedTotalCents), 'chart'],
    ] as const).map(([label, value, icon], index) => <MetricCard key={label} label={label} value={value} icon={icon} tone={index === 2 ? 'amber' : index === 4 ? 'blue' : 'green'} detail={index === 4 ? 'Sin cobros reales' : 'Datos actuales · DEMO'} />)}</div>}
    <nav className="owner-commercial-navigation" aria-label="Vistas comerciales">
      {[['catalog', 'Catálogo', ''], ['subscriptions', 'Suscripciones', 'suscripciones'], ['operations', 'Operaciones DEMO', 'operaciones']].map(([key, label, value]) =>
        <button type="button" key={key} aria-pressed={view === key} onClick={() => { setParameters(value ? { vista: value } : {}); setEditing(false) }}>{label}</button>)}
    </nav>
    {editing && view === 'catalog' && <form key={selectedPlan?.id ?? 'new'} id="owner-plan-editor" ref={formRef} className="panel commerce-form owner-editor" onKeyDown={event => { if (event.key === 'Escape' && !busy) setEditing(false) }} onSubmit={event => { void save(event) }}>
      <PlanEditor plan={selectedPlan} busy={busy} onCancel={() => setEditing(false)} />
    </form>}
    {overview && view === 'catalog' && <section className="owner-catalog"><h2>Catálogo de planes</h2><p className="owner-page-copy">Cada nueva versión conserva las condiciones de las contrataciones anteriores.</p>{plans.length ? <div className="commerce-grid">{plans.filter(plan => !plans.some(p => p.code === plan.code && p.version > plan.version)).map(plan => <PlanCard key={plan.id} plan={plan}>
      <p>Estado: {plan.state === 'draft' ? 'Borrador · no público' : plan.isActive ? 'Activo' : 'Inactivo'} · Orden: {plan.displayOrder ?? 0}</p>
      {plans.filter(p => p.code === plan.code && p.isActive && p.id !== plan.id).map(active => <div key={active.id}><p>La versión pública v{active.version} continúa vigente hasta publicar este borrador.</p><button type="button" disabled={busy} onClick={() => { void togglePlan(active) }}>Desactivar versión pública v{active.version}</button></div>)}
      <div className="commerce-actions"><button className="action-button action-button--secondary" disabled={busy} onClick={event => { editorOpener.current = event.currentTarget; setSelectedPlan(plan); setEditing(true); creation.current = { payload: '', key: '' } }}>Editar</button>
      <button className="action-button action-button--secondary" disabled={busy} onClick={() => { setBusy(true); setError(''); void getCommercialPlanVersions(plan.id).then(setVersions, error => setError(message(error))).finally(() => setBusy(false)) }}>Ver versiones</button>
      <button className="action-button action-button--secondary" disabled={busy} onClick={() => { void togglePlan(plan) }}>{plan.state === 'draft' ? 'Publicar versión' : plan.isActive ? 'Desactivar' : 'Activar'}</button></div></PlanCard>)}</div> : <p className="owner-empty">Tu catálogo está vacío. Usa «Nuevo plan» para preparar las primeras condiciones DEMO.</p>}
      {versions && <section className="panel" aria-label="Historial de versiones"><h3>Versiones de {versions[0]?.name} · solo lectura</h3><button type="button" onClick={() => setVersions(null)}>Cerrar historial</button><div className="commerce-grid">{versions.map(plan => <PlanCard key={plan.id} plan={plan}><p>{plan.state === 'draft' ? 'Borrador' : plan.isActive ? 'Activo' : 'Inactivo'}</p><p>Creación: {plan.createdAt ? date(plan.createdAt) : 'Fecha histórica no registrada'}</p><p>Publicación: {plan.publishedAt ? date(plan.publishedAt) : 'Sin fecha registrada'}</p><p>{plan.changeNote || 'Condiciones históricas conservadas'}</p></PlanCard>)}</div></section>}</section>}
    {overview && view === 'subscriptions' && <><section className="panel"><h2>Suscripciones por empresa</h2><OwnerSubscriptions subscriptions={overview.subscriptions} /></section>
      {!!overview.onboardings?.length && <section className="panel"><h2>Incorporación comercial</h2><div className="commerce-table" role="region" aria-label="Trazabilidad de altas comerciales" tabIndex={0}><table><caption>Referencias reales de solicitud, primera orden y suscripción DEMO</caption>
        <thead><tr><th scope="col">Empresa</th><th scope="col">Solicitud</th><th scope="col">Etapa</th><th scope="col">Primera orden / suscripción</th></tr></thead><tbody>{overview.onboardings.map(o => <tr key={o.applicationId}><td>Empresa #{o.organizationId}</td><td>{o.applicationId}</td><td>{o.stage === 'completed' ? 'Completada DEMO' : o.stage === 'awaiting_demo_order' ? 'Contratación DEMO pendiente' : 'Administrador pendiente'}</td><td>{o.orderId ?? 'Sin orden aprobada'} · {o.subscriptionId ?? 'Sin suscripción de este alta'}</td></tr>)}</tbody>
      </table></div><Link to="/plataforma/solicitudes">Revisar solicitudes e invitaciones</Link></section>}</>}
    {overview && view === 'operations' && <><section className="panel"><h2>Contrataciones DEMO</h2><OrderHistory orders={overview.orders} /></section>
      <section className="panel"><h2>Transacciones DEMO</h2><OwnerTransactions transactions={overview.transactions} /></section></>}
  </section>
}

export function OwnerSubscriptions({ subscriptions }: Pick<CommercialOverview, 'subscriptions'>) {
  return subscriptions.length ? <div className="commerce-table" role="region" aria-label="Suscripciones por empresa" tabIndex={0}><table><caption>Vigencia y condiciones de las suscripciones DEMO</caption>
    <thead><tr><th scope="col">Empresa</th><th scope="col">Plan contratado</th><th scope="col">Estado</th><th scope="col">Inicio</th><th scope="col">Vencimiento</th></tr></thead>
    <tbody>{subscriptions.map(s => <tr key={s.organizationId}><td>Empresa #{s.organizationId}</td><td><strong>{s.plan.name}</strong><small className="owner-record-id">Versión {s.plan.version} · {money(s.plan.amountCents)} / {s.plan.period === 'annual' ? 'año' : 'mes'}</small></td><td><span className="commerce-badge">{states[s.status]}</span>{s.inGracePeriod && <small>Gracia informativa hasta {date(s.graceEndsAt!)}</small>}</td><td>{date(s.startsAt)}</td><td>{date(s.endsAt)}</td></tr>)}</tbody>
  </table></div> : <p className="owner-empty">Todavía no hay suscripciones DEMO. Aparecerán cuando un administrador empresarial confirme una contratación simulada.</p>
}

export function OwnerTransactions({ transactions }: Pick<CommercialOverview, 'transactions'>) {
  return transactions.length ? <div className="commerce-table" role="region" aria-label="Transacciones DEMO" tabIndex={0}><table><caption>Pago simulado — No se realizó ningún cobro</caption>
    <thead><tr><th scope="col">Fecha</th><th scope="col">Empresa</th><th scope="col">Referencia</th><th scope="col">Resultado</th><th scope="col">Importe DEMO</th></tr></thead>
    <tbody>{transactions.map(tx => <tr key={tx.id}><td>{date(tx.createdAt)}</td><td>Empresa #{tx.organizationId}</td><td className="commerce-reference">{tx.orderId ?? 'Cancelación de suscripción'}</td><td><span className="commerce-badge">{states[tx.outcome]}</span></td><td>{money(tx.amountCents)}</td></tr>)}</tbody>
  </table></div> : <p className="owner-empty">No hay transacciones registradas. Aquí podrás distinguir aprobaciones, rechazos y cancelaciones DEMO, sin ingresos reales.</p>
}

export function PlanEditor({ plan, busy, onCancel }: { plan: Plan | null; busy: boolean; onCancel: () => void }) {
  return <>
      <h3>{plan ? `Editar ${plan.name} · nueva versión` : 'Nuevo plan DEMO'}</h3><p>Guardar crea un borrador; publicar requiere una confirmación adicional. Las contrataciones anteriores no cambian.</p>
      <fieldset disabled={busy}><legend>Información del plan</legend><div className="commerce-form-grid">
        <label>Código estable<input name="code" defaultValue={plan?.code} readOnly={!!plan} required pattern="[a-z][a-z0-9-]{1,39}" maxLength={40} /></label>
        <label>Nombre<input name="name" defaultValue={plan?.name} required minLength={2} maxLength={100} /></label>
        <label>Precio ilustrativo (PEN)<input name="price" defaultValue={plan ? (plan.amountCents / 100).toFixed(2) : ''} required type="number" min="0" max="1000000" step="0.01" /></label>
        <label>Periodo<select name="period" defaultValue={plan?.period ?? 'monthly'}><option value="monthly">Mensual</option><option value="annual">Anual</option></select></label>
        <label>Orden de presentación<input name="displayOrder" defaultValue={plan?.displayOrder ?? 0} type="number" min="0" max="100000" step="1" required /></label>
      </div><label>Descripción<textarea name="description" defaultValue={plan?.description} required minLength={2} maxLength={500} /></label>
      <label>Beneficios (uno por línea)<textarea name="benefits" defaultValue={plan?.benefits.join('\n')} required maxLength={2415} /></label>
      <details><summary>Límites referenciales opcionales</summary><p>Solo informativos durante la demostración. Ejemplo: {`{"evaluaciones": 1000}`}</p><label>Límites (JSON)<textarea name="limits" defaultValue={JSON.stringify(plan?.limits ?? {})} maxLength={2000} /></label></details>
      <label><input name="recommended" defaultChecked={plan?.recommended} type="checkbox" /> Identificar como recomendado</label>
      <label>Resumen de cambios<textarea name="changeNote" maxLength={500} required={!!plan} /></label>
      <button className="action-button action-button--primary">{busy ? 'Guardando…' : 'Guardar borrador'}</button> <button type="button" onClick={() => onCancel()}>Cancelar</button></fieldset>
  </>
}
