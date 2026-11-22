import { useEffect, useRef, useState, type FormEvent } from 'react'
import { applicationOrganizations, decideApplication, type CommercialApplication, type DecisionInput } from './applicationsApi'
import { money } from './commercialApi'

export function ApplicationDecisionPanel({ application, onSaved }: { application: CommercialApplication; onSaved: (value: CommercialApplication) => void }) {
  const [action, setAction] = useState<'approve' | 'reject'>('approve')
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [mode, setMode] = useState('create')
  const [organizationId, setOrganizationId] = useState('')
  const [organizations, setOrganizations] = useState<Awaited<ReturnType<typeof applicationOrganizations>> | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement | null>(null)
  const working = useRef(false)
  const retry = useRef({ payload: '', key: crypto.randomUUID() })
  useEffect(() => { if (open) { dialog.current?.showModal(); dialog.current?.querySelector('textarea')?.focus() } }, [open])
  useEffect(() => {
    if (!open || mode !== 'existing' || action !== 'approve') return
    let active = true
    applicationOrganizations().then(items => { if (active) setOrganizations(items) }, () => { if (active) setError('No se pudo consultar empresas. Cancela y reintenta.') })
    return () => { active = false }
  }, [open, mode, action])
  function start(next: 'approve' | 'reject', button: HTMLButtonElement) {
    trigger.current = button; setAction(next); setReason(''); setError(''); setSuccess(''); setConfirmed(false); setMode('create'); setOrganizationId(''); setOpen(true)
  }
  function close() { if (!working.current) dialog.current?.close() }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (working.current) return
    const input: Omit<DecisionInput, 'idempotencyKey'> = { action, reason: reason.trim(),
      ...(action === 'approve' ? { approvedPlanId: application.requestedPlanId, identityConfirmed: confirmed,
        ...(mode === 'existing' ? { existingOrganizationId: Number(organizationId) } : {}) } : {}) }
    const payload = JSON.stringify(input)
    if (retry.current.payload !== payload) retry.current = { payload, key: crypto.randomUUID() }
    working.current = true; setBusy(true); setError('')
    try {
      const saved = await decideApplication(application.id, { ...input, idempotencyKey: retry.current.key })
      setSuccess(action === 'approve' ? 'Solicitud aprobada. Empresa asociada; genera la invitación inicial para incorporar al administrador. Sin pago ni suscripción activa.' : 'Solicitud rechazada. No se aprovisionó ninguna empresa ni cuenta.')
      onSaved(saved); dialog.current?.close()
    } catch (error) { setError(error instanceof Error ? error.message : 'No se guardó la decisión. Reintenta.') }
    finally { working.current = false; setBusy(false) }
  }
  return <>
    {success && <p role="status">{success}</p>}
    {['pending','under_review'].includes(application.status) && <div className="commerce-actions">
      <button className="action-button action-button--primary" aria-haspopup="dialog" onClick={e => start('approve', e.currentTarget)}>Aprobar</button>
      <button className="action-button action-button--secondary" aria-haspopup="dialog" onClick={e => start('reject', e.currentTarget)}>Rechazar</button></div>}
    <dialog ref={dialog} className="application-decision-dialog commerce-form" aria-labelledby="application-decision-title"
      onCancel={e => { if (working.current) e.preventDefault() }} onClose={() => { setOpen(false); if (trigger.current?.isConnected) trigger.current.focus(); else document.querySelector<HTMLElement>('[aria-label="Detalle de solicitud"] h2')?.focus() }}>
      {open && <form onSubmit={event => { void submit(event) }} aria-busy={busy}><h2 id="application-decision-title">{action === 'approve' ? 'Confirmar aprobación' : 'Confirmar rechazo'}</h2>
        <p>{application.companyName} · {application.plan.name} v{application.plan.version} · {money(application.plan.amountCents)} DEMO / {application.requestedPeriod === 'monthly' ? 'mes' : 'año'}.</p>
        <p>{action === 'approve' ? 'Se conservará la propuesta original. Esta acción no crea administradores, invitaciones ni suscripciones y no registra pagos.' : 'El rechazo es definitivo y quedará registrado. No crea empresas ni cuentas.'}</p>
        {error && <p role="alert" className="commerce-error">{error}</p>}
        <fieldset disabled={busy}><legend>Decisión administrativa</legend>
          <label>Motivo administrativo<textarea value={reason} required minLength={3} maxLength={1000} onChange={e => setReason(e.target.value)} /></label>
          {action === 'approve' && <>
            <label>Empresa a asociar<select value={mode} onChange={e => { setMode(e.target.value); setConfirmed(false) }}><option value="create">Crear empresa con el nombre solicitado</option><option value="existing">Vincular empresa existente verificada</option></select></label>
            {mode === 'existing' && <label>Empresa existente<select value={organizationId} required onChange={e => { setOrganizationId(e.target.value); setConfirmed(false) }}><option value="">{organizations ? 'Selecciona la empresa verificada' : 'Consultando empresas…'}</option>{organizations?.map(o => <option key={o.id} value={o.id}>{o.name} · ID {o.id}{!o.isActive ? ' · Suspendida (se conservará)' : ''}</option>)}</select></label>}
            <label className="application-identity-confirm"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />He verificado la identidad empresarial y la correspondencia de la empresa seleccionada con esta solicitud.</label>
          </>}
          <div className="commerce-actions"><button type="button" onClick={close}>Cancelar</button><button className="action-button action-button--primary" disabled={busy || reason.trim().length < 3 || (action === 'approve' && (!confirmed || (mode === 'existing' && !organizationId)))}>{busy ? 'Guardando decisión…' : action === 'approve' ? 'Confirmar aprobación' : 'Confirmar rechazo'}</button></div>
        </fieldset></form>}
    </dialog>
  </>
}
