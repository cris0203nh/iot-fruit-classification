import type { IconName } from '../components/layout/Icon'

export type NavigationItem = {
  path: string
  label: string
  icon: IconName
}

export const primaryNavigation: NavigationItem[] = [
  { path: '/', label: 'Inicio', icon: 'home' },
  { path: '/evaluacion', label: 'Evaluación', icon: 'scan' },
  { path: '/historial', label: 'Historial', icon: 'history' },
  { path: '/trazabilidad', label: 'Trazabilidad', icon: 'network' },
  { path: '/estadisticas', label: 'Estadísticas', icon: 'chart' },
  { path: '/lotes', label: 'Lotes', icon: 'boxes' },
]

export const secondaryNavigation: NavigationItem[] = [
  { path: '/mantenimiento', label: 'Mantenimiento', icon: 'settings' },
]
