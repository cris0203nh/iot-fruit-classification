import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MetricCard } from '../components/MetricCard'
import { Icon } from '../components/layout/Icon'
import { createPlatformAdministrator, createPlatformOrganization, designatePlatformAdministrator, listPlatformAdministrators,
  loadPlatformOverview, removePlatformAdministrator, setPlatformOrganizationStatus,
  type PlatformMetrics, type PlatformOverview, type PlatformUser } from '../services/agroscanApi'
import './UsersPage.css'
import './PlatformDashboard.css'

export function PlatformSummary({ metrics }: { metrics: PlatformMetrics }) {
  return <section className="owner-metrics" aria-label="Resumen de plataforma">
    <MetricCard icon="boxes" label={`Empresas · ${metrics.activeOrganizations} activas`} value={metrics.organizations} detail="Organizaciones registradas" />
    <MetricCard icon="user" tone="blue" label={`Usuarios · ${metrics.activeUsers} activos`} value={metrics.users} detail="Cuentas de la plataforma" />
    <MetricCard icon="clipboard" tone="amber" label="Evaluaciones registradas" value={metrics.evaluations} detail="Trazabilidad acumulada" />
  </section>
}

export function PlatformDashboard({ section = 'companies' }: { section?: 'companies' | 'administrators' }) {
  const [parameters] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const [editingAdministrator, setEditingAdministrator] = useState(false)
  const [query, setQuery] = useState('')
  const [overview, setOverview] = useState<PlatformOverview | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [company, setCompany] = useState(() => parameters.get('empresa') ?? '')
  const [user, setUser] = useState('')
  const [newAccount, setNewAccount] = useState(false)
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [administrators, setAdministrators] = useState<PlatformUser[] | null>(null)
  const [adminError, setAdminError] = useState('')
  const editorRef = useRef<HTMLElement>(null)
  const editorOpener = useRef<HTMLButtonElement>(null)
  const wasEditing = useRef(false)
  useEffect(() => {
    const open = creating || editingAdministrator
    if (open) editorRef.current?.querySelector<HTMLElement>('input,select')?.focus()
    else if (wasEditing.current) editorOpener.current?.focus()
    wasEditing.current = open
  }, [creating, editingAdministrator])

  useEffect(() => {
    let active = true
    loadPlatformOverview().then((data) => { if (active) setOverview(data) },
      (failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los datos.') })
    return () => { active = false }
  }, [refresh])

  useEffect(() => {
    if (section !== 'administrators' || !company) return
    let active = true
    listPlatformAdministrators(Number(company)).then((data) => { if (active) setAdministrators(data) },
      (failure: unknown) => { if (active) setAdminError(failure instanceof Error ? failure.message : 'No se pudieron cargar los administradores.') })
    return () => { active = false }
  }, [company, refresh, section])

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
      setCreating(false)
      setCompany(String(created.id))
      setUser('')
      setPassword(''); setUsername(''); setFullName(''); setNewAccount(false)
    }, 'Empresa registrada.')
  }

  const selected = overview?.organizations.find((organization) => String(organization.id) === company)
  return <div className="page-stack platform-dashboard">
    <header className="section-heading">
      <div><p className="eyebrow">Plataforma / {section === 'companies' ? 'Organizaciones' : 'Accesos empresariales'}</p>
        <h1>{section === 'companies' ? 'Empresas' : 'Administradores'}</h1>
        <p className="owner-page-copy">{section === 'companies' ? 'Supervisa las organizaciones y su actividad en AgroScan.' : 'Gestiona responsables por empresa, sin conceder privilegios globales.'}</p></div>
      <button className="action-button action-button--secondary" type="button" disabled={saving} onClick={reload}>Actualizar</button>
    </header>
    {error && <p className="users-message users-message--error" role="alert">{error}</p>}
    {message && <p className="users-message users-message--success" role="status">{message}</p>}
    {!overview && !error && <p role="status">Cargando datos de plataforma…</p>}
    {error && !overview && <button className="action-button action-button--secondary" onClick={reload}>Reintentar consulta</button>}
    {overview && <>
      <PlatformSummary metrics={overview.metrics} />
      {section === 'companies' && <div className="owner-list-toolbar"><label htmlFor="owner-company-search">Buscar empresa
        <input id="owner-company-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Nombre de la empresa" /></label>
        <button ref={editorOpener} disabled={saving} type="button" className="action-button action-button--primary" aria-expanded={creating} aria-controls="owner-company-editor" onClick={() => setCreating(v => !v)}>{creating ? 'Cerrar formulario' : 'Registrar empresa'}</button></div>}
      {section === 'companies' && creating && <section ref={editorRef} onKeyDown={event => { if (event.key === 'Escape' && !saving) setCreating(false) }} id="owner-company-editor" className="panel users-form-panel owner-editor" aria-labelledby="new-company-heading">
        <h2 id="new-company-heading">Registrar empresa</h2>
        <form className="users-form" onSubmit={register}>
          <div className="users-field"><label htmlFor="platform-company-name">Nombre de la empresa</label>
            <input id="platform-company-name" value={name} minLength={2} maxLength={120} required disabled={saving}
              onChange={(event) => setName(event.target.value)} /></div>
          <div className="users-form__actions"><button className="action-button action-button--primary" disabled={saving || name.trim().length < 2}>Registrar empresa</button></div>
        </form>
      </section>}
      {section === 'companies' && <section className="panel users-list-panel" aria-labelledby="company-list-heading">
        <h2 id="company-list-heading">Empresas</h2>
        {!overview.organizations.length ? <p>No hay empresas registradas. Usa «Registrar empresa» para crear la primera.</p> : <div className="users-table-wrapper" role="region" aria-label="Empresas registradas" tabIndex={0}>
          <table className="users-table"><caption className="owner-table-caption">Organizaciones registradas y actividad actual</caption><thead><tr><th scope="col">Empresa</th><th scope="col">Estado</th><th scope="col">Usuarios</th><th scope="col">Evaluaciones</th><th scope="col">Acciones</th></tr></thead>
            <tbody>{overview.organizations.filter(organization => organization.name.toLocaleLowerCase('es').includes(query.trim().toLocaleLowerCase('es'))).map((organization) => <tr key={organization.id}>
              <td><strong>{organization.name}</strong><small className="owner-record-id">Empresa #{organization.id}</small></td><td><span className={`owner-status ${organization.isActive ? 'owner-status--active' : 'owner-status--suspended'}`}>{organization.isActive ? 'Activa' : 'Suspendida'}</span></td>
              <td>{organization.userCount}</td><td>{organization.evaluationCount}</td>
              <td><div className="owner-row-actions"><Link className="text-link" to={`/plataforma/administradores?empresa=${organization.id}`}>Administradores</Link><button className="action-button action-button--secondary" type="button" disabled={saving}
                aria-label={`${organization.isActive ? 'Suspender' : 'Activar'} ${organization.name}`}
                onClick={() => { if (!window.confirm(`¿${organization.isActive ? 'Suspender' : 'Activar'} ${organization.name}?`)) return; void act(() => setPlatformOrganizationStatus(organization.id, !organization.isActive),
                  organization.isActive ? 'Empresa suspendida.' : 'Empresa activada.') }}>
                {organization.isActive ? 'Suspender' : 'Activar'}</button></div></td>
            </tr>)}</tbody>
          </table>
        </div>}
        {overview.organizations.length > 0 && !overview.organizations.some(o => o.name.toLocaleLowerCase('es').includes(query.trim().toLocaleLowerCase('es'))) && <p role="status">No hay empresas que coincidan con la búsqueda.</p>}
      </section>}
      {section === 'administrators' && <section className="panel users-form-panel" aria-labelledby="company-admin-heading">
        <h2 id="company-admin-heading">Administradores empresariales</h2>
        <p className="owner-page-copy">Asigna una persona responsable a la empresa elegida. Este permiso no da acceso global a AgroScan.</p>
        <div className="owner-assignment-step"><span className="owner-step-number" aria-hidden="true">1</span><div><h3>Elige la empresa</h3><p>La asignación se aplicará únicamente a esta organización.</p></div></div>
        <div className="owner-list-toolbar"> <div className="users-field"><label htmlFor="platform-company-select">Empresa que administrará</label>
            <select id="platform-company-select" required value={company} disabled={saving} onChange={(event) => {
              setCompany(event.target.value); setUser(''); setAdministrators(null); setAdminError('')
              setPassword(''); setUsername(''); setFullName(''); setEditingAdministrator(false)
            }}><option value="" disabled>Selecciona una empresa</option>
              {overview.organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
            </select></div>

          <button ref={editorOpener} type="button" className="action-button action-button--primary" disabled={!selected?.isActive || saving} aria-expanded={editingAdministrator} aria-controls="owner-admin-editor" onClick={() => { setEditingAdministrator(v => !v); setPassword('') }}>{editingAdministrator ? 'Cerrar asignación' : 'Continuar con esta empresa'}<Icon name="arrow-right" size={17} /></button>
        </div>
        {!company && <p className="owner-empty" role="status">Selecciona una empresa. Solo verás las asignaciones de la organización elegida.</p>}
        {editingAdministrator && <section ref={editorRef} id="owner-admin-editor" className="owner-editor" onKeyDown={event => { if (event.key === 'Escape' && !saving) { setEditingAdministrator(false); setPassword('') } }}><h3>Designar administrador empresarial</h3><form className="users-form" onSubmit={(event) => {
          event.preventDefault()
          void act(async () => {
            if (newAccount) {
              await createPlatformAdministrator(Number(company), { username, fullName, password })
              setUsername(''); setFullName(''); setPassword(''); setNewAccount(false)
            } else {
              await designatePlatformAdministrator(Number(company), Number(user))
            }
            setEditingAdministrator(false); setUser('')
          }, 'Administrador empresarial designado.')
        }}>
          <div className="owner-assignment-step"><span className="owner-step-number" aria-hidden="true">2</span><div><h3>Elige cómo asignar a la persona</h3><p>Empresa seleccionada: <strong>{selected?.name}</strong></p></div></div>
          <fieldset className="owner-account-options" disabled={saving}><legend>Tipo de asignación</legend>
            <label className={`owner-account-option ${!newAccount ? 'is-selected' : ''}`}>
              <input type="radio" name="admin-account-path" checked={!newAccount} onChange={() => { setNewAccount(false); setPassword(''); setUser('') }} />
              <span><strong>Usuario existente</strong><small>Asigna el rol a una cuenta que ya está registrada.</small></span>
            </label>
            <label className={`owner-account-option ${newAccount ? 'is-selected' : ''}`}>
              <input type="radio" name="admin-account-path" checked={newAccount} onChange={() => { setNewAccount(true); setPassword(''); setUser('') }} />
              <span><strong>Crear cuenta nueva</strong><small>Registra a la persona y asígnala a esta empresa.</small></span>
            </label>
          </fieldset>
          {!newAccount && <div className="users-field"><label htmlFor="platform-user-select">Usuario registrado</label>
            <select id="platform-user-select" required value={user} disabled={saving || !selected?.isActive}
              onChange={(event) => setUser(event.target.value)}><option value="" disabled>Selecciona un usuario</option>
              {overview.users.filter((account) => account.isActive).map((account) =>
                <option key={account.id} value={account.id}>{account.fullName} ({account.username})</option>)}
            </select></div>}
          {newAccount && <div className="owner-new-account-grid">
            <div className="users-field"><label htmlFor="platform-admin-name">Nombre completo</label>
              <input id="platform-admin-name" value={fullName} required minLength={2} maxLength={120} disabled={saving}
                onChange={(event) => setFullName(event.target.value)} /></div>
            <div className="users-field"><label htmlFor="platform-admin-username">Nombre de usuario</label>
              <input id="platform-admin-username" value={username} required minLength={3} maxLength={64} autoComplete="off" disabled={saving}
                onChange={(event) => setUsername(event.target.value)} /></div>
            <div className="users-field"><label htmlFor="platform-admin-password">Contraseña</label>
              <input id="platform-admin-password" value={password} type="password" required minLength={12} maxLength={128}
                autoComplete="new-password" disabled={saving} onChange={(event) => setPassword(event.target.value)} /></div>
          </div>}
          {selected && !selected.isActive && <p>Activa la empresa para designar administradores.</p>}
          <div className="owner-assignment-confirm"><div className="owner-assignment-step"><span className="owner-step-number" aria-hidden="true">3</span><div><h3>Confirma la asignación</h3><p>{newAccount ? (fullName.trim() || 'La nueva cuenta') : (overview.users.find(account => account.id === Number(user))?.fullName || 'La persona seleccionada')} recibirá el rol de administrador empresarial en <strong>{selected?.name}</strong>.</p></div></div>
          <div className="users-form__actions"><button className="action-button action-button--primary"
            disabled={saving || !company || !selected?.isActive || (newAccount ? !username.trim() || !fullName.trim() || password.length < 12 : !user)}>{saving ? 'Asignando…' : newAccount ? 'Crear cuenta y asignar administrador' : 'Confirmar asignación de administrador'}</button>
            <button type="button" className="action-button action-button--secondary" disabled={saving} onClick={() => { setEditingAdministrator(false); setPassword('') }}>Cancelar</button></div></div>
        </form></section>}
        {adminError && <p role="alert">{adminError}</p>}
        {company && !administrators && !adminError && <p role="status">Consultando administradores…</p>}
        {company && administrators && (administrators.length ? <div className="users-table-wrapper" role="region" aria-label="Administradores de la empresa" tabIndex={0}>
          <table className="users-table"><caption className="owner-table-caption">Administradores de {selected?.name}</caption><thead><tr><th scope="col">Cuenta</th><th scope="col">Estado</th><th scope="col">Permiso</th><th scope="col">Acci?n</th></tr></thead><tbody>
          {administrators.map(account => <tr key={account.id}><td><strong>{account.fullName}</strong><small className="owner-record-id">@{account.username}</small></td><td><span className={`owner-status ${account.isActive ? 'owner-status--active' : 'owner-status--suspended'}`}>{account.isActive ? 'Activo' : 'Inactivo'}</span></td><td>Administrador empresarial</td><td>
            <button className="action-button action-button--secondary" type="button" disabled={saving}
              aria-label={`Retirar administrador ${account.username}`} onClick={() => {
                if (window.confirm(`¿Retirar el rol administrativo de ${account.username}?`)) void act(() => removePlatformAdministrator(Number(company), account.id), 'Rol administrativo retirado.')
              }}>Retirar rol</button>
          </td></tr>)}
          </tbody></table></div> : <p className="owner-empty">Esta empresa todavía no tiene administradores. Usa «Designar administrador» para asignar una cuenta existente o crear una nueva.</p>)}
      </section>}
    </>}
  </div>
}
