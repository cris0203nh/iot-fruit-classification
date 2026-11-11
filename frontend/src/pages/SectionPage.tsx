import { Link } from 'react-router-dom'
import { Icon, type IconName } from '../components/layout/Icon'
import { StatisticsPage } from './StatisticsPage'
import './SectionPage.css'

type SectionKey = 'evaluacion' | 'estadisticas' | 'mantenimiento'

const sections: Record<SectionKey, { title: string; description: string; icon: IconName; upcoming: string[] }> = {
  evaluacion: {
    title: 'Evaluación',
    description: 'Flujo semiautomatizado de evaluación externa de mango y tomate.',
    icon: 'scan',
    upcoming: ['Seleccionar lote y pieza', 'Verificar pesaje y captura RGB', 'Guardar la evaluación antes de retirar la muestra'],
  },
  estadisticas: {
    title: 'Estadísticas',
    description: 'Resumen operativo basado únicamente en registros reales y verificables.',
    icon: 'chart',
    upcoming: ['Establecer filtros y denominadores', 'Diferenciar piezas, intentos e imágenes', 'Mostrar indicadores solo cuando existan datos válidos'],
  },
  mantenimiento: {
    title: 'Mantenimiento',
    description: 'Comprobaciones de dispositivos, calibración y estado de almacenamiento.',
    icon: 'settings',
    upcoming: ['Verificar conexión de sensores', 'Consultar calibraciones aplicadas', 'Informar errores con acciones recomendadas'],
  },
}

export function SectionPage({ section }: { section: SectionKey }) {
  if (section === 'estadisticas') return <StatisticsPage />
  const content = sections[section]

  return (
    <div className="seccion">
      <header className="seccion__head">
        <p className="seccion__kicker">Módulo AgroScan</p>
        <h1 className="seccion__title">{content.title}</h1>
        <p className="seccion__lede">{content.description}</p>
      </header>

      <div className="seccion__estado">
        <span className="seccion__estado-icon" aria-hidden="true"><Icon name={content.icon} size={22} /></span>
        <div className="seccion__estado-body">
          <p className="seccion__estado-kicker">Pendiente de implementación</p>
          <h2>Vista preparada para la siguiente etapa</h2>
          <p>La navegación está funcionando. Este módulo todavía no cuenta con servicios conectados ni datos operativos.</p>
        </div>
      </div>

      <section className="seccion__plan" aria-labelledby="seccion-plan">
        <h2 className="seccion__kicker" id="seccion-plan">Funcionalidades previstas</h2>
        <ol className="seccion__lista">
          {content.upcoming.map((item, index) => (
            <li key={item}>
              <span className="seccion__num" aria-hidden="true">{`0${index + 1}`}</span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      </section>

      <Link to="/" className="seccion__link">Volver al inicio <Icon name="arrow-right" size={15} /></Link>
    </div>
  )
}

export function NotFoundPage() {
  return (
    <div className="seccion">
      <header className="seccion__head">
        <p className="seccion__kicker">Navegación</p>
        <h1 className="seccion__title">Página no encontrada</h1>
        <p className="seccion__lede">La dirección solicitada no pertenece a una sección de AgroScan.</p>
      </header>
      <Link to="/" className="action-button action-button--primary">Volver al inicio</Link>
    </div>
  )
}
