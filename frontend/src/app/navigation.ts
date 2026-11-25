
import type { IconName } from '../components/layout/Icon'

export type NavigationItem = {
  path: string
  label: string
  icon: IconName
}

export const ownerNavigation: NavigationItem[] = [
  { path: '/plataforma/solicitudes', label: 'Solicitudes comerciales', icon: 'clipboard' },
  { path: '/plataforma/notificaciones', label: 'Notificaciones', icon: 'info' },
  { path: '/plataforma/empresas', label: 'Empresas', icon: 'boxes' },
  { path: '/plataforma/administradores', label: 'Administradores', icon: 'user' },
  { path: '/plataforma/planes', label: 'Planes y contrataciones DEMO', icon: 'chart' },
]

// Funciones exclusivas del operador
export const operatorNavigation: NavigationItem[] = [
  { path: '/app', label: 'Inicio', icon: 'home' },
  { path: '/evaluacion', label: 'Nueva evaluación', icon: 'scan' },
  { path: '/lotes', label: 'Mis lotes', icon: 'boxes' },
  { path: '/historial', label: 'Historial', icon: 'history' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
]

// Funciones exclusivas del revisor
export const reviewerNavigation: NavigationItem[] = [
  { path: '/app', label: 'Inicio', icon: 'home' },
  { path: '/revisiones', label: 'Revisiones pendientes', icon: 'clipboard' },
  { path: '/historial', label: 'Evaluaciones', icon: 'history' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
]

// Funciones administrativas existentes
export const administratorNavigation: NavigationItem[] = [
  { path: '/app', label: 'Inicio', icon: 'home' },
  { path: '/revisiones', label: 'Revisiones pendientes', icon: 'clipboard' },
  { path: '/usuarios', label: 'Gestión de usuarios', icon: 'user' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
  { path: '/estadisticas', label: 'Estadísticas', icon: 'chart' },
  { path: '/suscripcion', label: 'Plan y suscripción', icon: 'chart' },
]
