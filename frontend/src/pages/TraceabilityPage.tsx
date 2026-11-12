import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { ReviewDecisionPanel } from '../features/traceability/ReviewDecisionPanel'
import { formatDate, formatWeight } from '../features/history/historyService'
import {
  buildTraceabilityTimeline,
  traceabilityService,
  validateEvaluationId,
  type TraceabilityRecord,
} from '../features/traceability/traceabilityService'
import { ApiConnectionError, ApiResponseError, getSessionRole, markUncertainEvaluationImage, getVisionAssessments, resolveUncertainEvaluation, resolveEvidenceUrl, type VisionAssessment } from '../services/agroscanApi'
import { GeometryOrOriginal } from '../features/geometry/GeometryEvidence'
import { listFruitGeometries, type FruitGeometryResult } from '../services/agroscanApi'
import './TraceabilityPage.css'

type TraceabilityState =
  | { kind: 'loading' }
  | { kind: 'unavailable' }
  | { kind: 'restricted' }
  | { kind: 'error' }
  | { kind: 'not-found' }
  | { kind: 'ready'; record: TraceabilityRecord }

export function TraceabilityPage() {
  const [reference, setReference] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const navigate = useNavigate()
  const validId = validateEvaluationId(reference)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    if (validId) navigate(`/trazabilidad/${encodeURIComponent(validId)}`)
  }

  return (
    <div className="rastreo">
      <header className="rastreo__head">
        <p className="rastreo__kicker">Módulo de trazabilidad</p>
        <h1 className="rastreo__title">Trazabilidad de evaluaciones</h1>
        <p className="rastreo__lede">Consulta las evidencias y revisiones vinculadas a una pieza. El registro original debe conservarse sin modificaciones.</p>
      </header>

      <div className="rastreo__aviso" role="status">
        <span className="rastreo__aviso-icon" aria-hidden="true"><Icon name="info" size={17} /></span>
        <p><strong>Consulta conectada:</strong> la información se solicita a FastAPI. Los registros originales son de solo lectura; las acciones de revisión humana disponibles dependen del rol autenticado y requieren confirmación del servidor.</p>
      </div>

      <section className="trace-search" aria-labelledby="trace-search-heading">
        <div className="rastreo__panel-head">
          <span className="rastreo__panel-icon" aria-hidden="true"><Icon name="network" size={18} /></span>
          <div>
            <h2 id="trace-search-heading">Consultar una evaluación</h2>
            <p>Usa la referencia emitida al registrar la evaluación (por ejemplo, E-000001). También puedes abrir este expediente directamente desde Historial.</p>
          </div>
        </div>
        <p className="trace-search__shortcut">¿No sabes el identificador? <Link to="/historial">Encuéntralo en Historial <Icon name="arrow-right" size={15} /></Link></p>
        <form onSubmit={handleSubmit} noValidate className="trace-form">
          <div className="trace-field">
            <label htmlFor="trace-evaluation-id">Identificador de evaluación *</label>
            <div className="trace-field__control">
              <span className="trace-field__icon" aria-hidden="true"><Icon name="search" size={16} /></span>
              <input
                id="trace-evaluation-id"
                value={reference}
                onChange={(event) => { setReference(event.target.value); setSubmitted(false) }}
                maxLength={11}
                aria-invalid={submitted && !validId}
                aria-describedby={submitted && !validId ? 'trace-evaluation-error' : 'trace-evaluation-help'}
                placeholder="Ej.: E-000001"
                autoComplete="off"
              />
            </div>
            {submitted && !validId
              ? <p className="trace-error" role="alert" id="trace-evaluation-error">Utiliza el formato emitido por FastAPI: E- seguido de 1 a 9 dígitos (ej.: E-000001).</p>
              : <p id="trace-evaluation-help">Referencia de evaluación, no número de lote ni de pieza.</p>}
          </div>
          <button type="submit" className="action-button action-button--primary">Consultar referencia <Icon name="arrow-right" size={15} /></button>
        </form>
      </section>

      <section className="trace-guide" aria-label="Cómo se lee un expediente">
        <div className="trace-guide__step">
          <span className="trace-guide__icon" aria-hidden="true"><Icon name="search" size={16} /></span>
          <strong>1 · Buscar</strong>
          <p>El identificador lo emite el backend, por ejemplo E-000001.</p>
        </div>
        <div className="trace-guide__step">
          <span className="trace-guide__icon" aria-hidden="true"><Icon name="camera" size={16} /></span>
          <strong>2 · Revisar evidencia</strong>
          <p>Vistas RGB guardadas, con su referencia y sin reemplazar el original.</p>
        </div>
        <div className="trace-guide__step">
          <span className="trace-guide__icon" aria-hidden="true"><Icon name="history" size={16} /></span>
          <strong>3 · Leer la bitácora</strong>
          <p>Registro original y revisiones con responsable, motivo y fecha.</p>
        </div>
      </section>

      <section className="trace-overview" aria-label="Información sobre la trazabilidad">
        <article className="trace-overview__card">
          <div className="rastreo__panel-head">
            <span className="rastreo__panel-icon" aria-hidden="true"><Icon name="database" size={18} /></span>
            <h2>Evidencia vinculada</h2>
          </div>
          <p>La consulta mostrará pieza, lote, producto, peso, vistas RGB, calibración y versiones de reglas o modelo, solo cuando estos datos estén confirmados.</p>
        </article>
        <article className="trace-overview__card">
          <div className="rastreo__panel-head">
            <span className="rastreo__panel-icon" aria-hidden="true"><Icon name="history" size={18} /></span>
            <h2>Revisiones auditables</h2>
          </div>
          <p>La bitácora conserva responsable, fecha, motivo y valores asociados. Los revisores autorizados pueden registrar decisiones explícitas cuando el servicio permita esa operación.</p>
        </article>
      </section>
    </div>
  )
}

export function TraceabilityDetailPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()
  const validId = validateEvaluationId(evaluationId ?? '')
  if (!validId) {
    return (
      <div className="rastreo">
        <header className="rastreo__head">
          <h1 className="rastreo__title">Referencia no válida</h1>
          <p className="rastreo__lede">La dirección no contiene un identificador de evaluación admitido.</p>
        </header>
        <Link className="rastreo__link" to="/trazabilidad"><span aria-hidden="true">←</span> Volver a trazabilidad</Link>
      </div>
    )
  }
  return <TraceabilityDetailContent key={validId} evaluationId={validId} />
}

function TraceabilityDetailContent({ evaluationId }: { evaluationId: string }) {
  const [state, setState] = useState<TraceabilityState>({ kind: 'loading' })
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    traceabilityService.getByEvaluationId(evaluationId).then(
      (record) => { if (active) setState(record ? { kind: 'ready', record } : { kind: 'not-found' }) },
      (error: unknown) => { if (active) setState({ kind: error instanceof ApiConnectionError ? 'unavailable' : error instanceof ApiResponseError && (error.status === 401 || error.status === 403) ? 'restricted' : 'error' }) },
    )
    return () => { active = false }
  }, [evaluationId, revision])

  function retry() {
    setState({ kind: 'loading' })
    setRevision((current) => current + 1)
  }

  return (
    <div className="rastreo">
      <header className="rastreo__head">
        <p className="rastreo__kicker">Trazabilidad / Detalle</p>
        <h1 className="rastreo__title">Registro trazable</h1>
        <p className="rastreo__lede">El registro original se conserva. Las revisiones humanas solo se ejecutan con permisos y confirmación del servicio.</p>
      </header>
      <div className="rastreo__detail-nav">
        <Link className="rastreo__link rastreo__link--back" to="/trazabilidad"><span aria-hidden="true">←</span> Otra consulta</Link>
        <Link className="rastreo__link" to={`/historial/${encodeURIComponent(evaluationId)}`}>Ver detalle en Historial <Icon name="arrow-right" size={15} /></Link>
      </div>
      <section className="trace-detail" aria-label="Detalle de trazabilidad">
        <div className="rastreo__panel-head">
          <span className="rastreo__panel-icon" aria-hidden="true"><Icon name="clipboard" size={18} /></span>
          <div>
            <h2>Evaluación solicitada</h2>
            <p className="trace-identifier">{evaluationId}</p>
          </div>
        </div>
        {state.kind === 'loading' && <p role="status">Consultando evidencia y revisiones…</p>}
        {state.kind === 'unavailable' && (
          <div className="trace-message" role="status">
            <span className="trace-message__icon" aria-hidden="true"><Icon name="database" size={20} /></span>
            <h3>Backend desconectado</h3>
            <p>FastAPI no responde. No podemos verificar si esta evaluación existe; sus registros no se han modificado.</p>
            <button type="button" className="action-button action-button--secondary" onClick={retry}>Reintentar</button>
          </div>
        )}
        {state.kind === 'restricted' && (
          <div className="trace-message trace-message--error" role="alert">
            <span className="trace-message__icon" aria-hidden="true"><Icon name="alert" size={20} /></span>
            <h3>Acceso denegado</h3>
            <p>FastAPI rechazó la consulta (401/403). No hay datos que mostrar.</p>
          </div>
        )}
        {state.kind === 'not-found' && (
          <div className="trace-message" role="status">
            <span className="trace-message__icon" aria-hidden="true"><Icon name="info" size={20} /></span>
            <h3>Evaluación no encontrada</h3>
            <p>El servicio respondió correctamente, pero no existe un registro asociado a la referencia solicitada.</p>
          </div>
        )}
        {state.kind === 'error' && (
          <div className="trace-message trace-message--error" role="alert">
            <span className="trace-message__icon" aria-hidden="true"><Icon name="alert" size={20} /></span>
            <h3>Error al consultar la trazabilidad</h3>
            <p>No se pudo recuperar la información. Ninguna evidencia ha sido actualizada.</p>
            <button type="button" className="action-button action-button--secondary" onClick={retry}>Reintentar</button>
          </div>
        )}
        {state.kind === 'ready' && <TraceabilityRecordContent record={state.record} onUpdated={retry} />}
      </section>
    </div>
  )
}

function TraceabilityRecordContent({ record, onUpdated }: { record: TraceabilityRecord; onUpdated: () => void }) {
  const timeline = buildTraceabilityTimeline(record)
  const { evaluation } = record
  const [imageId, setImageId] = useState(record.evaluation.evidence[0]?.id ?? '')
  const [note, setNote] = useState('')
  const [decision, setDecision] = useState<'E0'|'E1'|'E2'|'no_evaluable'>('no_evaluable')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [assessments, setAssessments] = useState<VisionAssessment[]>([])
  const [geometries, setGeometries] = useState<FruitGeometryResult[]>([])
  useEffect(() => {
    let active = true
    void listFruitGeometries(evaluation.id).then(rows => { if (active) setGeometries(rows) }).catch(() => {})
    return () => { active = false }
  }, [evaluation.id])
  const role = getSessionRole()
  const isReviewer = role === 'revisor' || role === 'administrador'
  useEffect(() => {
    let active = true
    void getVisionAssessments(evaluation.id).then(data => { if (active) setAssessments(data) }).catch(() => {})
    return () => { active = false }
  }, [evaluation.id, record.reviews.length])
  async function flagUncertain() {
    if (!isReviewer || !imageId || note.trim().length < 10 || busy) return
    setBusy(true); setActionError(null)
    try {
      await markUncertainEvaluationImage(evaluation.id, imageId, note)
      onUpdated()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo registrar la duda.')
    } finally { setBusy(false) }
  }
  async function resolveUncertain() {
    if (!isReviewer || evaluation.status !== 'pending_review' || note.trim().length < 10 || busy) return
    setBusy(true); setActionError(null)
    try {
      await resolveUncertainEvaluation(evaluation.id, decision, note)
      onUpdated()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo guardar la resolución.')
    } finally { setBusy(false) }
  }
  return (
    <div className="trace-record">
      <dl className="trace-data-grid">
        <div><dt>Estado de la evaluación</dt><dd>{evaluation.status === 'processing' ? 'En proceso' : evaluation.status === 'completed' ? 'Completada' : evaluation.status === 'pending_review' ? 'Por revisar' : evaluation.status === 'cancelled' ? 'Anulada' : 'Error'}</dd></div>
        {evaluation.failureReason && <div><dt>Motivo del error</dt><dd>{evaluation.failureReason}</dd></div>}
        <div className="trace-data-grid__primary"><dt>Lote</dt><dd>{evaluation.lotId}</dd></div>
        <div className="trace-data-grid__primary"><dt>Pieza</dt><dd>{evaluation.pieceId}</dd></div>
        <div className="trace-data-grid__primary"><dt>Producto</dt><dd>{evaluation.product === 'mango' ? 'Mango' : 'Tomate'}</dd></div>
        <div><dt>Peso registrado</dt><dd>{formatWeight(evaluation.weightGrams)}</dd></div>
        <div><dt>Fecha de registro</dt><dd>{formatDate(evaluation.registeredAt)}</dd></div>
        <div><dt>Calibración</dt><dd>{record.calibrationReference ?? 'No disponible'}</dd></div>
        <div><dt>Versión del modelo</dt><dd>{record.modelVersion ?? 'No disponible'}</dd></div>
        <div><dt>Versión de reglas</dt><dd>{record.rulesVersion ?? 'No disponible'}</dd></div>
      </dl>
      <section className="trace-record__section" aria-label="Evidencias visuales">
        <h3 className="rastreo__section-title"><Icon name="camera" size={17} /> Evidencias visuales ({evaluation.evidence.length})</h3>
        {evaluation.evidence.length === 0
          ? <p>No se registraron imágenes asociadas.</p>
          : <ul className="trace-evidence-list">{evaluation.evidence.map((item) => <li key={item.id}><div><strong>{item.view}</strong><span>Referencia: {item.id}</span>{resolveEvidenceUrl(item.imageUrl) ? <GeometryOrOriginal className="trace-evidence__image" path={item.imageUrl} alt={`Evidencia ${item.view} de ${evaluation.id}`} result={geometries.filter(row => row.imageId === item.id).at(-1)} /> : <span>Ruta de imagen no reconocida.</span>}</div></li>)}</ul>}
        <p>Las imágenes se consultan mediante la API autenticada. Nunca se reemplaza el archivo original.</p>
        {assessments.length > 0 && (
          <div role="region" aria-label="Evaluaciones automáticas originales" className="trace-assessments">
            <h4>Resultados de detección originales</h4>
            <ul>{assessments.map(result => <li key={result.id}>
              {result.imageId}: {result.reason} · confianza {result.confidence ?? 'sin detección'}
              · umbral {result.threshold} · modelo {result.modelVersion}
            </li>)}</ul>
            <p>Estas predicciones son de detección; NO califican E0/E1/E2.</p>
          </div>
        )}
        {isReviewer && evaluation.evidence.length > 0 && evaluation.status !== 'cancelled' && evaluation.status !== 'error' && (
          <div className="trace-review-uncertainty">
            <h4><Icon name="alert" size={16} /> AG-037 · Revisión de incertidumbre</h4>
            {evaluation.status !== 'pending_review' && <>
              <label htmlFor="ag037-image">Fotografía observada</label>
              <div className="trace-select">
                <select id="ag037-image" value={imageId} onChange={event => setImageId(event.target.value)} disabled={busy}>
                  {evaluation.evidence.map(img => <option key={img.id} value={img.id}>{img.view} — {img.id}</option>)}
                </select>
                <span className="trace-select__caret" aria-hidden="true">▾</span>
              </div>
            </>}
            {evaluation.status === 'pending_review' && <>
              <p>Resultado pendiente. Revisa las fotos y la rúbrica antes de resolver.</p>
              <label htmlFor="ag037-decision">Decisión humana</label>
              <div className="trace-select">
                <select id="ag037-decision" value={decision} onChange={event => setDecision(event.target.value as typeof decision)} disabled={busy}>
                  <option value="no_evaluable">No evaluable (sin categoría)</option>
                  <option value="E0">E0 — sin defecto externo relevante</option>
                  <option value="E1">E1 — requiere valoración</option>
                  <option value="E2">E2 — revisión prioritaria</option>
                </select>
                <span className="trace-select__caret" aria-hidden="true">▾</span>
              </div>
            </>}
            <label htmlFor="ag037-note">Justificación</label>
            <textarea id="ag037-note" rows={3} value={note} maxLength={evaluation.status === 'pending_review' ? 500 : 300}
              onChange={event => setNote(event.target.value)} disabled={busy}
              placeholder="Describe los defectos o el motivo por el que no puede evaluarse" />
            {evaluation.status === 'pending_review' ? (
              <button type="button" className="action-button action-button--primary"
                disabled={busy || note.trim().length < 10} onClick={() => void resolveUncertain()}>
                {busy ? 'Guardando...' : 'Registrar resolución humana'}
              </button>
            ) : (
              <button type="button" className="action-button action-button--secondary"
                disabled={busy || note.trim().length < 10} onClick={() => void flagUncertain()}>
                {busy ? 'Guardando...' : 'Marcar como pendiente'}
              </button>
            )}
            {actionError && <p role="alert" className="trace-error">{actionError}</p>}
          </div>
        )}
      </section>
      <section className="trace-record__section" aria-labelledby="trace-timeline-title">
        <h3 id="trace-timeline-title" className="rastreo__section-title"><Icon name="history" size={17} /> Historial de versiones y revisiones</h3>
        <ol className="trace-timeline">{timeline.map((event) => (
          <li key={event.id}>
            <span className="trace-timeline__marker" aria-hidden="true" />
            <div className="trace-timeline__entry">
              <strong>{event.title}</strong>
              <time dateTime={event.at}>{formatDate(event.at)}</time>
              {event.kind !== 'original' && <p>Responsable: {event.actorId || 'No disponible'}</p>}
              {event.reason && <p>Motivo: {event.reason}</p>}
              {event.kind === 'original'
                ? <p>Categoría inicial: {event.updatedValue ?? 'No disponible'}</p>
                : <p>Valor anterior: {event.previousValue ?? 'No disponible'} · Actualizado: {event.updatedValue ?? 'No disponible'}</p>}
            </div>
          </li>
        ))}</ol>
        {record.reviews.length === 0 && <p>No se registraron revisiones posteriores.</p>}
      </section>
      <ReviewDecisionPanel record={record} onUpdated={onUpdated} />
    </div>
  )
}
