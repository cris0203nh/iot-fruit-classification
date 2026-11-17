import { useEffect, useState, type FormEvent } from 'react'
import { createPlatformAdministrator, createPlatformOrganization, designatePlatformAdministrator, listPlatformAdministrators,
  loadPlatformOverview, removePlatformAdministrator, setPlatformOrganizationStatus,
  type PlatformMetrics, type PlatformOverview, type PlatformUser } from '../services/agroscanApi'
import './UsersPage.css'
import './PlatformDashboard.css'

export function PlatformSummary({ metrics }: { metrics: PlatformMetrics }) {
  return <section className="users-summary" aria-label="Resumen de plataforma">
    <article><div><strong>{metrics.organizations}</strong><span>Empresas · {metrics.activeOrganizations} activas</span></div></article>
    <article><div><strong>{metrics.users}</strong><span>Usuarios · {metrics.activeUsers} activos</span></div></article>
    <article><div><strong>{metrics.evaluations}</strong><span>Evaluaciones registradas</span></div></article>
  </section>
}

export function PlatformDashboard() {
  const [overview, setOverview] = useState<PlatformOverview | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [company, setCompany] = useState('')
  const [user, setUser] = useState('')
  const [newAccount, setNewAccount] = useState(false)
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [administrators, setAdministrators] = useState<PlatformUser[] | null>(null)
  const [adminError, setAdminError] = useState('')

  useEffect(() => {
    let active = true
    loadPlatformOverview().then((data) => { if (active) setOverview(data) },
      (failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los datos.') })
    return () => { active = false }
  }, [refresh])

  useEffect(() => {
    if (!company) return
    let active = true
    listPlatformAdministrators(Number(company)).then((data) => { if (active) setAdministrators(data) },
      (failure: unknown) => { if (active) setAdminError(failure instanceof Error ? failure.message : 'No se pudieron cargar los administradores.') })
    return () => { active = false }
  }, [company, refresh])

  function reload() {
    setOverview(null)
    setAdministrators(null)
    setError('')
    setAdminError('')
    setRefresh((value) => value + 1)
  }

  async function act(operation: () => Promise<void>, success: string) {
    if (saving) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await operation()
      setMessage(success)
      reload()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo completar la operación.')
    } finally {
      setSaving(false)
    }
  }

  function register(event: FormEvent) {
    event.preventDefault()
    void act(async () => {
      const created = await createPlatformOrganization(name)
      setName('')
      setCompany(String(created.id))
      setUser('')
      setPassword(''); setUsername(''); setFullName(''); setNewAccount(false)
    }, 'Empresa registrada.')
  }

  const selected = overview?.organizations.find((organization) => String(organization.id) === company)
  return <div className="page-stack platform-dashboard">
    <header className="section-heading">
      <div><p className="eyebrow">AgroScan</p><h1>Administración de empresas</h1></div>
      <button className="action-button action-button--secondary" type="button" disabled={saving} onClick={reload}>Actualizar</button>
    </header>
    {error && <p className="users-message users-message--error" role="alert">{error}</p>}
    {message && <p className="users-message users-message--success" role="status">{message}</p>}
    {!overview && !error && <p role="status">Consultando empresas…</p>}
    {overview && <>
      <PlatformSummary metrics={overview.metrics} />
      <section className="panel users-form-panel" aria-labelledby="new-company-heading">
        <h2 id="new-company-heading">Registrar empresa</h2>
        <form className="users-form" onSubmit={register}>
          <div className="users-field"><label htmlFor="platform-company-name">Nombre de la empresa</label>
            <input id="platform-company-name" value={name} minLength={2} maxLength={120} required disabled={saving}
              onChange={(event) => setName(event.target.value)} /></div>
          <div className="users-form__actions"><button className="action-button action-button--primary" disabled={saving || name.trim().length < 2}>Registrar empresa</button></div>
        </form>
      </section>
      <section className="panel users-list-panel" aria-labelledby="company-list-heading">
        <h2 id="company-list-heading">Empresas</h2>
        {!overview.organizations.length ? <p>No hay empresas registradas.</p> : <div className="users-table-wrapper">
          <table className="users-table"><thead><tr><th>Empresa</th><th>Estado</th><th>Usuarios</th><th>Evaluaciones</th><th>Acción</th></tr></thead>
            <tbody>{overview.organizations.map((organization) => <tr key={organization.id}>
              <td>{organization.name}</td><td>{organization.isActive ? 'Activa' : 'Suspendida'}</td>
              <td>{organization.userCount}</td><td>{organization.evaluationCount}</td>
              <td><button className="action-button action-button--secondary" type="button" disabled={saving}
                aria-label={`${organization.isActive ? 'Suspender' : 'Activar'} ${organization.name}`}
                onClick={() => { void act(() => setPlatformOrganizationStatus(organization.id, !organization.isActive),
                  organization.isActive ? 'Empresa suspendida.' : 'Empresa activada.') }}>
                {organization.isActive ? 'Suspender' : 'Activar'}</button></td>
            </tr>)}</tbody>
          </table>
        </div>}
      </section>
      <section className="panel users-form-panel" aria-labelledby="company-admin-heading">
        <h2 id="company-admin-heading">Administradores empresariales</h2>
        <form className="users-form" onSubmit={(event) => {
          event.preventDefault()
          void act(async () => {
            if (newAccount) {
              await createPlatformAdministrator(Number(company), { username, fullName, password })
              setUsername(''); setFullName(''); setPassword(''); setNewAccount(false)
            } else {
              await designatePlatformAdministrator(Number(company), Number(user))
            }
          }, 'Administrador empresarial designado.')
        }}>
          <div className="users-field"><label htmlFor="platform-company-select">Empresa</label>
            <select id="platform-company-select" required value={company} disabled={saving} onChange={(event) => {
              setCompany(event.target.value); setUser(''); setAdministrators(null); setAdminError('')
              setPassword(''); setUsername(''); setFullName('')
            }}><option value="" disabled>Selecciona una empresa</option>
              {overview.organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
            </select></div>
          <label><input type="checkbox" checked={newAccount} disabled={saving} onChange={(event) => {
            setNewAccount(event.target.checked); setPassword(''); setUser('')
          }} /> Crear una cuenta nueva</label>
          {!newAccount && <div className="users-field"><label htmlFor="platform-user-select">Usuario registrado</label>
            <select id="platform-user-select" required value={user} disabled={saving || !selected?.isActive}
              onChange={(event) => setUser(event.target.value)}><option value="" disabled>Selecciona un usuario</option>
              {overview.users.filter((account) => account.isActive).map((account) =>
                <option key={account.id} value={account.id}>{account.fullName} ({account.username})</option>)}
            </select></div>}
          {newAccount && <>
            <div className="users-field"><label htmlFor="platform-admin-name">Nombre completo</label>
              <input id="platform-admin-name" value={fullName} required minLength={2} maxLength={120} disabled={saving}
                onChange={(event) => setFullName(event.target.value)} /></div>
            <div className="users-field"><label htmlFor="platform-admin-username">Nombre de usuario</label>
              <input id="platform-admin-username" value={username} required minLength={3} maxLength={64} autoComplete="off" disabled={saving}
                onChange={(event) => setUsername(event.target.value)} /></div>
            <div className="users-field"><label htmlFor="platform-admin-password">Contraseña</label>
              <input id="platform-admin-password" value={password} type="password" required minLength={12} maxLength={128}
                autoComplete="new-password" disabled={saving} onChange={(event) => setPassword(event.target.value)} /></div>
          </>}
          {selected && !selected.isActive && <p>Activa la empresa para designar administradores.</p>}
          <div className="users-form__actions"><button className="action-button action-button--primary"
            disabled={saving || !company || !selected?.isActive || (newAccount ? !username.trim() || !fullName.trim() || password.length < 12 : !user)}>Designar administrador</button></div>
        </form>
        {adminError && <p role="alert">{adminError}</p>}
        {company && !administrators && !adminError && <p role="status">Consultando administradores…</p>}
        {company && administrators && (administrators.length ? <ul className="platform-administrators">
          {administrators.map((account) => <li key={account.id}>
            <span>{account.fullName} ({account.username}){account.isActive ? '' : ' · Inactivo'}</span>
            <button className="action-button action-button--secondary" type="button" disabled={saving}
              aria-label={`Retirar administrador ${account.username}`} onClick={() => {
                void act(() => removePlatformAdministrator(Number(company), account.id), 'Rol administrativo retirado.')
              }}>Retirar rol</button>
          </li>)}
        </ul> : <p>Esta empresa todavía no tiene administradores designados.</p>)}
      </section>
    </>}
  </div>
}
