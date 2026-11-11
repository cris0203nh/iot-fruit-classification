
import type { IconName } from '../components/layout/Icon'

export type NavigationItem = {
  path: string
  label: string
  icon: IconName
}

// Funciones exclusivas del operador
export const operatorNavigation: NavigationItem[] = [
  { path: '/', label: 'Inicio', icon: 'home' },
  { path: '/evaluacion', label: 'Nueva evaluación', icon: 'scan' },
  { path: '/lotes', label: 'Mis lotes', icon: 'boxes' },
  { path: '/historial', label: 'Historial', icon: 'history' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
]

// Funciones exclusivas del revisor
export const reviewerNavigation: NavigationItem[] = [
  { path: '/', label: 'Inicio', icon: 'home' },
  { path: '/historial', label: 'Evaluaciones', icon: 'history' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
]

// Funciones administrativas existentes
export const administratorNavigation: NavigationItem[] = [
  { path: '/', label: 'Inicio', icon: 'home' },
  { path: '/usuarios', label: 'Gestión de usuarios', icon: 'user' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
  { path: '/estadisticas', label: 'Estadísticas', icon: 'chart' },
]
