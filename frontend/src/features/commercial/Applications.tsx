import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getCatalog, listCommercialPlans, money, type Plan } from './commercialApi.ts'
import { APPLICATION_MESSAGE, APPLICATION_STATES, NOTIFICATION_MESSAGES, listApplications, submitApplication,
  type ApplicationReceipt, type ApplicationStatus, type CommercialApplication } from './applicationsApi.ts'
import { ApplicationDecisionPanel } from './ApplicationDecisionPanel'
import { InitialAdministratorInvitation } from './InitialAdministratorInvitation'
import { PublicHeader } from '../../components/layout/PublicHeader'
import { ApiConnectionError } from '../../services/agroscanApi'
import './Commercial.css'

const failureMessage = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la consulta. Reintenta.'
export function CommercialApplicationPage() {
  const [parameters, setParameters] = useSearchParams()
  const [plans, setPlans] = useState<Plan[] | null>(null)
  const planId = parameters.get('plan') ?? ''
  const [companyName, setCompanyName] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [receipt, setReceipt] = useState<ApplicationReceipt | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const idempotency = useRef({ payload: '', key: crypto.randomUUID() })
  const confirmation = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (receipt) confirmation.current?.focus() }, [receipt])
  useEffect(() => { let active = true; getCatalog().then(data => { if (active) { setPlans(data.plans); setError('') } },
    error => { if (active) setError(failureMessage(error)) }); return () => { active = false } }, [retry])
  const selected = plans?.find(p => String(p.id) === planId)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!selected || busy) return
    const data = { companyName: companyName.trim(), contactName: contactName.trim(), contactEmail: contactEmail.trim(), requestedPlanId: selected.id, requestedPeriod: selected.period }
    const payload = JSON.stringify(data)
    if (idempotency.current.payload !== payload) idempotency.current = { payload, key: crypto.randomUUID() }
    setBusy(true); setError('')
    try {
      const result = await submitApplication({ ...data, idempotencyKey: idempotency.current.key })
      setReceipt(result); setCompanyName(''); setContactName(''); setContactEmail('')
    } catch (error) { setError(error instanceof ApiConnectionError ? 'No se pudo confirmar la respuesta. La solicitud puede haberse guardado: reintenta sin cambiar los datos para conservar la misma referencia.' : failureMessage(error)) } finally { setBusy(false) }
  }
  return <><PublicHeader /><main className="commerce-page"><header className="commerce-hero"><p className="eyebrow">AgroScan / Solicitud comercial</p>
    <h1>Cuéntanos sobre tu empresa</h1><p>Selecciona un plan de referencia y solicita la revisión de tu alta. No necesitas iniciar sesión.</p><Link to={planId ? `/planes?plan=${encodeURIComponent(planId)}` : '/planes'} className="text-link">Comparar planes</Link></header>
    {error && <p role="alert" className="commerce-error">{error}</p>}
    {!plans && !error && <p role="status">Cargando planes disponibles…</p>}
    {error && !plans && <button onClick={() => setRetry(v => v + 1)}>Reintentar catálogo</button>}
    {receipt ? <section className="panel"><h2 ref={confirmation} tabIndex={-1}>{APPLICATION_MESSAGE}</h2><p>Referencia: <span className="commerce-reference">{receipt.id}</span></p>
      {receipt.ownerNotification && <p role="status">{NOTIFICATION_MESSAGES[receipt.ownerNotification]}</p>}
      <p>La solicitud no aprueba la contratación ni crea una empresa o una cuenta. Conserva esta referencia para una comunicación posterior.</p><p>No se realizó ningún pago ni cobro.</p>
      <Link to="/acceso">Volver al acceso de AgroScan</Link></section>
      : plans && (plans.length ? <form className="panel commerce-form" onSubmit={event => { void submit(event) }}>
        <fieldset disabled={busy}><legend>Datos de la solicitud</legend><div className="commerce-form-grid">
          <label>Empresa solicitante<input value={companyName} required minLength={2} maxLength={120} autoComplete="organization" onChange={e => setCompanyName(e.target.value)} /></label>
          <label>Persona de contacto<input value={contactName} required minLength={2} maxLength={120} autoComplete="name" onChange={e => setContactName(e.target.value)} /></label>
          <label>Correo de contacto<input type="email" value={contactEmail} required maxLength={254} autoComplete="email" onChange={e => setContactEmail(e.target.value)} /></label>
          <ApplicationPlanField plans={plans} value={selected ? planId : ''} onChange={id => setParameters(previous => { const next = new URLSearchParams(previous); if (id) next.set('plan',id); else next.delete('plan'); return next })} />
        </div>{planId && !selected && <p role="status">El plan solicitado no está disponible. Selecciona un plan vigente antes de enviar.</p>}{selected && <p>{selected.description} · Versión {selected.version}. Precio ilustrativo en PEN, no tarifa aprobada.</p>}
        <p>Usaremos estos datos únicamente para gestionar tu solicitud. No envíes contraseñas, documentos ni datos financieros.</p>
        <p>El propietario revisará el alta. Esta solicitud no es una compra ni una suscripción activa.</p>
        <button className="action-button action-button--primary" disabled={busy || !selected}>{busy ? 'Enviando solicitud…' : 'Enviar solicitud para revisión'}</button></fieldset>
      </form> : <section className="panel"><h2>Catálogo en preparación</h2><p>Aún no hay planes disponibles para solicitar un alta.</p></section>)}
  </main></>
}

export function ApplicationPlanField({ plans, value, onChange }: { plans: Plan[]; value: string; onChange: (value: string) => void }) {
  return <label>Plan y periodo de referencia<select value={value} required onChange={e => onChange(e.target.value)}><option value="">Selecciona un plan</option>
    {plans.map(p => <option key={p.id} value={p.id}>{p.name} · {p.period === 'annual' ? 'Anual' : 'Mensual'} · {money(p.amountCents)} DEMO</option>)}</select></label>
}

export function CommercialApplicationsDashboard() {
  const [status, setStatus] = useState<ApplicationStatus | ''>('')
  const [planId, setPlanId] = useState('')
  const [plans, setPlans] = useState<Plan[]>([])
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<Awaited<ReturnType<typeof listApplications>> | null>(null)
  const [selected, setSelected] = useState<CommercialApplication | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const detailHeader = useRef<HTMLHeadingElement>(null)
  const detailOpener = useRef<HTMLButtonElement | null>(null)
  useEffect(() => { if (selected) detailHeader.current?.focus() }, [selected])
  useEffect(() => { let active = true; Promise.all([listApplications({ status: status || undefined, planId: planId ? Number(planId) : undefined, offset }), listCommercialPlans()]).then(([items, catalog]) => {
    if (active) { setData(items); setPlans(catalog); setError('') }
  }, error => { if (active) setError(failureMessage(error)) }); return () => { active = false } }, [status, planId, offset, refresh])
  function reset() { setData(null); setSelected(null); setError(''); setOffset(0) }
  return <section className="commerce-page commerce-owner"><header className="section-heading"><div><p className="eyebrow">Plataforma / Captación</p><h1>Solicitudes comerciales</h1><p>Revisa las solicitudes y decide su alta. Aprobar asocia la empresa; no activa una suscripción ni crea cuentas.</p></div>
    <button className="action-button action-button--secondary" onClick={() => { reset(); setRefresh(v => v + 1) }}>Actualizar</button></header>
    <div className="commerce-form commerce-form-grid"><label>Estado<select value={status} onChange={e => { reset(); setStatus(e.target.value as ApplicationStatus | '') }}><option value="">Todos</option>{Object.entries(APPLICATION_STATES).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Plan solicitado<select value={planId} onChange={e => { reset(); setPlanId(e.target.value) }}><option value="">Todos los planes</option>{plans.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></label></div>
    {error && <p role="alert" className="commerce-error">{error}</p>}{!data && !error && <p role="status">Consultando solicitudes…</p>}
    {data && <section className="panel"><h2>{data.total} solicitudes registradas</h2>{data.items.length ? <div className="commerce-table" role="region" aria-label="Solicitudes comerciales" tabIndex={0}><table><caption>Datos de contacto de acceso exclusivo del propietario</caption><thead><tr><th scope="col">Empresa</th><th scope="col">Plan</th><th scope="col">Fecha</th><th scope="col">Estado</th><th scope="col">Detalle</th></tr></thead>
      <tbody>{data.items.map(a => <tr key={a.id}><td>{a.companyName}</td><td>{a.plan.name} · v{a.plan.version}</td><td>{new Date(a.createdAt).toLocaleDateString('es-PE')}</td><td>{APPLICATION_STATES[a.status]}</td><td><button type="button" onClick={event => { detailOpener.current=event.currentTarget; setSelected(a) }}>Ver solicitud</button></td></tr>)}</tbody></table></div> : <p>No hay solicitudes con estos filtros. Las nuevas solicitudes públicas aparecerán aquí.</p>}
      <div className="commerce-actions"><button disabled={offset === 0} onClick={() => { setData(null); setSelected(null); setOffset(v => Math.max(0,v-20)) }}>Anterior</button><button disabled={offset + 20 >= data.total} onClick={() => { setData(null); setSelected(null); setOffset(v => v+20) }}>Siguiente</button></div></section>}
    {selected && <section className="panel" aria-label="Detalle de solicitud"><h2 ref={detailHeader} tabIndex={-1}>{selected.companyName}</h2><dl><dt>Referencia</dt><dd className="commerce-reference">{selected.id}</dd><dt>Contacto</dt><dd>{selected.contactName}</dd><dt>Correo</dt><dd>{selected.contactEmail}</dd><dt>Plan y periodo</dt><dd>{selected.plan.name} · {selected.requestedPeriod === 'annual' ? 'Anual' : 'Mensual'} · v{selected.plan.version}</dd><dt>Origen</dt><dd>Formulario público</dd><dt>Estado</dt><dd>{APPLICATION_STATES[selected.status]}</dd></dl>
      <p>Propuesta original: {money(selected.plan.amountCents)} DEMO · v{selected.plan.version}. Sin pago ni suscripción activa por aprobación.</p>
      {selected.ownerNotification && <p>Notificación: {NOTIFICATION_MESSAGES[selected.ownerNotification]}</p>}
      {selected.organizationId && <p>Empresa asociada: ID {selected.organizationId}. Etapa: {selected.provisioningState === 'completed' ? 'alta comercial DEMO completada' : selected.provisioningState === 'awaiting_demo_order' ? 'administrador incorporado; contratación DEMO pendiente' : 'pendiente de incorporar administrador'}.</p>}
      {selected.commercialOrderId && <p>Primera orden DEMO: {selected.commercialOrderId} · Suscripción: {selected.commercialSubscriptionId}. No se realizó ningún cobro.</p>}
      {!!selected.decisions?.length && <section aria-label="Trazabilidad de decisiones"><h3>Historial de decisiones</h3><ol>{selected.decisions.map(d => <li key={d.id}><strong>{d.action === 'approve' ? 'Aprobación' : d.action === 'reject' ? 'Rechazo' : 'Revisión'}</strong> · {new Date(d.createdAt).toLocaleString('es-PE')} · Propietario ID {d.actorUserId}<p>{d.reason}</p></li>)}</ol></section>}
      <ApplicationDecisionPanel key={selected.id} application={selected} onSaved={saved => { setSelected(saved); setRefresh(v => v + 1) }} />
      <InitialAdministratorInvitation key={'invite-' + selected.id} application={selected} />
      <button onClick={() => { setSelected(null); detailOpener.current?.focus() }}>Cerrar detalle</button></section>}
  </section>
}
