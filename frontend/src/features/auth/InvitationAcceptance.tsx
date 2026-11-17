import { useEffect, useState, type FormEvent } from 'react'
import { acceptInvitation, loginGoogle, previewInvitation, registerInvitation, type AgroScanRole,
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
  useEffect(() => {
    let active = true
    previewInvitation(token).then((value) => { if (active) setPreview(value) },
      (failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : 'Invitación no válida.') })
    return () => { active = false }
  }, [token])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (working) return
    setWorking(true); setError('')
    try {
      const role = authenticated ? await acceptInvitation(token, password) : await registerInvitation(token, { username, fullName, password })
      setPassword(''); onSuccess(role)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo aceptar la invitación.')
    } finally { setWorking(false) }
  }
  return <main className="agroscan-login"><section className="agroscan-login__form" aria-label="Aceptar invitación">
    <h1>Invitación empresarial</h1>
    {error && <p role="alert">{error}</p>}
    {!preview && !error && <p role="status">Verificando invitación…</p>}
    {preview && <>
      <p>{preview.organizationName} te invita como {preview.role}. Correo destinatario: {preview.email}.</p>
      <p>Vence: {new Date(preview.expiresAt).toLocaleString('es-PE')}.</p>
      <form className="users-form" onSubmit={submit}>
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
      </form>
      {!authenticated && <button type="button" onClick={onExisting}>Ya tengo una cuenta: iniciar sesión</button>}
      <GoogleAccessButton onCredential={async (credential) => {
        const role = await loginGoogle(credential, token); onSuccess(role)
      }} />
    </>}
    <button type="button" disabled={working} onClick={onCancel}>Cancelar invitación</button>
  </section></main>
}
