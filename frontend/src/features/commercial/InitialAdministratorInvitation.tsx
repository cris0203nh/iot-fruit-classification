import { useEffect, useRef, useState } from 'react'
import { invitationLink } from '../auth/googleGis'
import { manageInitialInvitation, type CommercialApplication } from './applicationsApi'

const statusLabel = { pending: 'Pendiente de aceptación', accepted: 'Aceptada', expired: 'Vencida', revoked: 'Revocada' }
export function InitialAdministratorInvitation({ application }: { application: CommercialApplication }) {
  const [invitation, setInvitation] = useState(application.initialInvitation ?? null)
  const [token, setToken] = useState('')
  const [action, setAction] = useState<'issue' | 'reissue' | 'revoke'>('issue')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const opener = useRef<HTMLButtonElement | null>(null)
  const linkField = useRef<HTMLTextAreaElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const requestKey = useRef('')
  const inFlight = useRef(false)
  useEffect(() => { if (open) dialog.current?.showModal() }, [open])
  if (application.status !== 'approved') return null
  const accepted = application.provisioningState === 'awaiting_demo_order' || invitation?.status === 'accepted'
  const link = token ? invitationLink(window.location.origin, token) : ''
  function start(next: typeof action, button: HTMLButtonElement) {
    opener.current = button; requestKey.current = crypto.randomUUID(); setAction(next); setError(''); setOpen(true)
  }
  async function confirm() {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true); setError('')
    try {
      const result = await manageInitialInvitation(application.id, { action, idempotencyKey: requestKey.current })
      setInvitation(result.invitation); setToken(result.token ?? '')
      setNotice(action === 'revoke' ? 'Invitación revocada. El enlace anterior ya no permite aceptar.'
        : result.token ? 'Enlace generado. Cópialo y entrégalo manualmente solo al contacto autorizado.'
          : 'Operación reconocida. El enlace no se vuelve a mostrar; reemite si no lo conservaste.')
      dialog.current?.close()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo guardar la invitación.') }
    finally { inFlight.current = false; setBusy(false) }
  }
  async function copyLink() {
    try {
      if (!navigator.clipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(link)
      setNotice('Enlace copiado. Compártelo por un canal privado.')
    } catch { linkField.current?.select(); setNotice('Selecciona el enlace y cópialo manualmente.') }
  }
  return <section className="commerce-confirm" aria-label="Primer administrador"><h3 ref={heading} tabIndex={-1}>Primer administrador empresarial</h3>
    <p>Destinatario: {application.contactEmail} · Rol: administrador. Empresa ID {application.organizationId}.</p>
    {invitation && <p>Invitación: <strong>{statusLabel[invitation.status]}</strong> · Vence: {new Date(invitation.expiresAt).toLocaleString('es-PE')}.</p>}
    {accepted ? <p role="status">Administrador incorporado{application.administratorActive ? ' y activo' : ' (consulta el estado vigente de su cuenta y membresía)'}. {application.provisioningState === 'completed' ? 'Alta comercial DEMO completada' : 'Contratación DEMO pendiente'}; no se realizó ningún cobro.</p>
      : <><p>La persona elige su contraseña o autoriza Google. No crea una suscripción ni concede privilegios globales.</p>
        <p>Después de la aceptación, actualiza la bandeja y abre el detalle para comprobar la incorporación.</p>
        <div className="commerce-actions">{!invitation ? <button aria-haspopup="dialog" onClick={e => start('issue',e.currentTarget)}>Generar invitación inicial</button>
          : <><button aria-haspopup="dialog" onClick={e => start('reissue',e.currentTarget)}>Reemitir enlace</button>{invitation.status === 'pending' && <button aria-haspopup="dialog" onClick={e => start('revoke',e.currentTarget)}>Revocar invitación</button>}</>}</div></>}
    {notice && <p role="status">{notice}</p>}
    {link && !accepted && <div className="commerce-form"><label>Enlace privado de un solo uso<textarea ref={linkField} readOnly value={link} autoComplete="off" spellCheck={false} /></label>
      <button onClick={() => { void copyLink() }}>Copiar enlace</button>
      <p>Solo se muestra al emitirlo. No lo pegues en repositorios, logs ni capturas públicas.</p></div>}
    <dialog ref={dialog} className="application-decision-dialog" aria-labelledby="initial-invitation-title" onCancel={e => { if (inFlight.current) e.preventDefault() }}
      onClose={() => { setOpen(false); if (opener.current?.isConnected) opener.current.focus(); else heading.current?.focus() }}>
      {open && <><h2 id="initial-invitation-title">{action === 'revoke' ? 'Revocar invitación' : action === 'reissue' ? 'Reemitir invitación' : 'Invitar al primer administrador'}</h2>
        <p>{application.companyName} · {application.contactEmail} · Administrador.</p>
        <p>{action === 'revoke' ? 'El enlace dejará de funcionar. No retira membresías ya aceptadas.' : 'El enlace vence en 48 horas. Se entrega manualmente y no solicita pagos.'}</p>
        {action === 'reissue' && <p>El enlace anterior quedará invalidado, incluso si todavía no había vencido.</p>}
        {error && <p role="alert">{error}</p>}<div className="commerce-actions"><button disabled={busy} onClick={() => dialog.current?.close()}>Cancelar</button><button disabled={busy} onClick={() => { void confirm() }}>{busy ? 'Guardando…' : 'Confirmar'}</button></div></>}
    </dialog>
  </section>
}
