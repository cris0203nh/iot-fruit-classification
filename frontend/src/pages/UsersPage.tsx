
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import type { FormEvent } from 'react'

import {
  listAdminUsers,
  createAdminUser,
  updateAdminUserRole,
  updateAdminUserStatus,
  getSessionRole,
  ApiConnectionError,
  ApiResponseError,
} from '../services/agroscanApi'

import type {
  AdminUser,
  AdminRole,
} from '../services/agroscanApi'

import { Icon } from '../components/layout/Icon'

import './UsersPage.css'

const roleLabels: Record<AdminRole, string> = {
  administrador: 'Administrador',
  operador: 'Operador',
  revisor: 'Revisor',
}

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [search, setSearch] = useState('')

  // Formulario de registro
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<AdminRole>('operador')

  const currentRole = getSessionRole()

  // ==========================================
  // CONSULTAR USUARIOS
  // ==========================================

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await listAdminUsers()
      setUsers(data)
    } catch (err: unknown) {
      if (err instanceof ApiConnectionError) {
        setError('No se pudo conectar con FastAPI. Comprueba que el backend esté activo.')
      } else if (err instanceof ApiResponseError) {
        setError(err.message)
      } else {
        setError('No se pudieron consultar los usuarios registrados.')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadUsers()
  }, [loadUsers])

  // ==========================================
  // INDICADORES
  // ==========================================

  const activeCount = users.filter(
    user => user.isActive
  ).length

  const inactiveCount = users.length - activeCount

  const administratorCount = users.filter(
    user => user.roles.includes('administrador')
  ).length

  const operatorCount = users.filter(
    user => user.roles.includes('operador')
  ).length

  const reviewerCount = users.filter(
    user => user.roles.includes('revisor')
  ).length

  // ==========================================
  // BUSCADOR
  // ==========================================

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return users

    return users.filter(user =>
      user.username.toLowerCase().includes(query) ||
      user.fullName.toLowerCase().includes(query) ||
      user.roles.some(item =>
        item.toLowerCase().includes(query)
      )
    )
  }, [users, search])

  // ==========================================
  // REGISTRAR USUARIO
  // ==========================================

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (saving) return

    setError('')
    setSuccess('')

    const cleanUsername = username.trim().toLowerCase()
    const cleanFullName = fullName.trim()

    if (cleanUsername.length < 3) {
      setError('El nombre de usuario debe tener al menos 3 caracteres.')
      return
    }

    if (cleanFullName.length < 2) {
      setError('Ingresa el nombre completo del usuario.')
      return
    }

    if (password.length < 12) {
      setError('La contraseña debe tener al menos 12 caracteres.')
      return
    }

    if (users.some(user => user.username.toLowerCase() === cleanUsername)) {
      setError('Ya existe una cuenta con ese nombre de usuario.')
      return
    }

    setSaving(true)

    try {
      const created = await createAdminUser({
        username: cleanUsername,
        fullName: cleanFullName,
        password,
        role,
      })

      setUsers(previous => [...previous, created])

      setUsername('')
      setFullName('')
      setPassword('')
      setRole('operador')

      setSuccess(
        `El usuario ${created.username} fue registrado correctamente.`
      )
    } catch (err: unknown) {
      if (err instanceof ApiResponseError) {
        setError(err.message)
      } else if (err instanceof ApiConnectionError) {
        setError('No se pudo conectar con el servidor.')
      } else {
        setError('No se pudo registrar el usuario.')
      }
    } finally {
      setSaving(false)
    }
  }

  // ==========================================
  // CAMBIAR ROL
  // ==========================================

  async function handleRoleChange(
    user: AdminUser,
    newRole: AdminRole
  ) {
    if (saving || user.roles.includes(newRole)) return

    setError('')
    setSuccess('')

    const confirmed = window.confirm(
      `¿Deseas cambiar el rol de ${user.username} a ${roleLabels[newRole]}?`
    )

    if (!confirmed) return

    setSaving(true)

    try {
      const updated = await updateAdminUserRole(
        user.id,
        newRole
      )

      setUsers(previous =>
        previous.map(item =>
          item.id === updated.id ? updated : item
        )
      )

      setSuccess(
        `El rol de ${updated.username} fue actualizado correctamente.`
      )
    } catch (err: unknown) {
      setError(
        err instanceof ApiResponseError
          ? err.message
          : 'No se pudo actualizar el rol del usuario.'
      )
    } finally {
      setSaving(false)
    }
  }

  // ==========================================
  // ACTIVAR / DESACTIVAR USUARIO
  // ==========================================

  async function handleStatusChange(user: AdminUser) {
    if (saving) return

    const action = user.isActive
      ? 'desactivar'
      : 'activar'

    const confirmed = window.confirm(
      `¿Deseas ${action} la cuenta de ${user.username}?`
    )

    if (!confirmed) return

    setSaving(true)
    setError('')
    setSuccess('')

    try {
      const updated = await updateAdminUserStatus(
        user.id,
        !user.isActive
      )

      setUsers(previous =>
        previous.map(item =>
          item.id === updated.id ? updated : item
        )
      )

      setSuccess(
        `La cuenta de ${updated.username} fue ${
          updated.isActive ? 'activada' : 'desactivada'
        } correctamente.`
      )
    } catch (err: unknown) {
      setError(
        err instanceof ApiResponseError
          ? err.message
          : 'No se pudo actualizar el estado de la cuenta.'
      )
    } finally {
      setSaving(false)
    }
  }

  // ==========================================
  // INTERFAZ
  // ==========================================

  return (
    <div className="page-stack users-page">

      {/* ENCABEZADO */}

      <div className="page-heading">
        <span className="eyebrow">
          Administración / Usuarios
        </span>

        <h1>Gestión de usuarios</h1>

        <p>
          Registra, consulta y administra los accesos
          de los usuarios a la plataforma AgroScan.
        </p>
      </div>

      {/* INDICADORES */}

      <section className="users-summary">

        <article>
          <span className="users-summary__icon green">
            <Icon name="user" size={21} />
          </span>

          <div>
            <strong>{users.length}</strong>
            <span>Usuarios registrados</span>
          </div>
        </article>

        <article>
          <span className="users-summary__icon blue">
            <Icon name="user" size={21} />
          </span>

          <div>
            <strong>{activeCount}</strong>
            <span>Cuentas activas</span>
          </div>
        </article>

        <article>
          <span className="users-summary__icon orange">
            <Icon name="alert" size={21} />
          </span>

          <div>
            <strong>{inactiveCount}</strong>
            <span>Cuentas inactivas</span>
          </div>
        </article>

      </section>

      {/* DISTRIBUCIÓN POR ROLES */}

      <section className="users-summary">

        <article>
          <div>
            <strong>{administratorCount}</strong>
            <span>Administradores</span>
          </div>
        </article>

        <article>
          <div>
            <strong>{operatorCount}</strong>
            <span>Operadores</span>
          </div>
        </article>

        <article>
          <div>
            <strong>{reviewerCount}</strong>
            <span>Revisores</span>
          </div>
        </article>

      </section>

      {/* MENSAJES */}

      {error && (
        <div
          className="users-message users-message--error"
          role="alert"
        >
          <Icon name="alert" size={18} />
          {error}
        </div>
      )}

      {success && (
        <div
          className="users-message users-message--success"
          role="status"
        >
          {success}
        </div>
      )}

      {/* FORMULARIO DE REGISTRO */}

      <section className="panel users-form-panel">

        <div className="panel-heading">

          <span className="round-icon round-icon--green">
            <Icon name="plus" size={20} />
          </span>

          <div>
            <h2>Registrar nuevo usuario</h2>

            <p>
              Completa los datos para crear una nueva cuenta
              en AgroScan.
            </p>
          </div>

        </div>

        <form
          className="users-form"
          onSubmit={handleCreate}
        >

          <div className="users-field">
            <label htmlFor="user-fullname">
              Nombre completo
            </label>

            <input
              id="user-fullname"
              type="text"
              value={fullName}
              onChange={event => setFullName(event.target.value)}
              placeholder="Ingrese nombres y apellidos"
              minLength={2}
              maxLength={120}
              autoComplete="name"
              required
            />
          </div>

          <div className="users-field">
            <label htmlFor="user-username">
              Nombre de usuario
            </label>

            <input
              id="user-username"
              type="text"
              value={username}
              onChange={event => setUsername(event.target.value)}
              placeholder="Ej. operador02"
              minLength={3}
              maxLength={64}
              autoComplete="off"
              required
            />
          </div>

          <div className="users-field">
            <label htmlFor="user-password">
              Contraseña
            </label>

            <input
              id="user-password"
              type="password"
              value={password}
              onChange={event => setPassword(event.target.value)}
              placeholder="Mínimo 12 caracteres"
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />
          </div>

          <div className="users-field">
            <label htmlFor="user-role">
              Rol del usuario
            </label>

            <select
              id="user-role"
              value={role}
              onChange={event =>
                setRole(event.target.value as AdminRole)
              }
            >
              <option value="operador">
                Operador
              </option>

              <option value="revisor">
                Revisor
              </option>

              <option value="administrador">
                Administrador
              </option>
            </select>
          </div>

          <div className="users-form__actions">

            <button
              type="submit"
              className="action-button action-button--primary"
              disabled={saving}
            >
              <Icon name="plus" size={17} />

              {saving
                ? 'Registrando...'
                : 'Registrar usuario'}
            </button>

          </div>

        </form>

      </section>

      {/* LISTADO DE USUARIOS */}

      <section className="panel users-list-panel">

        <div className="users-list-heading">

          <div className="panel-heading">

            <span className="round-icon round-icon--green">
              <Icon name="user" size={20} />
            </span>

            <div>
              <h2>Usuarios registrados</h2>

              <p>
                Cuentas almacenadas en la base de datos AgroScan.
              </p>
            </div>

          </div>

          <button
            type="button"
            className="action-button action-button--secondary"
            onClick={() => void loadUsers()}
            disabled={loading || saving}
          >
            <Icon name="history" size={17} />

            {loading ? 'Consultando...' : 'Actualizar'}
          </button>

        </div>

        {/* BUSCADOR */}

        <div className="users-search">

          <label htmlFor="users-search">
            Buscar usuario
          </label>

          <input
            id="users-search"
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Buscar por nombre, usuario o rol..."
          />

        </div>

        {/* TABLA */}

        {loading ? (

          <p className="users-empty" role="status">
            Consultando usuarios registrados...
          </p>

        ) : filteredUsers.length === 0 ? (

          <p className="users-empty">
            No se encontraron usuarios.
          </p>

        ) : (

          <div className="users-table-wrapper">

            <table className="users-table">

              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Nombre completo</th>
                  <th>Rol</th>
                  <th>Estado</th>
                  <th>Administración</th>
                </tr>
              </thead>

              <tbody>

                {filteredUsers.map(user => {

                  const userRole = (
                    user.roles[0] || 'operador'
                  ) as AdminRole

                  return (

                    <tr key={user.id}>

                      <td>
                        <strong>
                          {user.username}
                        </strong>

                        <small>
                          ID: {user.id}
                        </small>
                      </td>

                      <td>
                        {user.fullName}
                      </td>

                      <td>

                        <select
                          aria-label={`Rol de ${user.username}`}
                          value={userRole}
                          disabled={
                            saving ||
                            currentRole !== 'administrador'
                          }
                          onChange={event =>
                            void handleRoleChange(
                              user,
                              event.target.value as AdminRole
                            )
                          }
                        >

                          {Object.entries(roleLabels).map(
                            ([value, label]) => (

                              <option
                                key={value}
                                value={value}
                              >
                                {label}
                              </option>

                            )
                          )}

                        </select>

                      </td>

                      <td>

                        <span
                          className={`users-status ${
                            user.isActive ? 'active' : 'inactive'
                          }`}
                        >
                          {user.isActive ? 'Activo' : 'Inactivo'}
                        </span>

                      </td>

                      <td>

                        <button
                          type="button"
                          className={`users-status-button ${
                            user.isActive ? 'deactivate' : 'activate'
                          }`}
                          disabled={
                            saving ||
                            currentRole !== 'administrador'
                          }
                          onClick={() =>
                            void handleStatusChange(user)
                          }
                        >
                          {user.isActive
                            ? 'Desactivar'
                            : 'Activar'}
                        </button>

                      </td>

                    </tr>

                  )
                })}

              </tbody>

            </table>

          </div>

        )}

        <p className="users-footnote">
          Los cambios se guardan en el backend. La desactivación
          conserva la cuenta y sus registros históricos.
        </p>

      </section>

    </div>
  )
}
