import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ProtectedEvidenceImage } from '../capture/ProtectedEvidenceImage'
import { formatDate, formatWeight } from './historyService'
import {
  ApiConnectionError, ApiResponseError, getPieceHistory, listPieceHistories,
  getLotTraceabilityReport, resolveEvidenceUrl, type PieceHistoryList, type PieceHistoryDetail,
} from '../../services/agroscanApi'
import type { LotTraceabilityReport } from './pieceReportPolicy'
import './PieceHistoryPanel.css'

type Load<T> = { state: 'idle' | 'loading' | 'error' | 'ready'; value: T | null; error: string }
const idle = <T,>(): Load<T> => ({ state: 'idle', value: null, error: '' })

function errorMessage(e: unknown): string {
  if (e instanceof ApiConnectionError) return 'FastAPI no responde. Los registros siguen almacenados.'
  if (e instanceof ApiResponseError && (e.status === 401 || e.status === 403)) return 'No tienes permiso para consultar este expediente.'
  if (e instanceof ApiResponseError && e.status === 404) return 'El lote o la pieza no existe en SQLite.'
  return 'No se pudo verificar el historial. Comprueba la conexión y vuelve a consultar.'
}

export function PieceHistoryPanel({ suggestedLots }: { suggestedLots: string[] }) {
  const [draft, setDraft] = useState('')
  const [lot, setLot] = useState('')
  const [piece, setPiece] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [list, setList] = useState<Load<PieceHistoryList>>(() => idle<PieceHistoryList>())
  const [detail, setDetail] = useState<Load<PieceHistoryDetail>>(() => idle<PieceHistoryDetail>())
  const [report, setReport] = useState<LotTraceabilityReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')

  useEffect(() => {
    setReport(null)
    setReportError('')
    if (!lot) { setList(idle<PieceHistoryList>()); return }
    let active = true
    setList({ state: 'loading', value: null, error: '' })
    void listPieceHistories(lot).then(
      value => { if (active) setList({ state: 'ready', value, error: '' }) },
      error => { if (active) setList({ state: 'error', value: null, error: errorMessage(error) }) },
    )
    return () => { active = false }
  }, [lot, refresh])

  useEffect(() => {
    if (!lot || !piece) { setDetail(idle<PieceHistoryDetail>()); return }
    let active = true
    setDetail({ state: 'loading', value: null, error: '' })
    void getPieceHistory(lot, piece).then(
      value => { if (active) setDetail({ state: 'ready', value, error: '' }) },
      error => { if (active) setDetail({ state: 'error', value: null, error: errorMessage(error) }) },
    )
    return () => { active = false }
  }, [lot, piece, refresh])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = draft.trim()
    if (!next || next.length > 32) return
    setPiece('')
    setLot(next)
    setRefresh(current => current + 1)
  }

  async function prepareReport() {
    if (!lot || reportLoading) return
    setReportLoading(true)
    setReport(null)
    setReportError('')
    try {
      const next = await getLotTraceabilityReport(lot)
      setReport(next)
    } catch (error) {
      setReportError(errorMessage(error))
    } finally {
      setReportLoading(false)
    }
  }

  function downloadReport(format: 'csv' | 'json') {
    if (!report || (format === 'csv' && report.integrity.status === 'inconsistent')) return
    const safeName = report.lotCode.replace(/[^a-zA-Z0-9_.-]/g, '_')
    const { csv, ...manifest } = report
    const content = format === 'csv' ? csv : JSON.stringify(manifest, null, 2) + '\n'
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AG040_${safeName}_trazabilidad.${format}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  return (
    <section className="panel ag040" aria-labelledby="ag040-heading">
      <div className="panel-heading">
        <h2 id="ag040-heading">AG-040 · Historial integral por pieza y lote</h2>
        <p>Una pieza por lote, con todos sus intentos, capturas y revisiones. Los conteos se consultan desde FastAPI.</p>
      </div>
      <form onSubmit={submit} className="ag040__form">
        <label htmlFor="ag040-lot">Código del lote</label>
        <input id="ag040-lot" list="ag040-suggested-lots" value={draft} maxLength={32}
          onChange={event => setDraft(event.target.value)} placeholder="Ej.: LOTE-MANGO-001" required />
        <datalist id="ag040-suggested-lots">
          {suggestedLots.map(value => <option value={value} key={value} />)}
        </datalist>
        <button type="submit" className="action-button action-button--primary">Consultar piezas</button>
        {lot && <button className="action-button action-button--secondary" type="button"
          onClick={() => setRefresh(current => current + 1)}>Actualizar desde SQLite</button>}
      </form>
      {list.state === 'loading' && <p role="status">Consultando piezas del lote…</p>}
      {list.state === 'error' && <p role="alert" className="ag040__error">{list.error}</p>}
      {list.state === 'ready' && list.value && <>
        <div className="ag040__report">
          <button type="button" className="action-button action-button--secondary"
            disabled={reportLoading} onClick={() => void prepareReport()}>
            {reportLoading ? 'Auditando lote…' : 'Preparar reporte de lote'}
          </button>
          {reportError && <p role="alert" className="ag040__error">{reportError}</p>}
          {report && <>
            <p role="status">Auditoría: <strong>{report.integrity.status}</strong> ·
              {report.counts.pieceCount} piezas · {report.counts.attemptCount} intentos ·
              {report.counts.captureCount} fotos · {report.integrity.issues.length} observaciones</p>
            <p>SHA256 CSV: <code>{report.csvSha256}</code></p>
            <div className="ag040__report-actions">
              <button type="button" className="action-button action-button--primary"
                disabled={report.integrity.status === 'inconsistent'} onClick={() => downloadReport('csv')}>Exportar CSV</button>
              <button type="button" className="action-button action-button--secondary"
                onClick={() => downloadReport('json')}>Exportar manifiesto JSON</button>
            </div>
            {report.integrity.status === 'inconsistent' && <p className="ag040__error">CSV bloqueado: revisa las inconsistencias del manifiesto.</p>}
            {report.integrity.issues.length > 0 && <details><summary>Ver observaciones de integridad</summary>
              <ul>{report.integrity.issues.map((issue, i) => <li key={i}>
                {issue.severity}: {issue.pieceCode || 'Lote'} · {issue.message}
              </li>)}</ul>
            </details>}
          </>}
        </div>
        <p className="ag040__totals"><strong>{list.value.pieceCount} piezas únicas</strong> · {list.value.attemptCount} intentos · {list.value.captureCount} fotografías</p>
        {list.value.pieces.length === 0 && <p>No hay piezas registradas para este lote.</p>}
        <div className="ag040__piece-list">
          {list.value.pieces.map(item => <div key={`${item.lotCode}:${item.pieceCode}`} className="ag040__piece">
            <div><strong>{item.pieceCode}</strong><p>
              {item.attemptCount} intentos · {item.captureCount} fotos · {item.reviewEventCount} eventos de revisión
              {item.identitySource === 'legacy_inferred' && <span className="ag040__warning"> · Identidad histórica inferida</span>}
            </p></div>
            <button type="button" className="action-button action-button--secondary" aria-pressed={piece === item.pieceCode}
              onClick={() => setPiece(value => value === item.pieceCode ? '' : item.pieceCode)}>
              {piece === item.pieceCode ? 'Ocultar expediente' : 'Ver expediente'}
            </button>
          </div>)}
        </div>
      </>}
      {detail.state === 'loading' && <p role="status">Recuperando intentos y evidencias…</p>}
      {detail.state === 'error' && <p role="alert" className="ag040__error">{detail.error}</p>}
      {detail.state === 'ready' && detail.value && <div className="ag040__detail">
        <h3>Expediente: {detail.value.piece.pieceCode} · {detail.value.lotCode}</h3>
        {detail.value.identityWarning && <p className="ag040__warning">{detail.value.identityWarning}</p>}
        {detail.value.attempts.length === 0 && <p>Pieza registrada sin intentos de evaluación.</p>}
        {detail.value.attempts.map(attempt => <details key={attempt.id} className="ag040__attempt">
          <summary>Intento {attempt.attemptNumber} · {attempt.id} · {attempt.status} · {formatDate(attempt.createdAt)}</summary>
          <div className="ag040__attempt-body">
            <p>Peso: {formatWeight(attempt.weightGrams)} · Calibración: {attempt.calibrationReference ?? 'No disponible'}</p>
            <p>Modelo declarado: {attempt.declaredModelVersion ?? 'No disponible'} · Reglas declaradas: {attempt.declaredRulesVersion ?? 'No disponible'}</p>
            {attempt.failureReason && <p className="ag040__warning">Incidencia: {attempt.failureReason}</p>}
            <h4>Fotografías ({attempt.captures.length})</h4>
            {attempt.captures.length === 0 && <p>Sin fotografías persistidas.</p>}
            <div className="ag040__photos">{attempt.captures.map(capture => <div key={capture.id}>
              <strong>{capture.view} · {capture.id}</strong>
              <p>Guardada: {formatDate(capture.createdAt)}</p>
              <p>SHA256: <code>{capture.imageSha256 ?? 'No registrado'}</code></p>
              {capture.hashConflict && <p className="ag040__error">Inconsistencia entre referencias SHA256.</p>}
              {resolveEvidenceUrl(capture.imageUrl)
                ? <ProtectedEvidenceImage className="ag040__photo" path={capture.imageUrl} alt={`${capture.view} de ${attempt.id}`} />
                : <p>Ruta de evidencia no válida.</p>}
            </div>)}</div>
            <h4>Detecciones y versiones ({attempt.automaticAssessments.length})</h4>
            {attempt.automaticAssessments.length === 0 && <p>Sin snapshots del modelo registrados.</p>}
            <ol>{attempt.automaticAssessments.map(record => <li key={record.assessmentId}>
              Foto {record.imageId} · Modelo {record.modelVersion} · Reglas {record.rulesVersion} ·
              Umbral {record.threshold} · Confianza {record.confidence ?? 'No disponible'} · Resultado {record.outcome} ({record.reason})
            </li>)}</ol>
            <h4>Revisiones ({attempt.reviews.length})</h4>
            {attempt.reviews.length === 0 && <p>Sin eventos de revisión.</p>}
            <ol>{attempt.reviews.map(review => <li key={review.id}>
              <strong>{review.id} · {review.action ?? review.type}</strong> — {review.actorId} · {formatDate(review.createdAt)}
              <p>{review.previousValue ?? 'Sin valor'} → {review.updatedValue ?? 'Sin valor'} · {review.reason}</p>
              {review.imageId && <p>Foto inspeccionada: {review.imageId} · SHA256: {review.imageSha256 ?? 'No registrado'}</p>}
            </li>)}</ol>
            {attempt.dataQualityNotes.map((note, i) => <p className="ag040__warning" key={`${attempt.id}-${i}`}>{note}</p>)}
            <Link className="text-link" to={`/trazabilidad/${encodeURIComponent(attempt.id)}`}>Ver trazabilidad de este intento</Link>
          </div>
        </details>)}
      </div>}
      <p className="ag040__footnote">La identidad de pieza depende del código registrado dentro del lote. Las capturas descartadas antes de guardarse no forman parte de la bitácora.</p>
    </section>
  )
}
