import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiResponseError, acceptInvitation, loginGoogle, previewInvitation, registerInvitation, type AgroScanRole,
  type InvitationPreview } from '../../services/agroscanApi'
import { GoogleAccessButton } from './GoogleAccess'

export function InvitationAcceptance({ token, authenticated, onSuccess, onExisting, onCancel }:
  { token: string; authenticated: boolean; onSuccess: (role: AgroScanRole | 'superadmin') => void; onExisting: () => void; onCancel: () => void }) {
  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [acceptedRole, setAcceptedRole] = useState<AgroScanRole | 'superadmin' | null>(null)
  const inFlight = useRef(false)
  const confirmation = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (acceptedRole) confirmation.current?.focus() }, [acceptedRole])
  function fail(failure: unknown) {
    if (failure instanceof ApiResponseError && [404,410].includes(failure.status)) {
      setUnavailable(true); setError('Este enlace venció, ya fue utilizado o fue revocado. Solicita al emisor una nueva invitación.')
    } else setError(failure instanceof Error ? failure.message : 'No se pudo aceptar la invitación.')
  }
  useEffect(() => {
    let active = true
    previewInvitation(token).then((value) => { if (active) setPreview(value) },
      (failure: unknown) => { if (active) fail(failure) })
    return () => { active = false }
  }, [token])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (inFlight.current) return
    inFlight.current = true; setWorking(true); setError('')
    try {
      const role = authenticated ? await acceptInvitation(token, password) : await registerInvitation(token, { username, fullName, password })
      setPassword(''); setAcceptedRole(role)
    } catch (failure) {
      fail(failure)
    } finally { inFlight.current = false; setWorking(false) }
  }
  return <main className="agroscan-login"><section className="agroscan-login__form" aria-label="Aceptar invitación">
    <h1>Invitación empresarial</h1>
    {error && <p role="alert">{error}</p>}
    {!preview && !error && <p role="status">Verificando invitación…</p>}
    {acceptedRole ? <section><h2 tabIndex={-1} ref={confirmation}>Acceso empresarial activado</h2>
      <p>Tu cuenta quedó incorporada a {preview?.organizationName} como {preview?.role}. No se activó un pago ni una suscripción comercial.</p>
      <button className="action-button action-button--primary" onClick={() => onSuccess(acceptedRole)}>Ir al panel de AgroScan</button></section>
      : preview && !unavailable && <>
      <p>{preview.organizationName} te invita como {preview.role}. Correo destinatario: {preview.email}.</p>
      <p>Vence: {new Date(preview.expiresAt).toLocaleString('es-PE')}.</p>
      <p>1. Verifica la empresa y el rol. 2. Crea tu acceso o usa una cuenta existente. 3. Confirma y entra al panel.</p>
      <p>Elige una contraseña privada: el propietario no la conoce ni necesita recibirla. El enlace es personal y de un solo uso.</p>
      <form className="users-form" onSubmit={submit}>
        <fieldset disabled={working} aria-label="Datos para aceptar la invitación">
        {!authenticated && <>
          <div className="users-field"><label htmlFor="invite-fullname">Nombre completo</label><input id="invite-fullname" required minLength={2} maxLength={120} value={fullName} onChange={(event) => setFullName(event.target.value)} /></div>
          <div className="users-field"><label htmlFor="invite-username">Nuevo nombre de usuario</label><input id="invite-username" required minLength={3} maxLength={64} value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} /></div>
        </>}
        <div className="users-field"><label htmlFor="invite-password">{authenticated ? 'Confirma la contraseña de tu cuenta actual' : 'Elige tu contraseña'}</label>
          <input id="invite-password" required type="password" minLength={authenticated ? 1 : 12} maxLength={128}
            autoComplete={authenticated ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} /></div>
        <button className="action-button action-button--primary" disabled={working}>
          {working ? 'Aceptando…' : authenticated ? 'Aceptar en mi cuenta actual' : 'Crear cuenta y aceptar'}
        </button>
        </fieldset>
      </form>
      {!authenticated && <button type="button" disabled={working} onClick={onExisting}>Ya tengo una cuenta: iniciar sesión</button>}
      <div inert={working}><GoogleAccessButton onCredential={async (credential) => {
        if (inFlight.current) return
        inFlight.current = true; setWorking(true); setError('')
        try { const role = await loginGoogle(credential, token); setPassword(''); setAcceptedRole(role) }
        catch (failure) { fail(failure); throw failure }
        finally { inFlight.current = false; setWorking(false) }
      }} /></div>
    </>}
    {!acceptedRole && <button type="button" disabled={working} onClick={onCancel}>{unavailable ? 'Volver al acceso' : 'Cancelar invitación'}</button>}
  </section></main>
}
