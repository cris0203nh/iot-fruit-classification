
import { useEffect, useMemo, useState } from 'react'
import { listEvaluations } from '../services/agroscanApi'
import type { EvaluationSummary } from '../features/history/historyService'
import './StatisticsPage.css'

type ProductFilter = '' | 'mango' | 'tomate'

type StatusKey =
  | 'completed'
  | 'processing'
  | 'error'
  | 'pending_review'
  | 'cancelled'

const statusLabels: Record<StatusKey, string> = {
  completed: 'Completadas',
  processing: 'En proceso',
  error: 'Con errores',
  pending_review: 'Por revisar',
  cancelled: 'Anuladas',
}

const statusColors: Record<StatusKey, string> = {
  completed: '#159568',
  processing: '#3986d7',
  error: '#e45b55',
  pending_review: '#e5a13b',
  cancelled: '#8995a3',
}

const statusOrder: StatusKey[] = [
  'completed',
  'processing',
  'pending_review',
  'error',
  'cancelled',
]

function dateKey(value: string): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return ''

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}


function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-PE').format(value)
}

function countStatus(
  items: EvaluationSummary[],
  status: StatusKey,
): number {
  return items.filter(item => item.status === status).length
}

export function StatisticsPage() {
  const [evaluations, setEvaluations] = useState<EvaluationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [product, setProduct] = useState<ProductFilter>('')
  const [lot, setLot] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  async function loadStatistics() {
    setLoading(true)
    setError('')

    try {
      const data = await listEvaluations()
      setEvaluations(data)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No se pudieron consultar las estadísticas.',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadStatistics()
  }, [])

  const lots = useMemo(
    () => [...new Set(evaluations.map(item => item.lotId))]
      .filter(Boolean)
      .sort(),
    [evaluations],
  )

  const filtered = useMemo(() => {
    return evaluations.filter(item => {
      const date = dateKey(item.registeredAt)

      return (
        (!product || item.product === product) &&
        (!lot || item.lotId === lot) &&
        (!fromDate || date >= fromDate) &&
        (!toDate || date <= toDate)
      )
    })
  }, [evaluations, product, lot, fromDate, toDate])

  const metrics = useMemo(() => ({
    total: filtered.length,
    completed: countStatus(filtered, 'completed'),
    processing: countStatus(filtered, 'processing'),
    errors: countStatus(filtered, 'error'),
    pending: countStatus(filtered, 'pending_review'),
    mango: filtered.filter(item => item.product === 'mango').length,
    tomato: filtered.filter(item => item.product === 'tomate').length,
  }), [filtered])

  const lotData = useMemo(() => {
    const counts = new Map<string, number>()

    filtered.forEach(item => {
      counts.set(item.lotId, (counts.get(item.lotId) ?? 0) + 1)
    })

    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  }, [filtered])

  const timeline = useMemo(() => {
    const counts = new Map<string, number>()

    filtered.forEach(item => {
      const date = dateKey(item.registeredAt)
      if (date) counts.set(date, (counts.get(date) ?? 0) + 1)
    })

    return [...counts.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-14)
      .map(([date, count]) => ({ date, count }))
  }, [filtered])

  const distribution = useMemo(() => {
    return (['mango', 'tomate'] as const).map(fruit => ({
      product: fruit,
      total: filtered.filter(item => item.product === fruit).length,
      statuses: statusOrder.map(status => ({
        status,
        count: filtered.filter(
          item => item.product === fruit && item.status === status,
        ).length,
      })),
    }))
  }, [filtered])

  const maxLot = Math.max(1, ...lotData.map(item => item.count))
  const maxDate = Math.max(1, ...timeline.map(item => item.count))

  function clearFilters() {
    setProduct('')
    setLot('')
    setFromDate('')
    setToDate('')
  }

  return (
    <div className="page-stack statistics-page">

      <div className="page-heading statistics-heading">
        <span className="eyebrow">Administración / Estadísticas</span>
        <h1>Estadísticas de AgroScan</h1>
        <p>
          Análisis gráfico de las evaluaciones registradas de mango y tomate.
        </p>
      </div>

      <section className="statistics-filters">
        <div>
          <label htmlFor="stats-from">Desde</label>
          <input
            id="stats-from"
            type="date"
            value={fromDate}
            max={toDate || undefined}
            onChange={event => setFromDate(event.target.value)}
          />
        </div>

        <div>
          <label htmlFor="stats-to">Hasta</label>
          <input
            id="stats-to"
            type="date"
            value={toDate}
            min={fromDate || undefined}
            onChange={event => setToDate(event.target.value)}
          />
        </div>

        <div>
          <label htmlFor="stats-product">Producto</label>
          <select
            id="stats-product"
            value={product}
            onChange={event => setProduct(event.target.value as ProductFilter)}
          >
            <option value="">Todos los productos</option>
            <option value="mango">Mango</option>
            <option value="tomate">Tomate</option>
          </select>
        </div>

        <div>
          <label htmlFor="stats-lot">Lote</label>
          <select
            id="stats-lot"
            value={lot}
            onChange={event => setLot(event.target.value)}
          >
            <option value="">Todos los lotes</option>
            {lots.map(item => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="statistics-clear"
          onClick={clearFilters}
        >
          Limpiar filtros
        </button>
      </section>

      {loading && (
        <section className="statistics-message" role="status">
          Consultando evaluaciones almacenadas en AgroScan...
        </section>
      )}

      {!loading && error && (
        <section className="statistics-message statistics-message--error">
          <strong>No se pudieron cargar las estadísticas.</strong>
          <p>{error}</p>
          <button type="button" onClick={() => void loadStatistics()}>
            Reintentar consulta
          </button>
        </section>
      )}

      {!loading && !error && (
        <>
          <div className="statistics-result-info">
            <span>
              Datos correspondientes a los filtros seleccionados
            </span>
            <strong>{formatNumber(metrics.total)} evaluaciones</strong>
          </div>

          <section className="statistics-kpis">
            <article className="statistics-kpi">
              <span className="statistics-kpi__label">
                Total de evaluaciones
              </span>
              <strong>{formatNumber(metrics.total)}</strong>
              <span className="statistics-kpi__detail">
                Registros encontrados
              </span>
            </article>

            <article className="statistics-kpi statistics-kpi--green">
              <span className="statistics-kpi__label">Completadas</span>
              <strong>{formatNumber(metrics.completed)}</strong>
              <span className="statistics-kpi__detail">
                Evaluaciones finalizadas
              </span>
            </article>

            <article className="statistics-kpi statistics-kpi--blue">
              <span className="statistics-kpi__label">En proceso</span>
              <strong>{formatNumber(metrics.processing)}</strong>
              <span className="statistics-kpi__detail">
                Evaluaciones en curso
              </span>
            </article>

            <article className="statistics-kpi statistics-kpi--red">
              <span className="statistics-kpi__label">Con errores</span>
              <strong>{formatNumber(metrics.errors)}</strong>
              <span className="statistics-kpi__detail">
                Registros con error
              </span>
            </article>

            <article className="statistics-kpi statistics-kpi--orange">
              <span className="statistics-kpi__label">Por revisar</span>
              <strong>{formatNumber(metrics.pending)}</strong>
              <span className="statistics-kpi__detail">
                Pendientes de revisión
              </span>
            </article>
          </section>

          <section className="statistics-grid">

            <article className="statistics-card">
              <div className="statistics-card__heading">
                <div>
                  <h2>Cantidad de productos evaluados</h2>
                  <p>Comparación entre mango y tomate</p>
                </div>
              </div>

              <div className="product-comparison">
                <div className="product-comparison__item">
                  <div>
                    <span className="product-dot product-dot--mango" />
                    <strong>Mango</strong>
                  </div>
                  <strong>{formatNumber(metrics.mango)}</strong>
                  <div className="product-track">
                    <span
                      className="product-track__mango"
                      style={{
                        width: `${metrics.total ? metrics.mango / metrics.total * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>

                <div className="product-comparison__item">
                  <div>
                    <span className="product-dot product-dot--tomato" />
                    <strong>Tomate</strong>
                  </div>
                  <strong>{formatNumber(metrics.tomato)}</strong>
                  <div className="product-track">
                    <span
                      className="product-track__tomato"
                      style={{
                        width: `${metrics.total ? metrics.tomato / metrics.total * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </article>

            <article className="statistics-card">
              <div className="statistics-card__heading">
                <div>
                  <h2>Actividad por lote</h2>
                  <p>Cantidad de evaluaciones registradas por lote</p>
                </div>
              </div>

              {lotData.length === 0 ? (
                <p className="statistics-empty">Sin datos disponibles.</p>
              ) : (
                <div className="lot-chart">
                  {lotData.map(item => (
                    <div className="lot-chart__row" key={item.name}>
                      <span title={item.name}>{item.name}</span>
                      <div className="lot-chart__track">
                        <span
                          style={{ width: `${item.count / maxLot * 100}%` }}
                        />
                      </div>
                      <strong>{formatNumber(item.count)}</strong>
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="statistics-card statistics-card--wide">
              <div className="statistics-card__heading">
                <div>
                  <h2>Evolución de evaluaciones por fecha</h2>
                  <p>Registros diarios de las últimas 14 fechas con actividad</p>
                </div>
              </div>

              {timeline.length === 0 ? (
                <p className="statistics-empty">Sin datos disponibles.</p>
              ) : (
                <div className="timeline-chart">
                  <div className="timeline-chart__bars">
                    {timeline.map(item => (
                      <div className="timeline-chart__column" key={item.date}>
                        <strong>{item.count}</strong>
                        <div className="timeline-chart__track">
                          <span
                            style={{
                              height: `${item.count / maxDate * 100}%`,
                            }}
                          />
                        </div>
                        <span>{item.date.slice(5)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </article>

            <article className="statistics-card statistics-card--wide">
              <div className="statistics-card__heading">
                <div>
                  <h2>Distribución de resultados por producto</h2>
                  <p>
                    Estados registrados en las evaluaciones de cada producto
                  </p>
                </div>
              </div>

              {filtered.length === 0 ? (
                <p className="statistics-empty">Sin datos disponibles.</p>
              ) : (
                <>
                  <div className="distribution-legend">
                    {statusOrder.map(status => (
                      <span key={status}>
                        <i style={{ background: statusColors[status] }} />
                        {statusLabels[status]}
                      </span>
                    ))}
                  </div>

                  <div className="distribution-list">
                    {distribution.map(item => (
                      <div
                        className="distribution-row"
                        key={item.product}
                      >
                        <div className="distribution-row__heading">
                          <strong>
                            {item.product === 'mango' ? 'Mango' : 'Tomate'}
                          </strong>
                          <strong>{formatNumber(item.total)}</strong>
                        </div>

                        <div className="distribution-bar">
                          {item.statuses.map(segment => (
                            segment.count > 0 && (
                              <span
                                key={segment.status}
                                title={`${statusLabels[segment.status]}: ${segment.count}`}
                                style={{
                                  width: `${item.total ? segment.count / item.total * 100 : 0}%`,
                                  background: statusColors[segment.status],
                                }}
                              />
                            )
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </article>

          </section>

          <p className="statistics-footnote">
            Fuente: registros almacenados en la base de datos de AgroScan.
            Los indicadores representan evaluaciones, no necesariamente
            piezas únicas ni resultados de clasificación de inteligencia
            artificial.
          </p>
        </>
      )}

    </div>
  )
}
