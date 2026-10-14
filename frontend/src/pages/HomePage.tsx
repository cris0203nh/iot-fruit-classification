import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { getBackendHealth } from '../services/agroscanApi'

const indicators = [
  { label: 'Guardadas', value: 'Sin consultar', icon: 'clipboard' as const, tone: 'green' },
  { label: 'Por revisar', value: 'Sin consultar', icon: 'clock' as const, tone: 'blue' },
  { label: 'Lote activo', value: 'No seleccionado', icon: 'boxes' as const, tone: 'purple' },
  { label: 'Estación', value: 'No verificada', icon: 'settings' as const, tone: 'red' },
]

const devices = [
  { icon: 'camera' as const, text: 'Cámara RGB: sin verificar' },
  { icon: 'scale' as const, text: 'Pesaje ESP32: sin lectura confirmada' },
  { icon: 'settings' as const, text: 'Calibración: sin verificar' },
  { icon: 'database' as const, text: 'Almacenamiento: sin diagnóstico' },
]

export function HomePage() {
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true
    getBackendHealth().then(
      () => { if (active) setApiStatus('online') },
      () => { if (active) setApiStatus('offline') },
    )
    return () => { active = false }
  }, [retry])

  return (
    <div className="page-stack">
      <div className="page-heading">
        <span className="eyebrow">Panel general</span>
        <h1>Inicio: preparar la estación</h1>
        <p>Supervisa el proceso antes de comenzar a evaluar frutas.</p>
      </div>

      <div className="notice notice--warning" role="status">
        <Icon name="alert" size={19} />
        <span><strong>{apiStatus === 'online' ? 'Backend disponible' : apiStatus === 'checking' ? 'Comprobando backend' : 'Backend no disponible'}:</strong> {apiStatus === 'online'
          ? 'La API respondió correctamente. Esto no confirma sensores conectados ni evaluaciones guardadas.'
          : apiStatus === 'checking' ? 'Verificando la API local…' : 'Inicia FastAPI para poder consultar y crear lotes.'}
          {apiStatus === 'offline' && <button type="button" className="action-button action-button--secondary" onClick={() => { setApiStatus('checking'); setRetry((n) => n + 1) }}>Reintentar</button>}</span>
      </div>

      <section className="summary-grid" aria-label="Resumen de estación">
        {indicators.map((indicator) => (
          <div className="summary-card" key={indicator.label}>
            <span className={`round-icon round-icon--${indicator.tone}`}><Icon name={indicator.icon} size={22} /></span>
            <div>
              <h2>{indicator.label}</h2>
              <p>{indicator.value}</p>
            </div>
          </div>
        ))}
      </section>

      <section className="content-grid" aria-label="Información inicial">
        <article className="panel">
          <div className="panel-heading">
            <span className="round-icon round-icon--green"><Icon name="clipboard" size={20} /></span>
            <h2>Última evaluación</h2>
          </div>
          <p className="panel-copy">Esta pantalla todavía no consulta las evaluaciones. El historial podrá mostrar los datos confirmados por el backend cuando se conecte su servicio.</p>
          <div className="empty-evidence"><Icon name="camera" size={20} /> Sin captura vinculada</div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <span className="round-icon round-icon--green"><Icon name="network" size={20} /></span>
            <h2>Disponibilidad de la estación</h2>
          </div>
          <ul className="device-list">
            <li><Icon name="network" size={18}/><span>API local: {apiStatus === 'online' ? 'disponible' : apiStatus === 'checking' ? 'verificando' : 'no disponible'}</span></li>
            {devices.map((device) => (
              <li key={device.text}><Icon name={device.icon} size={18} /><span>{device.text}</span></li>
            ))}
          </ul>
          <p className="microcopy">Estas etiquetas no sustituyen una verificación real de hardware y servicios.</p>
        </article>
      </section>

      <div className="quick-actions" aria-label="Accesos rápidos">
        <Link className="action-button action-button--primary" to="/evaluacion"><Icon name="plus" size={19} /> Nueva evaluación</Link>
        <Link className="action-button action-button--secondary" to="/lotes"><Icon name="boxes" size={18} /> Seleccionar lote</Link>
        <Link className="action-button action-button--secondary" to="/mantenimiento"><Icon name="settings" size={18} /> Diagnosticar estación</Link>
      </div>

      <section className="panel panel--guide">
        <div className="panel-heading">
          <span className="round-icon round-icon--green"><Icon name="info" size={20} /></span>
          <h2>Antes de empezar</h2>
        </div>
        <p>El flujo previsto requiere seleccionar producto y lote, verificar el peso estable, confirmar la cámara y disponer de almacenamiento. Estas comprobaciones se implementarán en las siguientes etapas.</p>
      </section>
    </div>
  )
}
