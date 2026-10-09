import { Link } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'

type SectionKey = 'evaluacion' | 'trazabilidad' | 'estadisticas' | 'mantenimiento'

const sections: Record<SectionKey, { title: string; description: string; upcoming: string[] }> = {
  evaluacion: {
    title: 'Evaluación',
    description: 'Flujo semiautomatizado de evaluación externa de mango y tomate.',
    upcoming: ['Seleccionar lote y pieza', 'Verificar pesaje y captura RGB', 'Guardar la evaluación antes de retirar la muestra'],
  },
  trazabilidad: {
    title: 'Trazabilidad',
    description: 'Consulta de evidencia, versiones y revisiones vinculadas a cada pieza.',
    upcoming: ['Asociar piezas a lotes', 'Consultar evidencias y resultados', 'Conservar historial de revisiones'],
  },
  estadisticas: {
    title: 'Estadísticas',
    description: 'Resumen operativo basado únicamente en registros reales y verificables.',
    upcoming: ['Establecer filtros y denominadores', 'Diferenciar piezas, intentos e imágenes', 'Mostrar indicadores solo cuando existan datos válidos'],
  },
  mantenimiento: {
    title: 'Mantenimiento',
    description: 'Comprobaciones de dispositivos, calibración y estado de almacenamiento.',
    upcoming: ['Verificar conexión de sensores', 'Consultar calibraciones aplicadas', 'Informar errores con acciones recomendadas'],
  },
}

export function SectionPage({ section }: { section: SectionKey }) {
  const content = sections[section]

  return (
    <div className="page-stack">
      <div className="page-heading">
        <span className="eyebrow">Módulo AgroScan</span>
        <h1>{content.title}</h1>
        <p>{content.description}</p>
      </div>
      <section className="panel placeholder-panel">
        <div className="round-icon round-icon--blue"><Icon name="clipboard" size={23} /></div>
        <span className="placeholder-panel__eyebrow">Pendiente de implementación</span>
        <h2>Vista preparada para la siguiente etapa</h2>
        <p>La navegación está funcionando. Este módulo todavía no cuenta con servicios conectados ni datos operativos.</p>
        <div className="placeholder-panel__list">
          <h3>Funcionalidades previstas</h3>
          <ul>{content.upcoming.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <Link className="text-link" to="/">Volver al inicio <Icon name="arrow-right" size={16} /></Link>
      </section>
    </div>
  )
}

export function NotFoundPage() {
  return (
    <div className="page-stack">
      <div className="page-heading"><h1>Página no encontrada</h1><p>La dirección solicitada no pertenece a una sección de AgroScan.</p></div>
      <Link className="action-button action-button--primary action-button--compact" to="/">Volver al inicio</Link>
    </div>
  )
}
