import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiConnectionError, ApiResponseError, OrganizationSelectionRequiredError, clearOperatorSession,
  getBackendHealth, getSessionOrganizationId, getSessionOrganizations, getSessionRole,
  isAgroscanAuthenticated, isPlatformOwner, loginAgroscan, loginGoogle, selectOrganization,
  type AgroScanRole } from '../../services/agroscanApi'
import { GoogleAccessButton, GoogleLinkAccount } from './GoogleAccess'
import { InvitationAcceptance } from './InvitationAcceptance'
import { forgetInvitation, invitationFromLocation } from './googleGis'
import { PlatformDashboard } from '../../pages/PlatformDashboard'
import './AuthGate.css'

/** Barras decorativas del código de estación; puro ornamento de la etiqueta. */
const CODE_BARS = [3, 1, 2, 1, 1, 3, 1, 2, 4, 1, 1, 2, 1, 3, 1, 1, 2, 2, 1, 1, 4, 2, 1, 3, 1, 1, 2, 1, 3, 1, 1, 2, 3, 1, 2, 1, 1, 3, 2, 1, 1, 2, 1, 4]

/** Reloj de la estación: se monta solo en la pantalla de acceso. */
function StationClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return (
    <span className="agroscan-login__meta-right">
      <span className="agroscan-login__live" aria-hidden="true" />
      <span>Hora local</span>
      <b>{now.toLocaleTimeString('es-PE', { hour12: false })}</b>
    </span>
  )
}

/** Sesión por rol limitada a la pestaña. No persiste credenciales en el navegador. */
export function AuthGate({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [authenticated, setAuthenticated] = useState(isAgroscanAuthenticated)
  const [organizations, setOrganizations] = useState(getSessionOrganizations)
  const [activeOrganization, setActiveOrganization] = useState(getSessionOrganizationId)
  const [choosingOrganization, setChoosingOrganization] = useState(false)
  const [selectedOrganization, setSelectedOrganization] = useState('')
  const [invitationToken, setInvitationToken] = useState(invitationFromLocation)
  const [invitationLogin, setInvitationLogin] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [api, setApi] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    const receive = () => {
      const token = invitationFromLocation()
      if (token) { setInvitationToken(token); setInvitationLogin(false) }
    }
    window.addEventListener('hashchange', receive)
    return () => window.removeEventListener('hashchange', receive)
  }, [])

  useEffect(() => {
    let active = true
    getBackendHealth().then(
      () => { if (active) setApi('online') },
      () => { if (active) setApi('offline') },
    )
    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (working || !username.trim() || !password) return
    setWorking(true)
    setError(null)
    try {
      const role = await loginAgroscan(username, password)
      setPassword('')
      setAuthenticated(true)
      setOrganizations(getSessionOrganizations())
      setActiveOrganization(getSessionOrganizationId())
      if (role === 'revisor') navigate('/historial', { replace: true })
      if (role === 'superadmin') navigate('/plataforma', { replace: true })
    } catch (failure) {
      if (failure instanceof OrganizationSelectionRequiredError) {
        setPassword('')
        setOrganizations(getSessionOrganizations())
        setSelectedOrganization('')
        setChoosingOrganization(true)
        return
      }
      setError(failure instanceof ApiResponseError
        ? failure.status === 401 ? 'Usuario o contraseña incorrectos.' : failure.message
        : failure instanceof ApiConnectionError
          ? 'No se pudo conectar. Reintenta o solicita ayuda al administrador.'
          : 'No fue posible validar el inicio de sesión.')
    } finally {
      setWorking(false)
    }
  }

  async function changeOrganization(organizationId: number) {
    if (working) return
    setWorking(true)
    setError(null)
    try {
      const role = await selectOrganization(organizationId)
      setOrganizations(getSessionOrganizations())
      setActiveOrganization(getSessionOrganizationId())
      setChoosingOrganization(false)
      setAuthenticated(true)
      navigate(role === 'revisor' ? '/historial' : '/', { replace: true })
    } catch (failure) {
      clearOperatorSession()
      setAuthenticated(false)
      setChoosingOrganization(false)
      setOrganizations([])
      setActiveOrganization(null)
      setError(failure instanceof ApiResponseError ? failure.message : 'No fue posible validar la empresa. Inicia sesión nuevamente.')
    } finally {
      setWorking(false)
    }
  }

  function sessionReady(role: AgroScanRole | 'superadmin', accepted = false) {
    if (accepted) { forgetInvitation(); setInvitationToken(null) }
    setAuthenticated(true)
    setOrganizations(getSessionOrganizations())
    setActiveOrganization(getSessionOrganizationId())
    navigate(role === 'superadmin' ? '/plataforma' : role === 'revisor' ? '/historial' : '/', { replace: true })
  }

  async function googleLogin(credential: string) {
    try { sessionReady(await loginGoogle(credential)) }
    catch (failure) {
      if (failure instanceof OrganizationSelectionRequiredError) {
        setOrganizations(getSessionOrganizations()); setSelectedOrganization(''); setChoosingOrganization(true)
      } else { throw failure }
    }
  }

  if (invitationToken && (authenticated || !invitationLogin) && !choosingOrganization) {
    return <InvitationAcceptance key={invitationToken} token={invitationToken} authenticated={authenticated}
      onSuccess={(role) => sessionReady(role, true)} onExisting={() => setInvitationLogin(true)}
      onCancel={() => { forgetInvitation(); setInvitationToken(null); setAuthenticated(isAgroscanAuthenticated()) }} />
  }

  if (authenticated && isPlatformOwner()) {
    return <main className="platform-shell">
      <div className="agroscan-session">
        <span>Propietario de AgroScan</span>
        <GoogleLinkAccount />
        <button type="button" onClick={() => {
          clearOperatorSession(); setAuthenticated(false); setPassword(''); setError(null)
          navigate('/', { replace: true })
        }}>Cerrar sesión</button>
      </div>
      <PlatformDashboard />
    </main>
  }

  if (choosingOrganization && !authenticated) {
    return (
      <main className="agroscan-login">
        <form className="agroscan-login__form" aria-label="Seleccionar empresa" onSubmit={(event) => {
          event.preventDefault()
          void changeOrganization(Number(selectedOrganization))
        }}>
          <h1>Selecciona tu empresa</h1>
          <label htmlFor="agroscan-company-login">Empresa</label>
          <select id="agroscan-company-login" value={selectedOrganization} required disabled={working}
            onChange={(event) => setSelectedOrganization(event.target.value)}>
            <option value="" disabled>Selecciona una empresa</option>
            {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
          </select>
          <button className="agroscan-login__submit" type="submit" disabled={working || !selectedOrganization}>
            {working ? 'Verificando…' : 'Continuar'}
          </button>
          <button type="button" disabled={working} onClick={() => {
            clearOperatorSession(); setChoosingOrganization(false); setOrganizations([])
          }}>Cancelar</button>
        </form>
      </main>
    )
  }

  if (authenticated) {
    return (
      <>
        <div className="agroscan-session">
          <span>Sesión de {getSessionRole() === 'revisor' ? 'revisor (consulta)' : getSessionRole() === 'administrador' ? 'administrador' : 'operador'} activa</span>
          <GoogleLinkAccount />
          {organizations.length > 1 && <label className="agroscan-company-selector" htmlFor="agroscan-company-active">
            Empresa
            <select id="agroscan-company-active" value={activeOrganization ?? ''} disabled={working}
              onChange={(event) => { void changeOrganization(Number(event.target.value)) }}>
              {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
            </select>
          </label>}
          <button type="button" onClick={() => { clearOperatorSession(); setAuthenticated(false); setPassword(''); setShowPassword(false); setError(null); setOrganizations([]); setActiveOrganization(null) }}>Cerrar sesión</button>
        </div>
        {working ? <p role="status">Cambiando empresa…</p>
          : <Fragment key={activeOrganization ?? 'single'}>{children}</Fragment>}
      </>
    )
  }

  const apiLabel = api === 'online' ? 'en línea' : api === 'offline' ? 'sin enlace' : 'consultando'

  return (
    <main className="agroscan-login">
      <div className="agroscan-login__sheet">
        <header className="agroscan-login__meta">
          <span className="agroscan-login__meta-left">AgroScan</span>
          <StationClock />
        </header>

        <div className="agroscan-login__body">
          <section className="agroscan-login__identity" aria-labelledby="agroscan-login-brand">
            <p className="agroscan-login__kicker">Sistema de clasificación · IoT</p>

            <div className="agroscan-login__brand-wrap">
              <h1 className="agroscan-login__brand" id="agroscan-login-brand">AgroScan</h1>
            </div>

            <p className="agroscan-login__lede">Mango y tomate clasificados con visión artificial y pesaje en la misma estación. Cada pieza deja rastro: lote, peso, vistas y decisión.</p>

            <ul className="agroscan-login__status" aria-label="Estado de la estación">
              <li data-tone={api === 'online' ? 'ok' : api === 'offline' ? 'off' : 'wait'}>
                <span className="agroscan-login__dot" aria-hidden="true" />
                <span>Conexión</span>
                <b>{apiLabel}</b>
              </li>
              <li data-tone="wait">
                <span className="agroscan-login__dot" aria-hidden="true" />
                <span>Cámara RGB</span>
                <b>sin verificar</b>
              </li>
              <li data-tone="wait">
                <span className="agroscan-login__dot" aria-hidden="true" />
                <span>Báscula</span>
                <b>sin verificar</b>
              </li>
            </ul>

            <div className="agroscan-login__code" aria-hidden="true">
              <div className="agroscan-login__bars">
                {CODE_BARS.map((width, index) => <span key={index} style={{ width: `${width}px` }} />)}
              </div>
              <p>AGROSCAN-MVP · PROTOTIPO</p>
            </div>

            <span className="agroscan-login__stamp" aria-hidden="true">Estación local</span>
          </section>

          <form onSubmit={submit} className="agroscan-login__form" aria-labelledby="agroscan-login-title">
            <p className="agroscan-login__form-kicker">Control de acceso</p>
            <h2 id="agroscan-login-title">Identifícate</h2>
            <p className="agroscan-login__form-lede">Accede con tu cuenta de operador, revisor o administrador.</p>

            <div className="agroscan-login__fields">
              <div className="agroscan-login__field">
                <div className="agroscan-login__field-top">
                  <label htmlFor="agroscan-login-user">Usuario</label>
                  <span className="agroscan-login__field-num" aria-hidden="true">01</span>
                </div>
                <div className="agroscan-login__line">
                  <input
                    id="agroscan-login-user"
                    autoComplete="username"
                    placeholder="operador"
                    required
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    disabled={working}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? 'agroscan-login-error' : undefined}
                  />
                </div>
              </div>

              <div className="agroscan-login__field">
                <div className="agroscan-login__field-top">
                  <label htmlFor="agroscan-login-pass">Contraseña</label>
                  <span className="agroscan-login__field-num" aria-hidden="true">02</span>
                </div>
                <div className="agroscan-login__line">
                  <input
                    id="agroscan-login-pass"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={working}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? 'agroscan-login-error' : undefined}
                  />
                  <button
                    type="button"
                    className="agroscan-login__reveal"
                    onClick={() => setShowPassword((visible) => !visible)}
                    disabled={working}
                    aria-pressed={showPassword}
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  >
                    {showPassword ? 'Ocultar' : 'Ver'}
                  </button>
                </div>
              </div>
            </div>

            {error && (
              <p id="agroscan-login-error" role="alert" className="agroscan-login__error">
                <span className="agroscan-login__error-mark" aria-hidden="true" />
                <span>{error}</span>
              </p>
            )}

            <button type="submit" className="agroscan-login__submit" disabled={working || !username.trim() || !password}>
              {working
                ? <><span className="agroscan-login__spinner" aria-hidden="true" />Verificando…</>
                : <><span>Entrar a la estación</span><span className="agroscan-login__arrow" aria-hidden="true">→</span></>}
            </button>

            <p className="agroscan-login__note">La sesión vive solo en esta pestaña y se cierra al recargar. No compartas tus credenciales.</p>
            <GoogleAccessButton onCredential={googleLogin} />
          </form>
        </div>

        <footer className="agroscan-login__foot">
          <span>AgroScan · clasificación de mango y tomate</span>
          <span>¿Sin acceso? Contacta al administrador de la estación</span>
        </footer>
      </div>
    </main>
  )
}
