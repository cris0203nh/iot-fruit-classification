import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { getBackendHealth, getSessionRole } from '../services/agroscanApi'
import './HomePage.css'

const devices = [
  { label: 'Cámara RGB', value: 'sin verificar', tone: 'wait', icon: 'camera' as const },
  { label: 'Pesaje ESP32', value: 'sin lectura confirmada', tone: 'wait', icon: 'scale' as const },
  { label: 'Calibración', value: 'sin verificar', tone: 'wait', icon: 'settings' as const },
  { label: 'Almacenamiento', value: 'sin diagnóstico', tone: 'idle', icon: 'database' as const },
] as const

export function HomePage() {
  const reviewer = getSessionRole() === 'revisor'
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

  const apiTone = apiStatus === 'online' ? 'ok' : apiStatus === 'offline' ? 'off' : 'wait'
  const apiTitle = apiStatus === 'online' ? 'Backend disponible' : apiStatus === 'checking' ? 'Comprobando backend' : 'Backend no disponible'
  const apiText = apiStatus === 'online'
    ? 'La API respondió correctamente. Esto no confirma sensores conectados ni evaluaciones guardadas.'
    : apiStatus === 'checking'
      ? 'Verificando la API local…'
      : 'Inicia FastAPI para poder consultar y registrar lotes y evaluaciones.'
  const apiValue = apiStatus === 'online' ? 'disponible' : apiStatus === 'checking' ? 'verificando' : 'no disponible'

  return (
    <div className="inicio">
      <header className="inicio__head">
        <p className="inicio__eyebrow">Panel general</p>
        <h1 className="inicio__title">{reviewer ? 'Inicio: revisión y consulta' : 'Inicio: preparar la estación'}</h1>
        <p className="inicio__lede">{reviewer ? 'Consulta las evaluaciones y su trazabilidad, sin modificar registros ni capturas.' : 'Supervisa el proceso antes de comenzar a evaluar frutas.'}</p>
      </header>

      <div className="inicio__aviso" data-tone={apiTone}>
        <span className="inicio__aviso-icon" aria-hidden="true"><Icon name="alert" size={17} /></span>
        <div className="inicio__aviso-body" role="status">
          <p className="inicio__aviso-title">{apiTitle}</p>
          <p className="inicio__aviso-text">{apiText}</p>
        </div>
        {apiStatus === 'offline' && (
          <button type="button" className="inicio__aviso-btn" onClick={() => { setApiStatus('checking'); setRetry((n) => n + 1) }}>
            Reintentar
          </button>
        )}
      </div>

      <section className="inicio__siguiente" aria-labelledby="inicio-siguiente">
        <div className="inicio__siguiente-head">
          <div>
            <h2 id="inicio-siguiente">¿Qué necesitas hacer?</h2>
            <p>{reviewer ? 'Accede a las evaluaciones registradas o revisa su trazabilidad.' : 'Empieza con un lote, registra una pieza o consulta las evaluaciones guardadas.'}</p>
          </div>
        </div>
        <nav className="inicio__acciones" aria-label="Accesos rápidos de trabajo">
          {!reviewer && (
            <>
              <Link className="inicio__accion inicio__accion--primaria" to="/evaluacion">
                <span className="inicio__accion-icon" aria-hidden="true"><Icon name="plus" size={17} /></span>
                <span className="inicio__accion-label">Iniciar evaluación</span>
                <span className="inicio__accion-arrow" aria-hidden="true"><Icon name="arrow-right" size={16} /></span>
              </Link>
              <Link className="inicio__accion" to="/lotes">
                <span className="inicio__accion-icon" aria-hidden="true"><Icon name="boxes" size={17} /></span>
                <span className="inicio__accion-label">Gestionar lotes</span>
                <span className="inicio__accion-arrow" aria-hidden="true"><Icon name="arrow-right" size={16} /></span>
              </Link>
            </>
          )}
          <Link className="inicio__accion" to="/historial">
            <span className="inicio__accion-icon" aria-hidden="true"><Icon name="history" size={17} /></span>
            <span className="inicio__accion-label">Consultar historial</span>
            <span className="inicio__accion-arrow" aria-hidden="true"><Icon name="arrow-right" size={16} /></span>
          </Link>
          <Link className="inicio__accion" to="/trazabilidad">
            <span className="inicio__accion-icon" aria-hidden="true"><Icon name="network" size={17} /></span>
            <span className="inicio__accion-label">Consultar trazabilidad</span>
            <span className="inicio__accion-arrow" aria-hidden="true"><Icon name="arrow-right" size={16} /></span>
          </Link>
        </nav>
      </section>

      <div className="inicio__grid">
        <section className="inicio__bloque" aria-labelledby="inicio-ultima">
          <h2 className="inicio__kicker" id="inicio-ultima">Registros y expedientes</h2>
          <p className="inicio__copy">Consulta las evaluaciones confirmadas y los expedientes por lote en Historial. Aquí no se muestran cifras que aún no se hayan consultado.</p>
          <div className="inicio__consultas"><Link to="/historial">Ver evaluaciones registradas <Icon name="arrow-right" size={15} /></Link><Link to="/historial?vista=piezas">Consultar piezas por lote <Icon name="arrow-right" size={15} /></Link></div>
        </section>

        <section className="inicio__bloque" aria-labelledby="inicio-disponibilidad">
          <h2 className="inicio__kicker" id="inicio-disponibilidad">Disponibilidad de la estación</h2>
          <dl className="inicio__estado">
            <div data-tone={apiTone}>
              <dt><span className="inicio__estado-icon" aria-hidden="true"><Icon name="network" size={15} /></span>API local</dt>
              <dd><span className="inicio__dot" aria-hidden="true" />{apiValue}</dd>
            </div>
            {devices.map((device) => (
              <div key={device.label} data-tone={device.tone}>
                <dt><span className="inicio__estado-icon" aria-hidden="true"><Icon name={device.icon} size={15} /></span>{device.label}</dt>
                <dd><span className="inicio__dot" aria-hidden="true" />{device.value}</dd>
              </div>
            ))}
          </dl>
          <p className="inicio__micro">Estas etiquetas no sustituyen una verificación real de hardware y servicios.</p>
        </section>
      </div>

      <section className="inicio__bloque inicio__bloque--nota" aria-labelledby="inicio-antes">
        <h2 className="inicio__kicker" id="inicio-antes">Antes de empezar</h2>
        <div className="inicio__nota">
          <span className="inicio__nota-icon" aria-hidden="true"><Icon name="info" size={18} /></span>
          <p className="inicio__copy">{reviewer ? 'Este perfil es de consulta y revisión. No puede crear lotes, registrar pesajes ni capturar fotografías.' : 'Para registrar una pieza, selecciona producto y lote. El pesaje, la captura y la persistencia solo se consideran confirmados cuando sus respectivos pasos obtienen evidencia del sistema. El estado del hardware no se deduce de la respuesta de la API.'}</p>
        </div>
      </section>
    </div>
  )
}
