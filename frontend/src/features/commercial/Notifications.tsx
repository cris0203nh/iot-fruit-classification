import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MetricCard } from '../../components/MetricCard'
import { getNotifications, notificationEvents, notificationStates, notificationRetryEligible, retryNotification, type NotificationOverview } from './notificationsApi.ts'
import './Commercial.css'

const date = (value: string | null) => value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString('es-PE') : '—'
const errors: Record<string, string> = { smtp_disabled: 'Correo deshabilitado; intención conservada.', configuration_error: 'Revisar la configuración SMTP.',
  recipient_unavailable: 'No hay destinatario autorizado.', recipient_no_longer_authorized: 'El destinatario ya no está autorizado.',
  invitation_no_longer_available: 'La invitación fue utilizada, revocada o venció.',
  smtp_authentication_error: 'El servidor rechazó la autenticación.', smtp_transport_error: 'El transporte SMTP falló.',
  delivery_uncertain: 'Resultado incierto: no se permite reenviar automáticamente.' }

export function NotificationsPage() {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [data, setData] = useState<NotificationOverview | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getNotifications(new URLSearchParams(query)).then(value => { if (active) { setData(value); setError('') } },
      cause => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudo consultar el outbox.') })
    return () => { active = false }
  }, [query, revision])
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget), next = new URLSearchParams()
    for (const key of ['organization_id', 'event', 'status', 'since', 'until']) {
      const value = String(values.get(key) ?? '')
      if (value) next.set(key, key === 'since' ? value + 'T00:00:00Z' : key === 'until' ? value + 'T23:59:59Z' : value)
    }
    setData(null); setParams(next)
  }
  return <section className="commerce-page commerce-owner" aria-labelledby="notification-title">
    <header className="section-heading"><div><p className="eyebrow">Plataforma / Comunicación</p><h1 id="notification-title">Notificaciones comerciales</h1><p>Actividad persistida de correo transaccional. Una aceptación SMTP no confirma recepción en el buzón.</p></div>
      <button type="button" className="action-button action-button--secondary" onClick={() => setRevision(v => v + 1)}>Actualizar</button></header>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Consultando notificaciones…</p>}
    {data && <>
      <p role="status">{data.smtp.configured ? 'SMTP configurado. Consulta los resultados de cada intento.' : data.smtp.enabled ? 'Configuración SMTP incompleta. Las operaciones comerciales se conservan.' : 'Correo deshabilitado. Las notificaciones permanecen registradas sin afirmar un envío.'}</p>
      <div className="summary-grid"><MetricCard label="Registros filtrados" value={data.total} icon="clipboard" detail="Eventos persistidos según los filtros" /><MetricCard label="Aceptadas por SMTP" value={data.statistics.smtp_accepted ?? 0} icon="check" detail="No confirma recepción en el buzón" /><MetricCard label="Pendientes de reintento" value={data.statistics.retry_pending ?? 0} icon="clock" detail="Sujetos a espera y límite de intentos" /></div>
      <form className="panel commerce-form" onSubmit={filter} key={query}><h2>Filtrar actividad</h2><div className="commerce-form-grid">
        <label>Empresa<select name="organization_id" defaultValue={params.get('organization_id') ?? ''}><option value="">Todas / plataforma</option>{data.organizations.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
        <label>Evento<select name="event" defaultValue={params.get('event') ?? ''}><option value="">Todos</option>{Object.entries(notificationEvents).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Estado<select name="status" defaultValue={params.get('status') ?? ''}><option value="">Todos</option>{Object.entries(notificationStates).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Desde (UTC)<input name="since" type="date" defaultValue={params.get('since')?.slice(0, 10)} /></label><label>Hasta (UTC)<input name="until" type="date" defaultValue={params.get('until')?.slice(0, 10)} /></label></div><button className="action-button action-button--primary">Aplicar filtros</button>
      </form>
      <NotificationTable data={data} busy={busy} onRetry={async id => {
        if (busy || !window.confirm('¿Reintentar este mensaje pendiente? La aceptación SMTP no garantiza recepción.')) return
        setBusy(id); setError('')
        try { await retryNotification(id); setRevision(v => v + 1) } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo reintentar.') } finally { setBusy(null) }
      }} />
      <div className="commerce-actions"><button type="button" disabled={Number(params.get('offset') ?? 0) === 0} onClick={() => { params.set('offset', String(Math.max(0, Number(params.get('offset') ?? 0) - 50))); setParams(params) }}>Anterior</button><button type="button" disabled={Number(params.get('offset') ?? 0) + data.items.length >= data.total} onClick={() => { params.set('offset', String(Number(params.get('offset') ?? 0) + 50)); setParams(params) }}>Siguiente</button></div>
    </>}
  </section>
}

export function NotificationTable({ data, busy, onRetry }: { data: NotificationOverview; busy: string | null; onRetry: (id: string) => void }) {
  if (!data.items.length) return <p className="owner-empty">No hay notificaciones para estos filtros. Los próximos eventos comerciales quedarán registrados aquí.</p>
  return <div className="commerce-table" role="region" aria-label="Historial de notificaciones" tabIndex={0}><table><caption>Intentos y aceptación SMTP; no acredita entrega en buzón</caption><thead><tr><th scope="col">Evento / referencia</th><th scope="col">Empresa / destinatario</th><th scope="col">Estado</th><th scope="col">Fechas</th><th scope="col">Intentos / acciones</th></tr></thead>
    <tbody>{data.items.map(row => <tr key={row.id}><th scope="row">{notificationEvents[row.event]}<small className="owner-record-id">{row.reference}</small></th><td>{row.organizationId ? `Empresa #${row.organizationId}` : 'Plataforma'}<br />{row.recipient ?? 'Sin destinatario válido'}</td><td>{notificationStates[row.status]}{row.errorCode && <p>{errors[row.errorCode] ?? 'Error técnico registrado.'}</p>}</td><td>Creación: {date(row.createdAt)}<br />Último intento: {date(row.lastAttemptAt)}<br />Próximo: {date(row.nextAttemptAt)}<br />Aceptación SMTP: {date(row.smtpAcceptedAt)}</td><td>{row.attempts} / {data.maxAttempts}<br /><button type="button" disabled={busy !== null || !notificationRetryEligible(row, data.maxAttempts)} onClick={() => onRetry(row.id)}>{busy === row.id ? 'Procesando…' : 'Reintentar'}</button></td></tr>)}</tbody></table></div>
}
