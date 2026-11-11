
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { getBackendHealth } from '../services/agroscanApi'
import './HomePage.css'

type ApiStatus = 'checking' | 'online' | 'offline'

export function HomePage() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true

    getBackendHealth().then(
      () => {
        if (active) setApiStatus('online')
      },
      () => {
        if (active) setApiStatus('offline')
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

  return (
    <div className="operator-home">

      {/* ENCABEZADO */}
      <section className="operator-welcome">
        <div className="operator-welcome__content">
          <span className="operator-eyebrow">
            AGROSCAN · ÁREA DE OPERACIONES
          </span>

          <h1>Bienvenido a tu estación de trabajo</h1>

          <p>
            Registra, pesa y captura tus productos agrícolas
            desde una sola plataforma.
          </p>

          <span className="operator-date">
            <Icon name="clock" size={15} />
            {today}
          </span>

          <Link
            to="/evaluacion"
            className="operator-primary-button"
          >
            <Icon name="scan" size={19} />
            Iniciar nueva evaluación
            <Icon name="arrow-right" size={18} />
          </Link>
        </div>

        <div className="operator-welcome__visual">
          <div className="fruit-orbit fruit-orbit--one" />
          <div className="fruit-orbit fruit-orbit--two" />

          <div className="fruit-illustration fruit-illustration--mango">
            <span className="fruit-leaf" />
          </div>

          <div className="fruit-illustration fruit-illustration--tomato">
            <span className="tomato-leaf">✦</span>
          </div>

          <span className="fruit-label fruit-label--mango">
            MANGO
          </span>

          <span className="fruit-label fruit-label--tomato">
            TOMATE
          </span>
        </div>
      </section>

      {/* ACCESOS PRINCIPALES */}
      <section className="operator-section">
        <div className="operator-section-heading">
          <div>
            <span className="operator-eyebrow">
              TU ESPACIO DE TRABAJO
            </span>
            <h2>¿Qué deseas realizar?</h2>
          </div>
        </div>

        <div className="operator-actions-grid">

          <Link
            to="/evaluacion"
            className="operator-action-card operator-action-card--featured"
          >
            <div className="operator-action-icon">
              <Icon name="camera" size={25} />
            </div>

            <div>
              <h3>Nueva evaluación</h3>
              <p>
                Registra una fruta, realiza el pesaje
                y captura sus fotografías.
              </p>
            </div>

            <span className="operator-action-link">
              Comenzar <Icon name="arrow-right" size={17} />
            </span>
          </Link>

          <Link
            to="/lotes"
            className="operator-action-card"
          >
            <div className="operator-action-icon operator-action-icon--orange">
              <Icon name="boxes" size={25} />
            </div>

            <div>
              <h3>Mis lotes</h3>
              <p>
                Registra nuevos lotes y selecciona
                los productos que vas a evaluar.
              </p>
            </div>

            <span className="operator-action-link">
              Gestionar lotes <Icon name="arrow-right" size={17} />
            </span>
          </Link>

          <Link
            to="/historial"
            className="operator-action-card"
          >
            <div className="operator-action-icon operator-action-icon--blue">
              <Icon name="history" size={25} />
            </div>
            <div>
              <h3>Historial</h3>
              <p>
                Consulta las evaluaciones y los
                registros realizados.
              </p>
            </div>

            <span className="operator-action-link">
              Ver historial <Icon name="arrow-right" size={17} />
            </span>
          </Link>

        </div>
      </section>

      {/* ESTADO DE CONEXIONES */}
      <section className="operator-section">
        <div className="operator-section-heading">
          <div>
            <span className="operator-eyebrow">
              ESTADO DE CONEXIONES
            </span>
            <h2>Disponibilidad de la estación</h2>
          </div>

          <button
            type="button"
            className="operator-refresh"
            onClick={() => {
              setApiStatus('checking')
              setRetry(value => value + 1)
            }}
            aria-label="Actualizar estado del backend"
          >
            <Icon name="history" size={17} />
            Actualizar
          </button>
        </div>

        <div className="operator-device-grid">

          <article className="operator-device-card">
            <div className="operator-device-icon">
              <Icon name="network" size={21} />
            </div>

            <div className="operator-device-info">
              <strong>Backend AgroScan</strong>
              <span>
                {apiStatus === 'online'
                  ? 'API disponible'
                  : apiStatus === 'checking'
                    ? 'Comprobando conexión'
                    : 'Sin conexión'}
              </span>
            </div>

            <span
              className={`operator-status operator-status--${apiStatus}`}
            >
              {apiStatus === 'online'
                ? 'Disponible'
                : apiStatus === 'checking'
                  ? 'Verificando'
                  : 'Desconectado'}
            </span>
          </article>

          <article className="operator-device-card">
            <div className="operator-device-icon operator-device-icon--blue">
              <Icon name="camera" size={21} />
            </div>

            <div className="operator-device-info">
              <strong>Cámara web RGB</strong>
              <span>Captura de fotografías desde la PC</span>
            </div>

            <span className="operator-status operator-status--unknown">
              Validado
            </span>
          </article>

          <article className="operator-device-card">
            <div className="operator-device-icon operator-device-icon--orange">
              <Icon name="scale" size={21} />
            </div>

            <div className="operator-device-info">
              <strong>Balanza digital ESP32</strong>
              <span>Lectura de peso y calibración</span>
            </div>

            <span className="operator-status operator-status--unknown">
              Validada
            </span>
          </article>

        </div>

        <p className="operator-disclaimer">
          La cámara web RGB y la balanza ESP32 cuentan con validaciones
          funcionales realizadas durante las pruebas reales
        </p>
      </section>

      {/* PRODUCTOS */}
      <section className="operator-products">
        <div>
          <span className="operator-eyebrow">
            PRODUCTOS COMPATIBLES
          </span>
          <h2>Trabajamos con productos agrícolas</h2>
          <p>
            Selecciona el producto correspondiente al crear
            una nueva evaluación.
          </p>
        </div>

        <div className="operator-product-tags">
          <span className="operator-product-tag">
            <span className="product-dot product-dot--mango" />
            Mango
          </span>

          <span className="operator-product-tag">
            <span className="product-dot product-dot--tomato" />
            Tomate
          </span>
        </div>

      </section>

      <footer className="operator-footer">
        AgroScan · Plataforma de evaluación de calidad agrícola
      </footer>

    </div>
  )
}
