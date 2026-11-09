/** AG-040 / AGROP-48: comprobación cruzada del manifiesto exportable. */
export type LotReportRow = {
  lotCode: string
  pieceCode: string
  identitySource: 'registered' | 'legacy_inferred'
  attemptCount: number
  captureCount: number
  automaticAssessmentCount: number
  reviewEventCount: number
  attemptIds: string[]
  captureIds: string[]
  assessmentIds: string[]
  reviewIds: string[]
  modelVersions: string[]
  rulesVersions: string[]
  qualityNotes: string[]
}

export type LotTraceabilityReport = {
  reportVersion: 'AG040-02-v1'
  generatedAt: string
  lotCode: string
  product: 'mango' | 'tomate'
  counts: { pieceCount: number; attemptCount: number; captureCount: number
    automaticAssessmentCount: number; reviewEventCount: number }
  integrity: { status: 'ok' | 'warning' | 'inconsistent'
    issues: { severity: 'error' | 'warning'; code: string; pieceCode: string; message: string }[] }
  rows: LotReportRow[]
  csv: string
  csvSha256: string
  csvEncoding: 'UTF-8'
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
const count = (n: unknown): n is number => Number.isSafeInteger(n) && typeof n === 'number' && n >= 0
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(x => typeof x === 'string')

export function validateLotTraceabilityReport(value: unknown, lot: string): value is LotTraceabilityReport {
  if (!record(value) || !record(value.counts) || !record(value.integrity) || !Array.isArray(value.rows)
      || value.lotCode !== lot || value.reportVersion !== 'AG040-02-v1'
      || !['mango', 'tomate'].includes(String(value.product))
      || value.csvEncoding !== 'UTF-8' || typeof value.csv !== 'string'
      || !/^\w{64}$/.test(String(value.csvSha256))
      || typeof value.generatedAt !== 'string' || !Number.isFinite(Date.parse(value.generatedAt))) return false
  const totals = value.counts
  if (!['pieceCount', 'attemptCount', 'captureCount', 'automaticAssessmentCount', 'reviewEventCount'].every(k => count(totals[k]))) return false
  if (!['ok', 'warning', 'inconsistent'].includes(String(value.integrity.status))
      || !Array.isArray(value.integrity.issues)
      || !value.integrity.issues.every((issue: unknown) => record(issue)
        && ['error', 'warning'].includes(String(issue.severity))
        && typeof issue.code === 'string' && typeof issue.pieceCode === 'string'
        && typeof issue.message === 'string')) return false
  if (value.integrity.status === 'ok' && value.integrity.issues.length) return false
  if (value.integrity.status === 'warning' && (value.integrity.issues.length === 0 || value.integrity.issues.some((x: {severity: string}) => x.severity === 'error'))) return false
  if (value.integrity.status === 'inconsistent' && !value.integrity.issues.some((x: {severity: string}) => x.severity === 'error')) return false

  const keys = new Set<string>()
  const ids = { attemptIds: new Set<string>(), captureIds: new Set<string>(), assessmentIds: new Set<string>(), reviewIds: new Set<string>() }
  const sums = { attemptCount: 0, captureCount: 0, automaticAssessmentCount: 0, reviewEventCount: 0 }
  const pairs: Array<[keyof typeof ids, keyof typeof sums]> = [
    ['attemptIds', 'attemptCount'], ['captureIds', 'captureCount'],
    ['assessmentIds', 'automaticAssessmentCount'], ['reviewIds', 'reviewEventCount'],
  ]
  for (const raw of value.rows) {
    if (!record(raw) || raw.lotCode !== lot || typeof raw.pieceCode !== 'string' || !raw.pieceCode
        || !['registered', 'legacy_inferred'].includes(String(raw.identitySource))
        || !texts(raw.modelVersions) || !texts(raw.rulesVersions) || !texts(raw.qualityNotes)) return false
    if (keys.has(raw.pieceCode)) return false
    keys.add(raw.pieceCode)
    for (const [idKey, totalKey] of pairs) {
      if (!count(raw[totalKey]) || !texts(raw[idKey]) || raw[idKey].length !== raw[totalKey]) return false
      sums[totalKey] += raw[totalKey]
      for (const id of raw[idKey] as string[]) {
        if (ids[idKey].has(id)) return false
        ids[idKey].add(id)
      }
    }
  }
  return keys.size === totals.pieceCount && pairs.every(([, key]) => sums[key] === totals[key])
}
