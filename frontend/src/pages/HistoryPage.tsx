import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Icon } from '../components/layout/Icon'
import { ProtectedEvidenceImage } from '../features/capture/ProtectedEvidenceImage'
import {
  filterHistory,
  formatDate,
  formatWeight,
  HISTORY_STATUS_LABELS,
  historyService,
  type EvaluationDetail,
  type EvaluationStatus,
  type EvaluationSummary,
  type HistoryFilters,
} from '../features/history/historyService'
import {
  ApiConnectionError,
  ApiResponseError,
  getSessionRole,
  resolveEvidenceUrl,
} from '../services/agroscanApi'
import { traceabilityService } from '../features/traceability/traceabilityService'
import './HistoryPage.css'

type LoadState<T> =
  | { kind: 'loading' }
  | { kind: 'unavailable' }
  | { kind: 'restricted' }
  | { kind: 'error' }
  | { kind: 'ready'; data: T }

const EMPTY_FILTERS: HistoryFilters = {
  query: '',
  lot: '',
  piece: '',
  product: '',
  status: '',
}

function useHistoryList(): {
  state: LoadState<EvaluationSummary[]>
  refresh: () => void
} {
  const [state, setState] = useState<LoadState<EvaluationSummary[]>>({
    kind: 'loading',
  })
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let current = true

    historyService.list().then(
      (records) => {
        if (current) setState({ kind: 'ready', data: records })
      },
      (error: unknown) => {
        if (current) {
          setState({
            kind:
              error instanceof ApiConnectionError
                ? 'unavailable'
                : error instanceof ApiResponseError &&
                    (error.status === 401 || error.status === 403)
                  ? 'restricted'
                  : 'error',
          })
        }
      },
    )

    return () => {
      current = false
    }
  }, [revision])

  function refresh() {
    setState({ kind: 'loading' })
    setRevision((value) => value + 1)
  }

  return { state, refresh }
}

function HistoryStateMessage({
  title,
  explanation,
  kind,
}: {
  title: string
  explanation: string
  kind: 'unavailable' | 'empty' | 'error' | 'restricted'
}) {
  return (
    <div
      className={`history-state history-state--${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      <span className="round-icon round-icon--blue">
        <Icon name={kind === 'error' ? 'alert' : 'database'} size={24} />
      </span>
      <strong>{title}</strong>
      <p>{explanation}</p>
    </div>
  )
}

function StatusLabel({ status }: { status: EvaluationStatus }) {
  return (
    <span className={`history-status history-status--${status}`}>
      {HISTORY_STATUS_LABELS[status]}
    </span>
  )
}

export function HistoryPage() {
  const { state, refresh } = useHistoryList()
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_FILTERS)

  const records = state.kind === 'ready' ? state.data : []
  const filteredRecords = filterHistory(records, filters)

  const lots = Array.from(
    new Set(records.map((record) => record.lotId)),
  ).sort((a, b) => a.localeCompare(b, 'es-PE'))

  const filtersActive =
    filters.query !== '' ||
    filters.lot !== '' ||
    filters.piece !== '' ||
    filters.product !== '' ||
    filters.status !== ''

  return (
    <div className="page-stack history-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de historial</span>
        <h1>Historial de evaluaciones</h1>
        <p>
          Consulta por lote, pieza y producto los registros que hayan sido
          almacenados y confirmados por el sistema.
        </p>

        {getSessionRole() === 'revisor' && (
          <p className="history-readonly-note">
            Modo revisor: consulta de evaluaciones y revisión de evidencias.
          </p>
        )}
      </div>

      {state.kind === 'unavailable' && (
        <div className="notice notice--warning" role="status">
          <Icon name="alert" size={19} />
          <span>
            <strong>Sin conexión con FastAPI:</strong> no se pudo consultar el
            historial. Los registros pueden seguir almacenados en SQLite;
            inicia el servidor y reintenta.
          </span>
        </div>
      )}

      <section
        className="panel history-panel"
        aria-labelledby="history-list-heading"
      >
        <div className="panel-heading history-panel__heading">
          <span className="round-icon round-icon--green">
            <Icon name="history" size={20} />
          </span>

          <div>
            <h2 id="history-list-heading">Evaluaciones registradas</h2>
            <p>
              Registros consultados desde FastAPI y almacenados en SQLite.
            </p>
          </div>
        </div>

        <div
          className="history-filters"
          role="search"
          aria-label="Filtros de historial"
        >
          <div className="history-field history-field--search">
            <label htmlFor="history-search">
              Buscar lote, pieza o evaluación
            </label>
            <input
              id="history-search"
              type="search"
              value={filters.query}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  query: event.target.value,
                }))
              }
              placeholder="Código o identificador"
            />
          </div>

          <div className="history-field">
            <label htmlFor="history-lot">Lote</label>
            <select
              id="history-lot"
              value={filters.lot ?? ''}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  lot: event.target.value,
                }))
              }
            >
              <option value="">Todos los lotes</option>
              {lots.map((lot) => (
                <option key={lot} value={lot}>
                  {lot}
                </option>
              ))}
            </select>
          </div>

          <div className="history-field">
            <label htmlFor="history-piece">Pieza</label>
            <input
              id="history-piece"
              type="search"
              placeholder="Ej.: PEE_01"
              value={filters.piece ?? ''}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  piece: event.target.value,
                }))
              }
            />
          </div>

          <div className="history-field">
            <label htmlFor="history-product">Producto</label>
            <select
              id="history-product"
              value={filters.product}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  product: event.target.value as HistoryFilters['product'],
                }))
              }
            >
              <option value="">Todos</option>
              <option value="mango">Mango</option>
              <option value="tomate">Tomate</option>
            </select>
          </div>

          <div className="history-field">
            <label htmlFor="history-status">Estado</label>
            <select
              id="history-status"
              value={filters.status}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  status: event.target.value as HistoryFilters['status'],
                }))
              }
            >
              <option value="">Todos</option>
              {Object.entries(HISTORY_STATUS_LABELS).map(
                ([key, label]) => (
                  <option value={key} key={key}>
                    {label}
                  </option>
                ),
              )}
            </select>
          </div>

          <button
            className="action-button action-button--secondary history-reset"
            type="button"
            onClick={() => setFilters(EMPTY_FILTERS)}
            disabled={!filtersActive}
          >
            Limpiar filtros
          </button>
        </div>

        <div className="history-results-bar" aria-live="polite">
          <span>
            {state.kind === 'ready'
              ? `${filteredRecords.length} ${
                  filteredRecords.length === 1
                    ? 'evaluación'
                    : 'evaluaciones'
                } encontradas`
              : state.kind === 'loading'
                ? 'Consultando backend…'
                : 'Consulta no disponible'}
          </span>
          <span>Datos persistidos, no simulados</span>
        </div>

        <div className="history-table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th scope="col">Evaluación / Pieza</th>
                <th scope="col">Producto</th>
                <th scope="col">Lote</th>
                <th scope="col">Fecha</th>
                <th scope="col">Peso</th>
                <th scope="col">Imágenes</th>
                <th scope="col">Estado</th>
                <th scope="col">Acción</th>
              </tr>
            </thead>

            <tbody>
              {filteredRecords.map((record) => (
                <tr key={record.id}>
                  <td>
                    <strong>{record.id}</strong>
                    <span>{record.pieceId}</span>
                  </td>
                  <td>
                    {record.product === 'mango' ? 'Mango' : 'Tomate'}
                  </td>
                  <td>{record.lotId}</td>
                  <td>{formatDate(record.registeredAt)}</td>
                  <td>{formatWeight(record.weightGrams)}</td>
                  <td>{record.imageCount}</td>
                  <td>
                    <StatusLabel status={record.status} />
                  </td>
                  <td>
                    <Link
                      className="history-detail-link"
                      to={`/historial/${encodeURIComponent(record.id)}`}
                    >
                      Ver detalle
                      <Icon name="arrow-right" size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {state.kind === 'loading' && (
          <div className="history-state" role="status">
            Consultando historial…
          </div>
        )}

        {state.kind === 'unavailable' && (
          <div className="history-state">
            <HistoryStateMessage
              kind="unavailable"
              title="FastAPI no disponible"
              explanation="No fue posible contactar con el backend. La ausencia de filas no significa que no existan evaluaciones guardadas."
            />
            <button
              type="button"
              className="action-button action-button--secondary"
              onClick={refresh}
            >
              Reintentar consulta
            </button>
          </div>
        )}

        {state.kind === 'restricted' && (
          <HistoryStateMessage
            kind="restricted"
            title="Acceso no autorizado"
            explanation="El backend ha denegado esta consulta (401/403). No se mostrarán datos de evaluaciones."
          />
        )}

        {state.kind === 'error' && (
          <div className="history-state">
            <HistoryStateMessage
              kind="error"
              title="No se pudo consultar el historial"
              explanation="Se produjo un error al obtener los registros. El historial no se ha actualizado."
            />
            <button
              type="button"
              className="action-button action-button--secondary"
              onClick={refresh}
            >
              Reintentar consulta
            </button>
          </div>
        )}

        {state.kind === 'ready' && records.length === 0 && (
          <HistoryStateMessage
            kind="empty"
            title="Sin evaluaciones registradas"
            explanation="El servicio respondió correctamente, pero no devolvió evaluaciones. Los filtros no afectan este resultado."
          />
        )}

        {state.kind === 'ready' &&
          records.length > 0 &&
          filteredRecords.length === 0 && (
            <HistoryStateMessage
              kind="empty"
              title="Sin coincidencias"
              explanation="No hay registros que cumplan los filtros seleccionados. Prueba con otros criterios."
            />
          )}
      </section>

      <section className="panel history-guide" aria-labelledby="history-guide-title">
        <div className="panel-heading">
          <span className="round-icon round-icon--green">
            <Icon name="info" size={20} />
          </span>
          <h2 id="history-guide-title">Información que se conservará</h2>
        </div>

        <p>
          Las consultas muestran registros persistidos. Tras reiniciar FastAPI,
          vuelve a iniciar sesión y busca el mismo ID: los registros se
          recuperan desde SQLite. Las evaluaciones en proceso pueden no tener
          peso ni imágenes.
        </p>

        {getSessionRole() !== 'revisor' && (
          <Link className="text-link" to="/evaluacion">
            Ir a Evaluación
            <Icon name="arrow-right" size={16} />
          </Link>
        )}
      </section>
    </div>
  )
}

export function HistoryDetailPage() {
  const { evaluationId } = useParams<{ evaluationId: string }>()

  if (!evaluationId) {
    return (
      <HistoryStateMessage
        kind="empty"
        title="Identificador no proporcionado"
        explanation="Regresa al historial para seleccionar una evaluación."
      />
    )
  }

  return (
    <HistoryDetailContent
      key={evaluationId}
      evaluationId={evaluationId}
    />
  )
}

function HistoryDetailContent({
  evaluationId,
}: {
  evaluationId: string
}) {
  const [state, setState] = useState<LoadState<EvaluationDetail | null>>({
    kind: 'loading',
  })
  const [newValue, setNewValue] = useState<'E0' | 'E1'>('E0')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [reviewMessage, setReviewMessage] = useState('')
  const [reviewError, setReviewError] = useState('')

  const isReviewer = getSessionRole() === 'revisor'

  async function loadDetail() {
    setState({ kind: 'loading' })

    try {
      const data = await historyService.getById(evaluationId)
      setState({ kind: 'ready', data })
    } catch (error: unknown) {
      setState({
        kind:
          error instanceof ApiConnectionError
            ? 'unavailable'
            : error instanceof ApiResponseError &&
                (error.status === 401 || error.status === 403)
              ? 'restricted'
              : 'error',
      })
    }
  }

  useEffect(() => {
    let current = true

    historyService.getById(evaluationId).then(
      (data) => {
        if (current) {
          setState({ kind: 'ready', data })
        }
      },
      (error: unknown) => {
        if (current) {
          setState({
            kind:
              error instanceof ApiConnectionError
                ? 'unavailable'
                : error instanceof ApiResponseError &&
                    (error.status === 401 || error.status === 403)
                  ? 'restricted'
                  : 'error',
          })
        }
      },
    )

    return () => {
      current = false
    }
  }, [evaluationId])

  async function handleReviewSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    // Comprobar que la evaluación está cargada antes de acceder a sus datos.
    if (
      state.kind !== 'ready' ||
      state.data === null ||
      !isReviewer ||
      saving
    ) {
      return
    }

    // Guardar una referencia segura para TypeScript.
    const evaluation = state.data
    const cleanReason = reason.trim()

    if (!cleanReason) {
      setReviewError('Debes escribir el motivo de la revisión.')
      return
    }

    if (
      !['pending_review', 'completed'].includes(evaluation.status)
    ) {
      setReviewError('Esta evaluación no admite nuevas revisiones.')
      return
    }

    setSaving(true)
    setReviewError('')
    setReviewMessage('')

    try {
      await traceabilityService.addReview(evaluationId, {
        reason: cleanReason,
        newValue,
      })

      setReviewMessage('La revisión se registró correctamente.')
      setReason('')

      await loadDetail()
    } catch (error: unknown) {
      setReviewError(
        error instanceof ApiResponseError
          ? `No se pudo registrar la revisión: ${error.message}`
          : error instanceof ApiConnectionError
            ? 'No hay conexión con el backend.'
            : 'Ocurrió un error al registrar la revisión.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-stack history-page">
      <div className="page-heading">
        <span className="eyebrow">
          {isReviewer ? 'Centro de revisión' : 'Historial / Detalle'}
        </span>

        <h1>Detalle de evaluación</h1>

        <p>
          Consulta la información, las fotografías y los datos registrados
          de cada producto agrícola.
        </p>
      </div>

      <div className="traceability-history-links">
        <Link className="text-link history-back" to="/historial">
          ← Volver al historial
        </Link>
      </div>

      <section className="panel" aria-label="Detalle de evaluación">
        {state.kind === 'loading' && (
          <p role="status">Consultando detalle…</p>
        )}

        {state.kind === 'unavailable' && (
          <HistoryStateMessage
            kind="unavailable"
            title="Backend desconectado"
            explanation="No se puede consultar este detalle porque FastAPI no responde."
          />
        )}

        {state.kind === 'restricted' && (
          <HistoryStateMessage
            kind="restricted"
            title="Acceso denegado"
            explanation="La API denegó el acceso a este detalle (401/403)."
          />
        )}

        {state.kind === 'error' && (
          <HistoryStateMessage
            kind="error"
            title="Error al consultar el detalle"
            explanation="No se pudo recuperar la información. Intenta nuevamente."
          />
        )}

        {state.kind === 'ready' && state.data === null && (
          <HistoryStateMessage
            kind="empty"
            title="Evaluación no encontrada"
            explanation="No existe un registro asociado a este identificador."
          />
        )}

        {state.kind === 'ready' && state.data !== null && (
          <div className="history-detail">
            <div className="history-detail__header">
              <div>
                <span className="history-detail__hint">Identificador</span>
                <h2>{state.data.id}</h2>
              </div>

              <StatusLabel status={state.data.status} />
            </div>

            <dl className="history-detail__grid">
              <div>
                <dt>Pieza</dt>
                <dd>{state.data.pieceId}</dd>
              </div>

              <div>
                <dt>Lote</dt>
                <dd>{state.data.lotId}</dd>
              </div>

              <div>
                <dt>Producto</dt>
                <dd>
                  {state.data.product === 'mango' ? 'Mango' : 'Tomate'}
                </dd>
              </div>

              <div>
                <dt>Fecha</dt>
                <dd>{formatDate(state.data.registeredAt)}</dd>
              </div>

              <div>
                <dt>Peso</dt>
                <dd>{formatWeight(state.data.weightGrams)}</dd>
              </div>

              <div>
                <dt>Imágenes asociadas</dt>
                <dd>{state.data.evidence.length}</dd>
              </div>

              <div>
                <dt>Categoría visual</dt>
                <dd>{state.data.visualCategory ?? 'No disponible'}</dd>
              </div>

              <div>
                <dt>Observación de revisión</dt>
                <dd>
                  {state.data.reviewNote ?? 'Sin observaciones registradas'}
                </dd>
              </div>

              {state.data.failureReason && (
                <div>
                  <dt>Motivo del error</dt>
                  <dd>{state.data.failureReason}</dd>
                </div>
              )}
            </dl>

            <h3>Evidencia visual</h3>

            {state.data.evidence.length === 0 ? (
              <p>Sin imágenes vinculadas.</p>
            ) : (
              <ul className="history-evidence">
                {state.data.evidence.map((item) => (
                  <li key={item.id}>
                    <strong>
                      {item.view} · {item.id}
                    </strong>

                    {resolveEvidenceUrl(item.imageUrl) ? (
                      <ProtectedEvidenceImage
                        className="history-evidence__image"
                        path={item.imageUrl}
                        alt={`Evidencia ${item.view}`}
                      />
                    ) : (
                      <span>Referencia de imagen no reconocida.</span>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {isReviewer && (
              <section
                className="review-form-panel"
                aria-labelledby="review-form-title"
              >
                <div className="panel-heading">
                  <span className="round-icon round-icon--green">
                    <Icon name="clipboard" size={21} />
                  </span>

                  <div>
                    <h2 id="review-form-title">Registrar revisión</h2>
                    <p>
                      Verifica la evidencia y registra la clasificación
                      correspondiente.
                    </p>
                  </div>
                </div>

                {['pending_review', 'completed'].includes(
                  state.data.status,
                ) ? (
                  <form
                    className="review-form"
                    onSubmit={handleReviewSubmit}
                  >
                    <div className="history-field">
                      <label htmlFor="review-original">
                        Clasificación actual
                      </label>

                      <input
                        id="review-original"
                        value={
                          state.data.visualCategory ?? 'No disponible'
                        }
                        readOnly
                      />
                    </div>

                    <div className="history-field">
                      <label htmlFor="review-new-value">
                        Nueva clasificación
                      </label>

                      <select
                        id="review-new-value"
                        value={newValue}
                        onChange={(event) =>
                          setNewValue(
                            event.target.value as 'E0' | 'E1',
                          )
                        }
                        disabled={saving}
                      >
                        <option value="E0">E0 - Primera</option>
                        <option value="E1">E1 - Segunda</option>
                      </select>
                    </div>

                    <div className="history-field">
                      <label htmlFor="review-reason">
                        Motivo de la revisión *
                      </label>

                      <textarea
                        id="review-reason"
                        value={reason}
                        onChange={(event) =>
                          setReason(event.target.value)
                        }
                        placeholder="Explica por qué corresponde esta clasificación..."
                        maxLength={500}
                        rows={4}
                        required
                        disabled={saving}
                      />

                      <small>{reason.length}/500 caracteres</small>
                    </div>

                    {reviewError && (
                      <div
                        className="notice notice--warning"
                        role="alert"
                      >
                        <Icon name="alert" size={18} />
                        <span>{reviewError}</span>
                      </div>
                    )}

                    {reviewMessage && (
                      <div
                        className="notice notice--success"
                        role="status"
                      >
                        <Icon name="clipboard" size={18} />
                        <span>{reviewMessage}</span>
                      </div>
                    )}

                    <button
                      className="action-button action-button--primary"
                      type="submit"
                      disabled={saving || !reason.trim()}
                    >
                      <Icon name="clipboard" size={18} />
                      {saving
                        ? 'Guardando revisión...'
                        : 'Guardar revisión'}
                    </button>
                  </form>
                ) : (
                  <p role="status">
                    Esta evaluación no está disponible para revisión.
                  </p>
                )}
              </section>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
