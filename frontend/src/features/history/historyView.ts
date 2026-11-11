export type HistoryView = 'evaluaciones' | 'piezas'

/** Solo interpreta la pestaña; nunca consulta ni modifica registros. */
export function resolveHistoryView(value: string | null): HistoryView {
  return value === 'piezas' ? 'piezas' : 'evaluaciones'
}

/** Conserva otros parámetros y permite enlaces directos a AG-040. */
export function paramsForHistoryView(current: URLSearchParams, view: HistoryView): URLSearchParams {
  const next = new URLSearchParams(current)
  if (view === 'piezas') next.set('vista', 'piezas')
  else next.delete('vista')
  return next
}
