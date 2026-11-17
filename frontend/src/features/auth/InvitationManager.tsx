import { useEffect, useState, type FormEvent } from 'react'
import { createInvitation, listInvitations, revokeInvitation, type AgroScanRole, type EnterpriseInvitation } from '../../services/agroscanApi'
import { invitationLink } from './googleGis'

export function InvitationManager() {
  const [items, setItems] = useState<EnterpriseInvitation[] | null>(null)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<AgroScanRole>('operador')
  const [link, setLink] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let active = true
    listInvitations().then((value) => { if (active) setItems(value) },
      (failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : 'No se pudieron consultar las invitaciones.') })
    return () => { active = false }
  }, [refresh])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (working) return
    setWorking(true); setError(''); setLink('')
    try {
      const created = await createInvitation(email, role)
      setLink(invitationLink(window.location.origin, created.token))
      setEmail(''); setRefresh((value) => value + 1)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo crear la invitación.') }
    finally { setWorking(false) }
  }
  return <section className="panel users-form-panel" aria-labelledby="invite-heading">
    <h2 id="invite-heading">Invitar a esta empresa</h2>
    {error && <p role="alert">{error}</p>}
    <form className="users-form" onSubmit={submit}>
      <div className="users-field"><label htmlFor="invite-email">Correo del destinatario</label><input id="invite-email" type="email" required maxLength={254} value={email} disabled={working} onChange={(event) => setEmail(event.target.value)} /></div>
      <div className="users-field"><label htmlFor="invite-role">Rol en esta empresa</label><select id="invite-role" value={role} disabled={working} onChange={(event) => setRole(event.target.value as AgroScanRole)}>
        <option value="operador">Operador</option><option value="revisor">Revisor</option><option value="administrador">Administrador empresarial</option>
      </select></div>
      <button className="action-button action-button--primary" disabled={working}>Crear invitación</button>
    </form>
    {link && <div className="users-field"><label htmlFor="manual-invitation-link">Enlace para entregar personalmente</label>
      <input id="manual-invitation-link" value={link} readOnly onFocus={(event) => event.target.select()} />
      <p>Enlace de un solo uso, válido durante 48 horas. Compártelo únicamente con el destinatario; no se enviará correo automáticamente.</p>
    </div>}
    {items && <ul>{items.map((item) => <li key={item.id}>
      {item.email} · {item.role} · {{ pending: 'Pendiente', accepted: 'Aceptada', revoked: 'Revocada', expired: 'Vencida' }[item.status]}
      {item.status === 'pending' && <button type="button" disabled={working} onClick={async () => {
        setWorking(true); setError('')
        try { await revokeInvitation(item.id); setLink(''); setRefresh((value) => value + 1) }
        catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo revocar la invitación.') }
        finally { setWorking(false) }
      }}>Revocar invitación a {item.email}</button>}
    </li>)}</ul>}
  </section>
}
