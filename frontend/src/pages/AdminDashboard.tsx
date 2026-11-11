import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getBackendHealth,
  listAdminUsers,
  listEvaluations,
  type AdminUser,
} from '../services/agroscanApi'
import type { EvaluationSummary } from '../features/history/historyService'
import { Icon } from '../components/layout/Icon'
import './AdminDashboard.css'

type DashboardData = {
  evaluations: EvaluationSummary[]
  users: AdminUser[]
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: DashboardData }
  | { kind: 'error'; message: string }

type BackendStatus = 'checking' | 'online' | 'offline'

export function AdminDashboard() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [backendStatus, setBackendStatus] =
    useState<BackendStatus>('checking')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true

    Promise.all([
      listEvaluations(),
      listAdminUsers(),
    ]).then(
      ([evaluations, users]) => {
        if (active) {
          setState({
            kind: 'ready',
            data: { evaluations, users },
          })
        }
      },
      (error: unknown) => {
        if (active) {
          setState({
            kind: 'error',
            message: error instanceof Error
              ? error.message
              : 'No se pudieron consultar los datos.',
          })
        }
      },
    )

    return () => {
      active = false
    }
  }, [retry])

  useEffect(() => {
    let active = true

    setBackendStatus('checking')

    getBackendHealth().then(
      () => {
        if (active) setBackendStatus('online')
      },
      () => {
        if (active) setBackendStatus('offline')
      },
    )

    return () => {
      active = false
    }
  }, [retry])

  const today = new Intl.DateTimeFormat('es-PE', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date())

  const evaluations =
    state.kind === 'ready' ? state.data.evaluations : []

  const users =
    state.kind === 'ready' ? state.data.users : []

  const completed = evaluations.filter(
    item => item.status === 'completed',
  ).length

  const pending = evaluations.filter(
    item => item.status === 'pending_review',
  ).length

  const processing = evaluations.filter(
    item => item.status === 'processing',
  ).length

  const errors = evaluations.filter(
    item => item.status === 'error',
  ).length

  const mango = evaluations.filter(
    item => item.product === 'mango',
  ).length

  const tomato = evaluations.filter(
    item => item.product === 'tomate',
  ).length

  const activeUsers = users.filter(user => user.isActive).length

  const operators = users.filter(
    user => user.roles.includes('operador'),
  ).length

  const reviewers = users.filter(
    user => user.roles.includes('revisor'),
  ).length

  const administrators = users.filter(
    user => user.roles.includes('administrador'),
  ).length

  const totalProducts = mango + tomato

  const mangoPercentage = totalProducts
    ? (mango / totalProducts) * 100
    : 0

  const tomatoPercentage = totalProducts
    ? (tomato / totalProducts) * 100
    : 0

  return (
    <div className="admin-dashboard">

      <section className="admin-welcome">
        <div>
          <span className="admin-eyebrow">
            AGROSCAN · ADMINISTRACIÓN GENERAL
          </span>

          <h1>Panel de administración</h1>

          <p>
            Supervisa las operaciones, los usuarios y el
            funcionamiento general de la plataforma AgroScan.
          </p>

          <span className="admin-date">
            <Icon name="clock" size={15} />
            {today}
          </span>
        </div>

        <div className="admin-welcome-icon">
          <Icon name="database" size={65} />
        </div>
      </section>

      <section className="admin-section">

        <div className="admin-section-heading">
          <div>
            <span className="admin-eyebrow">
              INDICADORES GENERALES
            </span>
            <h2>Resumen de AgroScan</h2>
          </div>

          <button
            type="button"
            className="admin-refresh"
            onClick={() => {
              setState({ kind: 'loading' })
              setRetry(value => value + 1)
            }}
          >
            <Icon name="history" size={17} />
            Actualizar
          </button>
        </div>

        {state.kind === 'loading' && (
          <div className="admin-message">
            Consultando información del sistema...
          </div>
        )}

        {state.kind === 'error' && (
          <div className="admin-error" role="alert">
            <Icon name="alert" size={20} />
            <div>
              <strong>No se pudieron cargar los indicadores.</strong>
              <p>{state.message}</p>
            </div>
          </div>
        )}

        {state.kind === 'ready' && (
          <>
            <div className="admin-stat-grid">

              <article className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-icon--green">
                  <Icon name="clipboard" size={23} />
                </div>
                <div>
                  <span>Evaluaciones registradas</span>
                  <strong>{evaluations.length}</strong>
                </div>
              </article>

              <article className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-icon--blue">
                  <Icon name="user" size={23} />
                </div>
                <div>
                  <span>Usuarios registrados</span>
                  <strong>{users.length}</strong>
                </div>
              </article>

              <article className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-icon--purple">
                  <Icon name="history" size={23} />
                </div>
                <div>
                  <span>Evaluaciones completadas</span>
                  <strong>{completed}</strong>
                </div>
              </article>

              <article className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-icon--orange">
                  <Icon name="clock" size={23} />
                </div>
                <div>
                  <span>Pendientes de revisión</span>
                  <strong>{pending}</strong>
                </div>
              </article>

            </div>

            <div className="admin-content-grid">

              <article className="admin-panel">
                <div className="admin-panel-heading">
                  <h2>Estado de evaluaciones</h2>
                  <Icon name="chart" size={21} />
                </div>

                <div className="admin-progress-list">

                  <div>
                    <div className="admin-progress-label">
                      <span>Completadas</span>
                      <strong>{completed}</strong>
                    </div>
                    <div className="admin-progress-track">
                      <span
                        className="admin-progress-fill admin-fill--green"
                        style={{
                          width: `${evaluations.length
                            ? completed / evaluations.length * 100
                            : 0}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="admin-progress-label">
                      <span>En proceso</span>
                      <strong>{processing}</strong>
                    </div>
                    <div className="admin-progress-track">
                      <span
                        className="admin-progress-fill admin-fill--blue"
                        style={{
                          width: `${evaluations.length
                            ? processing / evaluations.length * 100
                            : 0}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="admin-progress-label">
                      <span>Por revisar</span>
                      <strong>{pending}</strong>
                    </div>
                    <div className="admin-progress-track">
                      <span
                        className="admin-progress-fill admin-fill--orange"
                        style={{
                          width: `${evaluations.length
                            ? pending / evaluations.length * 100
                            : 0}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="admin-progress-label">
                      <span>Con error</span>
                      <strong>{errors}</strong>
                    </div>
                    <div className="admin-progress-track">
                      <span
                        className="admin-progress-fill admin-fill--red"
                        style={{
                          width: `${evaluations.length
                            ? errors / evaluations.length * 100
                            : 0}%`,
                        }}
                      />
                    </div>
                  </div>

                </div>
              </article>

              <article className="admin-panel">
                <div className="admin-panel-heading">
                  <h2>Productos evaluados</h2>
                  <Icon name="boxes" size={21} />
                </div>

                <div className="admin-product-summary">

                  <div className="admin-product-row">
                    <span className="admin-product-dot admin-dot--mango" />
                    <span>Mango</span>
                    <strong>{mango}</strong>
                  </div>

                  <div className="admin-product-row">
                    <span className="admin-product-dot admin-dot--tomato" />
                    <span>Tomate</span>
                    <strong>{tomato}</strong>
                  </div>

                  <div className="admin-product-bar">
                    <span
                      className="admin-product-bar__mango"
                      style={{ width: `${mangoPercentage}%` }}
                    />
                    <span
                      className="admin-product-bar__tomato"
                      style={{ width: `${tomatoPercentage}%` }}
                    />
                  </div>

                  <p>
                    Distribución basada en las evaluaciones registradas.
                  </p>
                </div>
              </article>

            </div>

            <article className="admin-panel">
              <div className="admin-panel-heading">
                <h2>Personal del sistema</h2>
                <Icon name="user" size={21} />
              </div>

              <div className="admin-role-grid">
                <div>
                  <strong>{administrators}</strong>
                  <span>Administradores</span>
                </div>
                <div>
                  <strong>{operators}</strong>
                  <span>Operadores</span>
                </div>
                <div>
                  <strong>{reviewers}</strong>
                  <span>Revisores</span>
                </div>
                <div>
                  <strong>{activeUsers}</strong>
                  <span>Cuentas activas</span>
                </div>
              </div>
            </article>
          </>
        )}
      </section>

      <section className="admin-section">
        <div className="admin-section-heading">
          <div>
            <span className="admin-eyebrow">
              CONTROL DE LA PLATAFORMA
            </span>
            <h2>Estado de los componentes</h2>
          </div>
        </div>

        <div className="admin-system-grid">

          <SystemStatus
            title="Backend AgroScan"
            description="Comunicación con la API FastAPI"
            status={backendStatus === 'online'
              ? 'Validado'
              : backendStatus === 'checking'
                ? 'Verificando'
                : 'Desconectado'}
            online={backendStatus === 'online'}
          />

          <SystemStatus
            title="Cámara web RGB"
            description="Captura de imágenes desde la PC"
            status="Validada"
            online
          />

          <SystemStatus
            title="Balanza digital ESP32"
            description="Lectura de peso del producto"
            status="Validada"
            online
          />

          <SystemStatus
            title="Inteligencia artificial"
            description="Clasificación y análisis de imágenes"
            status="En desarrollo"
            online={false}
          />

        </div>

        <p className="admin-disclaimer">
          Los estados de cámara y balanza reflejan las validaciones
          funcionales realizadas. No representan una comprobación
          automática de conexión en tiempo real.
        </p>
      </section>

      <section className="admin-section">
        <div className="admin-section-heading">
          <div>
            <span className="admin-eyebrow">
              ACCESOS ADMINISTRATIVOS
            </span>
            <h2>Gestión del sistema</h2>
          </div>
        </div>

        <div className="admin-access-grid">

          <AdminAccess
            icon="user"
            title="Gestión de usuarios"
            description="Registrar usuarios, asignar roles y administrar cuentas."
            path="/usuarios"
          />

          <AdminAccess
            icon="network"
            title="Trazabilidad"
            description="Consultar el historial de cambios y revisiones."
            path="/trazabilidad"
          />

          <AdminAccess
            icon="chart"
            title="Estadísticas"
            description="Consultar los indicadores y resultados del sistema."
            path="/estadisticas"
          />

        </div>
      </section>

      <footer className="admin-footer">
        AgroScan · Panel de administración general
      </footer>

    </div>
  )
}

function SystemStatus({
  title,
  description,
  status,
  online,
}: {
  title: string
  description: string
  status: string
  online: boolean
}) {
  return (
    <article className="admin-system-card">
      <div className="admin-system-indicator">
        <span className={online
          ? 'admin-indicator admin-indicator--online'
          : 'admin-indicator admin-indicator--offline'}
        />
      </div>

      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>

      <small className={online
        ? 'admin-system-status admin-system-status--online'
        : 'admin-system-status admin-system-status--offline'}
      >
        {status}
      </small>
    </article>
  )
}

function AdminAccess({
  icon,
  title,
  description,
  path,
}: {
  icon: 'user' | 'network' | 'chart' | 'settings'
  title: string
  description: string
  path: string
}) {
  return (
    <Link to={path} className="admin-access-card">
      <div className="admin-access-icon">
        <Icon name={icon} size={23} />
      </div>

      <h3>{title}</h3>
      <p>{description}</p>

      <span>
        Acceder <Icon name="arrow-right" size={16} />
      </span>
    </Link>
  )
}