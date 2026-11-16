import type { BoardEstimate, FruitGeometryResult } from '../../services/agroscanApi.ts'
import { recoverApproxA4, type Evidence, type Result } from './approxA4Flow.ts'

export type ApproxDeps = {
  getBoards: (evaluationId: string, imageId: string) => Promise<BoardEstimate[]>
  getGeometries: (evaluationId: string) => Promise<FruitGeometryResult[]>
  analyzeGeometry: (evaluationId: string, imageId: string) => Promise<FruitGeometryResult>
  estimate: (evaluationId: string, imageId: string) => Promise<BoardEstimate>
}

const active = new Map<string, Promise<Result[]>>()

/** Calcula al aparecer dos vistas guardadas. Sin declaraciones físicas inventadas. */
export function runAutoApproxA4(
  evaluationId: string, evidence: readonly Evidence[], authorized: boolean, deps: ApproxDeps,
): Promise<Result[]> {
  const identities = evidence.map(item => `${item.view}:${item.id}`)
  if (evidence.length < 2 || new Set(identities).size !== identities.length ||
      new Set(evidence.map(item => item.id)).size !== evidence.length) {
    return Promise.resolve(evidence.map(item => ({ imageId: item.id, view: item.view,
      status: 'pending' as const })))
  }
  const key = `${evaluationId}:${identities.join('|')}`
  const previous = active.get(key)
  if (previous) return previous

  const task = (async (): Promise<Result[]> => {
    const groups = await Promise.all(evidence.map(item => deps.getBoards(evaluationId, item.id)))
    const recovered = recoverApproxA4(evaluationId, evidence, groups)
    if (!authorized || recovered.every(row => row.status !== 'pending')) return recovered
    const geometries = await deps.getGeometries(evaluationId)
    const next: Result[] = []
    for (const item of recovered) {
      if (item.status !== 'pending') { next.push(item); continue }
      try {
        const geometry = geometries.filter(g => g.evaluationId === evaluationId &&
          g.imageId === item.imageId).at(-1) ??
          await deps.analyzeGeometry(evaluationId, item.imageId)
        if (geometry.evaluationId !== evaluationId || geometry.imageId !== item.imageId ||
            geometry.status !== 'measured') {
          next.push({ ...item, status: 'needs_review', reason: 'Contorno YOLOE no evaluable.' })
          continue
        }
        const row = await deps.estimate(evaluationId, item.imageId)
        const checked = recoverApproxA4(evaluationId, [{ id: item.imageId, view: item.view }], [[row]])[0]
        next.push(checked)
      } catch (failure) {
        next.push({ ...item, status: 'error',
          reason: failure instanceof Error ? failure.message : 'Error al estimar la escala.' })
      }
    }
    return next
  })()
  active.set(key, task)
  void task.then(() => { if (active.get(key) === task) active.delete(key) },
    () => { if (active.get(key) === task) active.delete(key) })
  return task
}
