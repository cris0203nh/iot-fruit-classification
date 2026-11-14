import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { ProtectedEvidenceImage } from '../features/capture/ProtectedEvidenceImage'
import { ReviewDecisionPanel } from '../features/traceability/ReviewDecisionPanel'
import { traceabilityService, type TraceabilityRecord } from '../features/traceability/traceabilityService'
import { describeReviewReason, mayRecordReview,
  type ReviewPriority, type ReviewProduct, type ReviewQueueFilters,
  type ReviewQueueItem, type ReviewQueueResponse } from '../features/reviews/reviewQueuePolicy.ts'
import { ApiConnectionError, ApiResponseError, getQualityProposals, getReviewQueue, getSessionRole, type QualityProposal } from '../services/agroscanApi'
import './ReviewQueuePage.css'

const PAGE_SIZE = 12
const PRIORITY: Record<ReviewPriority, string> = { high: 'Prioridad alta', normal: 'Prioridad ordinaria' }
type LoadState = { status: 'loading' | 'ready' | 'error' | 'unavailable' | 'restricted'; data?: ReviewQueueResponse; message?: string }
type AppliedFilters = Pick<ReviewQueueFilters, 'lot' | 'product' | 'priority'>
const EMPTY: AppliedFilters = {}

function errorState(error: unknown): LoadState {
  if (error instanceof ApiConnectionError) return { status: 'unavailable', message: 'FastAPI no responde. No se han modificado evaluaciones.' }
  if (error instanceof ApiResponseError && (error.status === 401 || error.status === 403)) {
    return { status: 'restricted', message: 'Tu sesión no tiene permisos para consultar la cola. Inicia sesión como revisor o administrador.' }
  }
  return { status: 'error', message: error instanceof Error ? error.message : 'No fue posible consultar la bandeja.' }
}

/** Read-only experimental proposals; saves are exclusively AG-038 decisions. */
function ExperimentalProposals({ evaluationId }: { evaluationId: string }) {
  const [rows, setRows] = useState<QualityProposal[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let current = true
    void getQualityProposals(evaluationId).then(data => { if (current) { setRows(data.filter(x =>
      ['experimental_proposal', 'needs_review', 'experimental_e0e1e2_pilot', 'experimental_e0e1e2_v2'].includes(x.status)))
      setError(null) } }).catch(cause => { if (current) setError(cause instanceof Error ? cause.message : 'No hay propuestas consultables.') })
    return () => { current = false }
  }, [evaluationId])
  return <section className="review-queue__proposals" aria-label="Propuestas IA experimentales">
    <h4>Propuestas de IA · no confirmadas</h4>
    {error && <p role="status">No se pudieron consultar las propuestas: {error}</p>}
    {!error && rows.length === 0 && <p>Sin propuestas E0/E1/E2 registradas para mostrar.</p>}
    {rows.length > 0 && <ul>{rows.map(x => <li key={x.id}>
      <strong>{x.proposedGrade ? `Sugerencia ${x.proposedGrade}` : 'Sin grado sugerido'}</strong>
      {' · '}{x.reason} · Modelo {x.modelVersion}. Revisión humana obligatoria.
    </li>)}</ul>}
  </section>
}

function PendingCase({ item, onUpdated }: { item: ReviewQueueItem; onUpdated: () => void }) {
  const [record, setRecord] = useState<TraceabilityRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let active = true
    void traceabilityService.getByEvaluationId(item.evaluationId).then(value => {
      if (!active) return
      if (value) { setRecord(value); setError(null) }
      else setError('No existe un expediente para esta evaluación.')
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudo abrir el expediente.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [item.evaluationId, refresh])

  function updated() {
    setRefresh(value => value + 1)
    onUpdated()
  }

  const pending = new Set(item.imageIds)
  return <section className="review-queue__detail" aria-label={`Expediente ${item.evaluationId}`}>
    <p><strong>Fotografías pendientes según AG-056:</strong> {item.imageIds.join(', ') || (
      item.reasons.some(reason => reason.code === 'acquisition_pending_review')
        ? 'Revisar todas las vistas de la adquisición.'
        : 'Incidencia sin identificación de fotografía.')}</p>
    {loading && !record && <p role="status">Cargando expediente y evidencia original…</p>}
    {error && <p role="alert">{error}</p>}
    {record && <>
      <h4>Evidencia original (acceso autenticado)</h4>
      {record.evaluation.evidence.length === 0 && <p role="alert">No existen fotografías para inspeccionar. No registres una clasificación sin evidencia.</p>}
      <div className="review-queue__photos">
        {record.evaluation.evidence.map(img => <figure key={img.id} className={pending.has(img.id) ? 'review-queue__photo review-queue__photo--pending' : 'review-queue__photo'}>
          <ProtectedEvidenceImage path={img.imageUrl} alt={`Fotografía original ${img.view}, ${img.id}, evaluación ${item.evaluationId}`} />
          <figcaption>{img.view} · {img.id} {pending.has(img.id) ? '· requiere revisión' : '· evidencia relacionada'}</figcaption>
        </figure>)}
      </div>
      {item.imageIds.some(id => !record.evaluation.evidence.some(img => img.id === id)) &&
        <p role="alert">Hay referencias de imagen que ya no están asociadas al expediente. Verifica la integridad antes de decidir.</p>}
      <ExperimentalProposals evaluationId={item.evaluationId} />
      {mayRecordReview(item.status) && ['completed', 'pending_review'].includes(record.evaluation.status) && record.evaluation.evidence.length > 0
        ? <>
          <p className="review-queue__warning">AG-038 guarda decisiones por fotografía y SHA-256. Selecciona la fotografía pendiente correcta. La propuesta de IA no es una clasificación confirmada.</p>
          <ReviewDecisionPanel record={record} onUpdated={updated} pendingImageIds={item.imageIds} />
        </>
        : <p role="status">Este caso no admite decisiones AG-038 desde la bandeja. Requiere completar captura o recuperar evidencia antes de revisar.</p>}
      <Link to={`/trazabilidad/${encodeURIComponent(item.evaluationId)}`} className="review-queue__link">Abrir trazabilidad completa <Icon name="arrow-right" size={16} /></Link>
    </>}
  </section>
}

export function ReviewQueuePage() {
  const role = getSessionRole()
  const authorized = role === 'revisor' || role === 'administrador'
  const [lot, setLot] = useState('')
  const [product, setProduct] = useState<ReviewProduct | ''>('')
  const [priority, setPriority] = useState<ReviewPriority | ''>('')
  const [applied, setApplied] = useState<AppliedFilters>(EMPTY)
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    if (!authorized) return
    let current = true
    const filters = { ...applied, limit: PAGE_SIZE, offset }
    void getReviewQueue(filters).then(data => {
      if (current) setState({ status: 'ready', data })
    }).catch(error => { if (current) setState(errorState(error)) })
    return () => { current = false }
  }, [authorized, applied, offset, revision])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSelected(null)
    setOffset(0)
    setState({ status: 'loading' })
    setApplied({ lot: lot.trim() || undefined, product: product || undefined, priority: priority || undefined })
  }
  function clear() {
    setLot(''); setProduct(''); setPriority(''); setSelected(null); setOffset(0)
    setState({ status: 'loading' }); setApplied({}); setRevision(value => value + 1)
  }
  function refresh() {
    setState({ status: 'loading' })
    setRevision(value => value + 1)
  }
  function page(next: number) {
    setSelected(null); setOffset(next); setState({ status: 'loading' })
  }

  if (!authorized) return <section className="review-queue" aria-label="Acceso restringido">
    <h1>Revisiones · acceso restringido</h1>
    <p>Solo los revisores y administradores pueden acceder a la bandeja de intervención humana.</p>
    <Link to="/">Volver al inicio</Link>
  </section>

  const data = state.status === 'ready' ? state.data : undefined
  return <div className="review-queue">
    <header className="review-queue__head">
      <p className="review-queue__eyebrow">AG-056 · Supervisión humana</p>
      <h1>Bandeja de revisiones pendientes</h1>
      <p>Solo se presentan evaluaciones con intervención pendiente según las reglas del servidor. La calidad E0/E1/E2 de AG-055 sigue siendo experimental y requiere decisión humana.</p>
    </header>
    <section className="review-queue__filters" aria-label="Filtrar cola de revisión">
      <form onSubmit={submit} className="review-queue__form">
        <label>Lote<input value={lot} maxLength={32} onChange={event => setLot(event.target.value)} placeholder="Código de lote" /></label>
        <label>Producto<select value={product} onChange={event => setProduct(event.target.value as ReviewProduct | '')}>
          <option value="">Todos</option><option value="mango">Mango</option><option value="tomate">Tomate</option>
        </select></label>
        <label>Prioridad<select value={priority} onChange={event => setPriority(event.target.value as ReviewPriority | '')}>
          <option value="">Todas</option><option value="high">Alta</option><option value="normal">Ordinaria</option>
        </select></label>
        <div className="review-queue__buttons">
          <button type="submit" className="action-button action-button--primary">Aplicar filtros</button>
          <button type="button" className="action-button action-button--secondary" onClick={clear}>Limpiar</button>
        </div>
      </form>
    </section>
    <div className="review-queue__toolbar">
      <h2>Casos que requieren intervención</h2>
      <button type="button" className="action-button action-button--secondary" onClick={refresh} disabled={state.status === 'loading'}>Actualizar bandeja</button>
    </div>
    {data && <div className="review-queue__stats" aria-label="Contadores del servidor">
      <span><strong>{data.counts.all}</strong> pendientes (sin filtrar prioridad)</span>
      <span><strong>{data.counts.high}</strong> prioridad alta</span>
      <span><strong>{data.counts.normal}</strong> prioridad ordinaria</span>
      <span><strong>{data.total}</strong> resultados con filtros aplicados</span>
    </div>}
    {state.status === 'loading' && <p className="review-queue__message" role="status">Consultando casos pendientes…</p>}
    {(state.status === 'error' || state.status === 'unavailable' || state.status === 'restricted') && <div className="review-queue__message" role="alert">
      <p>{state.message}</p><button type="button" onClick={refresh} className="action-button action-button--secondary">Reintentar</button>
    </div>}
    {data?.items.length === 0 && <p className="review-queue__message" role="status">No hay casos pendientes con los filtros seleccionados. Esto no acredita el rendimiento del modelo.</p>}
    {data && data.items.length > 0 && <section className="review-queue__items" aria-label="Lista de casos pendientes">
      {data.items.map(item => <article className="review-queue__card" key={item.evaluationId}>
        <div className="review-queue__card-header">
          <div><p className="review-queue__id">{item.evaluationId}</p><h3>{item.product === 'mango' ? 'Mango' : 'Tomate'} · {item.pieceId}</h3>
            <p>Lote {item.lotId} · {new Date(item.registeredAt).toLocaleString('es-PE')}</p></div>
          <strong className={`review-queue__priority review-queue__priority--${item.priority}`}>{PRIORITY[item.priority]}</strong>
        </div>
        <p className="review-queue__meta">Estado: {item.status} · Fotografías registradas: {item.imageCount}
          · Vistas señaladas: {item.imageIds.length ? item.imageIds.join(', ') : 'sin asociación individual'}</p>
        <ul className="review-queue__reasons">{item.reasons.map((reason, index) => <li key={`${reason.code}-${reason.imageId ?? 'general'}-${index}`}>
          <span>{describeReviewReason(reason.code)}</span>{reason.imageId && <small> · {reason.imageId}</small>}
        </li>)}</ul>
        <div className="review-queue__actions">
          <button type="button" className="action-button action-button--primary"
            aria-expanded={selected === item.evaluationId} aria-controls={`review-case-${item.evaluationId}`}
            onClick={() => setSelected(id => id === item.evaluationId ? null : item.evaluationId)}>
            {selected === item.evaluationId ? 'Cerrar expediente' : 'Inspeccionar evidencia y decidir'}
          </button>
          <Link className="review-queue__link" to={`/trazabilidad/${encodeURIComponent(item.evaluationId)}`}>Trazabilidad <Icon name="arrow-right" size={15} /></Link>
        </div>
        {selected === item.evaluationId && <div id={`review-case-${item.evaluationId}`}>
          <PendingCase key={item.evaluationId} item={item} onUpdated={refresh} />
        </div>}
      </article>)}
    </section>}
    {data && <nav className="review-queue__pagination" aria-label="Paginación de revisiones">
      <button type="button" className="action-button action-button--secondary" disabled={offset === 0} onClick={() => page(Math.max(0, offset - PAGE_SIZE))}>Anterior</button>
      <span>Mostrando {data.total ? offset + 1 : 0}–{Math.min(offset + data.items.length, data.total)} de {data.total}</span>
      <button type="button" className="action-button action-button--secondary" disabled={!data.hasMore} onClick={() => page(offset + PAGE_SIZE)}>Siguiente</button>
    </nav>}
    <p className="review-queue__footer">Las decisiones canónicas se registran mediante AG-038 y se recalcula la cola al actualizar. La bandeja no aprueba ni modifica fotografías automáticamente.</p>
  </div>
}
