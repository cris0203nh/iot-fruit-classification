import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { formatDate, formatWeight } from '../features/history/historyService'
import {
  buildTraceabilityTimeline,
  traceabilityService,
  validateEvaluationId,
  type TraceabilityRecord,
} from '../features/traceability/traceabilityService'
import { ApiConnectionError, ApiResponseError, resolveEvidenceUrl } from '../services/agroscanApi'
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
    <div className="page-stack trace-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de trazabilidad</span>
        <h1>Trazabilidad de evaluaciones</h1>
        <p>Consulta las evidencias y revisiones vinculadas a una pieza. El registro original debe conservarse sin modificaciones.</p>
      </div>
      <div className="notice" role="status">
        <Icon name="info" size={19} />
        <span><strong>Consulta conectada:</strong> la información se solicita a FastAPI. Las operaciones de revisión y anulación permanecen deshabilitadas hasta contar con autorización verificable.</span>
      </div>

      <section className="panel trace-search" aria-labelledby="trace-search-heading">
        <div className="panel-heading">
          <span className="round-icon round-icon--green"><Icon name="network" size={20} /></span>
          <div>
            <h2 id="trace-search-heading">Consultar una evaluación</h2>
            <p>Ingresa el identificador asignado por el backend. La consulta verificará si existe en SQLite.</p>
          </div>
        </div>
        <form onSubmit={handleSubmit} noValidate className="trace-form">
          <div className="trace-field">
            <label htmlFor="trace-evaluation-id">Identificador de evaluación *</label>
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
            {submitted && !validId
              ? <p className="trace-error" role="alert" id="trace-evaluation-error">Utiliza el formato emitido por FastAPI: E- seguido de 1 a 9 dígitos (ej.: E-000001).</p>
              : <p id="trace-evaluation-help">Referencia de evaluación, no número de lote ni de pieza.</p>}
          </div>
          <button type="submit" className="action-button action-button--primary">Consultar referencia <Icon name="arrow-right" size={16} /></button>
        </form>
        <Link className="text-link" to="/historial">Ver historial de evaluaciones <Icon name="arrow-right" size={16} /></Link>
      </section>

      <section className="trace-overview" aria-label="Información sobre la trazabilidad">
        <article className="panel trace-overview__card">
          <div className="panel-heading"><span className="round-icon round-icon--blue"><Icon name="database" size={21} /></span><h2>Evidencia vinculada</h2></div>
          <p>La consulta mostrará pieza, lote, producto, peso, vistas RGB, calibración y versiones de reglas o modelo, solo cuando estos datos estén confirmados.</p>
        </article>
        <article className="panel trace-overview__card">
          <div className="panel-heading"><span className="round-icon round-icon--purple"><Icon name="history" size={21} /></span><h2>Revisiones auditables</h2></div>
          <p>Cada modificación deberá conservar responsable, fecha, motivo y valores anterior y actualizado. La interfaz será de solo lectura hasta implementar autorización real.</p>
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
      <div className="page-stack trace-page">
        <div className="page-heading"><h1>Referencia no válida</h1><p>La dirección no contiene un identificador de evaluación admitido.</p></div>
        <Link className="text-link" to="/trazabilidad">← Volver a trazabilidad</Link>
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
    <div className="page-stack trace-page">
      <div className="page-heading">
        <span className="eyebrow">Trazabilidad / Detalle</span>
        <h1>Registro trazable</h1>
        <p>Consulta de lectura únicamente. Ninguna revisión o anulación puede realizarse desde esta interfaz sin un servicio autorizado.</p>
      </div>
      <Link className="text-link" to="/trazabilidad">← Volver a trazabilidad</Link>
      <section className="panel trace-detail" aria-label="Detalle de trazabilidad">
        <div className="panel-heading">
          <span className="round-icon round-icon--blue"><Icon name="clipboard" size={21} /></span>
          <div>
            <h2>Evaluación solicitada</h2>
            <p className="trace-identifier">{evaluationId}</p>
          </div>
        </div>
        {state.kind === 'loading' && <p role="status">Consultando evidencia y revisiones…</p>}
        {state.kind === 'unavailable' && (
          <div className="trace-message" role="status">
            <Icon name="database" size={28} />
            <h3>Backend desconectado</h3>
            <p>FastAPI no responde. No podemos verificar si esta evaluación existe; sus registros no se han modificado.</p>
            <button type="button" className="action-button action-button--secondary" onClick={retry}>Reintentar</button>
          </div>
        )}
        {state.kind === 'restricted' && <div className="trace-message trace-message--error" role="alert"><Icon name="alert" size={26}/><h3>Acceso denegado</h3><p>FastAPI rechazó la consulta (401/403). No hay datos que mostrar.</p></div>}
        {state.kind === 'not-found' && (
          <div className="trace-message" role="status">
            <Icon name="info" size={26} /><h3>Evaluación no encontrada</h3>
            <p>El servicio respondió correctamente, pero no existe un registro asociado a la referencia solicitada.</p>
          </div>
        )}
        {state.kind === 'error' && (
          <div className="trace-message trace-message--error" role="alert">
            <Icon name="alert" size={26} /><h3>Error al consultar la trazabilidad</h3>
            <p>No se pudo recuperar la información. Ninguna evidencia ha sido actualizada.</p>
            <button type="button" className="action-button action-button--secondary" onClick={retry}>Reintentar</button>
          </div>
        )}
        {state.kind === 'ready' && <TraceabilityRecordContent record={state.record} />}
      </section>
    </div>
  )
}

function TraceabilityRecordContent({ record }: { record: TraceabilityRecord }) {
  const timeline = buildTraceabilityTimeline(record)
  const { evaluation } = record
  return (
    <div className="trace-record">
      <dl className="trace-data-grid">
        <div><dt>Estado de la evaluación</dt><dd>{evaluation.status === 'processing' ? 'En proceso' : evaluation.status === 'completed' ? 'Completada' : evaluation.status === 'pending_review' ? 'Por revisar' : evaluation.status === 'cancelled' ? 'Anulada' : 'Error'}</dd></div>
        {evaluation.failureReason && <div><dt>Motivo del error</dt><dd>{evaluation.failureReason}</dd></div>}
        <div><dt>Lote</dt><dd>{evaluation.lotId}</dd></div>
        <div><dt>Pieza</dt><dd>{evaluation.pieceId}</dd></div>
        <div><dt>Producto</dt><dd>{evaluation.product === 'mango' ? 'Mango' : 'Tomate'}</dd></div>
        <div><dt>Peso registrado</dt><dd>{formatWeight(evaluation.weightGrams)}</dd></div>
        <div><dt>Fecha de registro</dt><dd>{formatDate(evaluation.registeredAt)}</dd></div>
        <div><dt>Calibración</dt><dd>{record.calibrationReference ?? 'No disponible'}</dd></div>
        <div><dt>Versión del modelo</dt><dd>{record.modelVersion ?? 'No disponible'}</dd></div>
        <div><dt>Versión de reglas</dt><dd>{record.rulesVersion ?? 'No disponible'}</dd></div>
      </dl>
      <section className="trace-record__section" aria-label="Evidencias visuales">
        <h3>Evidencias visuales ({evaluation.evidence.length})</h3>
        {evaluation.evidence.length === 0
          ? <p>No se registraron imágenes asociadas.</p>
          : <ul className="trace-evidence-list">{evaluation.evidence.map((item) => <li key={item.id}><div><strong>{item.view}</strong><span>Referencia: {item.id}</span>{resolveEvidenceUrl(item.imageUrl) ? <img className="trace-evidence__image" src={resolveEvidenceUrl(item.imageUrl)!} alt={`Evidencia ${item.view} de ${evaluation.id}`} loading="lazy" /> : <span>Ruta de imagen no reconocida.</span>}</div></li>)}</ul>}
          <p>Las imágenes se consultan desde la API local. El acceso a evidencias aún no tiene autenticación y no debe exponerse públicamente.</p>
      </section>
      <section className="trace-record__section" aria-labelledby="trace-timeline-title">
        <h3 id="trace-timeline-title">Historial de versiones y revisiones</h3>
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
    </div>
  )
}
