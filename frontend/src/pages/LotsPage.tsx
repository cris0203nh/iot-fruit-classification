import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { isValidReference, type FruitProduct, type LotDraft } from '../app/lotDraft'
import { FruitMark } from '../components/FruitMark'
import { Icon } from '../components/layout/Icon'
import { filterVisibleLots, type LotStatusFilter } from '../features/lots/lotListView'
import { ApiConnectionError, ApiResponseError, createLot, listLots, type LotRecord } from '../services/agroscanApi'
import './LotsPage.css'

type LotForm = { product: FruitProduct | ''; lot: string }
type ListState = { kind: 'loading' } | { kind: 'ready'; lots: LotRecord[] } | { kind: 'offline' | 'error'; message: string }
const EMPTY_FORM: LotForm = { product: '', lot: '' }

export function LotsPage() {
  const [form, setForm] = useState<LotForm>(EMPTY_FORM)
  const [attempted, setAttempted] = useState(false)
  const [selectedLot, setSelectedLot] = useState<LotRecord | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [listState, setListState] = useState<ListState>({ kind: 'loading' })
  const [revision, setRevision] = useState(0)
  const [lotSearch, setLotSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<LotStatusFilter>('all')

  useEffect(() => {
    let active = true
    listLots().then(
      (lots) => { if (active) setListState({ kind: 'ready', lots }) },
      (error: unknown) => {
        if (active) setListState({
          kind: error instanceof ApiConnectionError ? 'offline' : 'error',
          message: error instanceof Error ? error.message : 'Error desconocido al consultar lotes.',
        })
      },
    )
    return () => { active = false }
  }, [revision])

  const referenceValid = isValidReference(form.lot)
  const formValid = form.product !== '' && referenceValid
  const selectedDraft: LotDraft | null = selectedLot ? { product: selectedLot.product, lot: selectedLot.code } : null
  const listedLots = listState.kind === 'ready' ? listState.lots : []
  const openCount = listedLots.filter((lot) => lot.status === 'open').length
  const closedCount = listedLots.length - openCount
  const visibleLots = filterVisibleLots(listedLots, lotSearch, statusFilter)

  function changeForm(next: LotForm) {
    setForm(next)
    setSelectedLot(null)
    setCreateError('')
  }

  async function saveLot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttempted(true)
    if (!formValid || form.product === '' || creating) return
    setCreating(true)
    setCreateError('')
    setSelectedLot(null)
    try {
      const saved = await createLot({ code: form.lot.trim(), product: form.product })
      setSelectedLot(saved)
      setRevision((value) => value + 1)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'No fue posible guardar el lote.'
      setCreateError(error instanceof ApiResponseError && error.status === 409
        ? `No se creó el lote: ${message} Selecciona el existente en la lista.`
        : `No se creó el lote: ${message}`)
    } finally {
      setCreating(false)
    }
  }

  function clearForm() {
    setForm(EMPTY_FORM)
    setAttempted(false)
    setSelectedLot(null)
    setCreateError('')
  }

  function selectExisting(lot: LotRecord) {
    setForm({ product: lot.product, lot: lot.code })
    setSelectedLot(lot)
    setAttempted(false)
    setCreateError('')
  }

  function resetFilters() {
    setLotSearch('')
    setStatusFilter('all')
  }

  function retryList() {
    setListState({ kind: 'loading' })
    setRevision((value) => value + 1)
  }

  return (
    <div className="lotes">
      <header className="lotes__head">
        <p className="lotes__kicker">Módulo de lotes</p>
        <h1 className="lotes__title">Gestión de lotes</h1>
        <p className="lotes__lede">Crea un lote o elige uno abierto que ya esté registrado. Después podrás continuar con la evaluación de una pieza.</p>
      </header>

      {listState.kind === 'offline' && (
        <div className="lotes__aviso" role="status">
          <span className="lotes__aviso-icon" aria-hidden="true"><Icon name="alert" size={17} /></span>
          <p><strong>Backend no disponible:</strong> no es posible consultar ni guardar lotes. Comprueba que FastAPI esté iniciado.</p>
        </div>
      )}

      <div className="lotes__grid">
        <section className="lotes__panel" aria-labelledby="lots-prepare-title">
          <div className="lotes__panel-head">
            <span className="lotes__panel-icon" aria-hidden="true"><Icon name="boxes" size={18} /></span>
            <div>
              <h2 id="lots-prepare-title">Crear lote</h2>
              <p>Elige el producto y asigna un código único. Solo se confirmará la creación cuando responda el servidor.</p>
            </div>
          </div>

          <form noValidate onSubmit={saveLot} className="lotes__form">
            <fieldset className="lotes__fieldset" disabled={creating}>
              <legend>Producto del lote <span aria-hidden="true">*</span></legend>
              <div className="lotes__productos">
                {(['mango', 'tomate'] as const).map((product) => {
                  const selected = form.product === product
                  return (
                    <button
                      type="button"
                      key={product}
                      className={`lotes__producto${selected ? ' lotes__producto--selected' : ''}`}
                      aria-pressed={selected}
                      onClick={() => changeForm({ ...form, product })}
                    >
                      <span className="lotes__producto-fig"><FruitMark product={product} size={48} /></span>
                      <span className="lotes__producto-text">
                        <span className="lotes__producto-code" aria-hidden="true">{product === 'mango' ? 'M-01' : 'T-01'}</span>
                        <strong>{product === 'mango' ? 'Mango' : 'Tomate'}</strong>
                      </span>
                      {selected && <span className="lotes__producto-check" aria-hidden="true"><Icon name="check" size={14} /></span>}
                    </button>
                  )
                })}
              </div>
              {attempted && !form.product && <p role="alert" className="lotes__error">Selecciona mango o tomate.</p>}
            </fieldset>

            <div className="lotes__field">
              <label htmlFor="lots-reference">Referencia del lote <span aria-hidden="true">*</span></label>
              <div className="lotes__control">
                <input
                  id="lots-reference"
                  name="lotReference"
                  autoComplete="off"
                  maxLength={32}
                  placeholder="Ej.: LOTE-001"
                  value={form.lot}
                  disabled={creating}
                  aria-invalid={attempted && !referenceValid}
                  aria-describedby={attempted && !referenceValid ? 'lots-reference-error' : 'lots-reference-hint'}
                  onChange={(event) => changeForm({ ...form, lot: event.target.value })}
                />
              </div>
              {attempted && !referenceValid ? (
                <p className="lotes__error" id="lots-reference-error" role="alert">Usa entre 2 y 32 caracteres: letras, números, guion o guion bajo; inicia con letra o número.</p>
              ) : <p className="lotes__hint" id="lots-reference-hint">La referencia debe ser única. Solo se crea cuando el servidor confirma el guardado.</p>}
            </div>

            <div className="lotes__actions">
              <button className="action-button action-button--primary" type="submit" disabled={creating || listState.kind === 'offline'}>
                <Icon name="clipboard" size={16} /> {creating ? 'Guardando…' : 'Crear lote'}
              </button>
              <button className="action-button action-button--secondary" type="button" onClick={clearForm} disabled={creating}>Limpiar</button>
            </div>
            {createError && <p className="lotes__error" role="alert">{createError}</p>}
          </form>

          <div className={`lotes__preparado${selectedLot ? ' lotes__preparado--confirmado' : ''}`} aria-live="polite" aria-atomic="true">
            {selectedLot && selectedDraft ? (
              <>
                <strong>Lote abierto seleccionado</strong>
                <dl className="lotes__datos">
                  <div><dt>Producto</dt><dd>{selectedLot.product === 'mango' ? 'Mango' : 'Tomate'}</dd></div>
                  <div><dt>Código</dt><dd>{selectedLot.code}</dd></div>
                  <div><dt>ID interno</dt><dd>{selectedLot.id}</dd></div>
                </dl>
                <p>El servidor confirmó este lote. Puedes continuar con la identificación de una pieza. El pesaje y las fotografías se registran y validan por separado.</p>
                <Link className="action-button action-button--primary lotes__continuar" to="/evaluacion" state={{ lotDraft: selectedDraft }}>
                  Continuar a Evaluación <Icon name="arrow-right" size={15} />
                </Link>
              </>
            ) : (
              <>
                <strong>Sin lote seleccionado</strong>
                <p>Crea uno nuevo o selecciona un lote abierto del listado.</p>
              </>
            )}
          </div>
        </section>

        <div className="lotes__side">
          <section className="lotes__panel" aria-labelledby="lots-list-title">
            <div className="lotes__panel-head">
              <span className="lotes__panel-icon" aria-hidden="true"><Icon name="database" size={18} /></span>
              <div className="lotes__list-heading">
                <h2 id="lots-list-title">Lotes registrados</h2>
                {listState.kind === 'ready' && <p role="status">{openCount} abiertos · {closedCount} cerrados</p>}
              </div>
              <button type="button" className="action-button action-button--secondary lotes__refresh" onClick={retryList} disabled={listState.kind === 'loading'}>Actualizar</button>
            </div>

            {listState.kind === 'ready' && listState.lots.length > 0 && (
              <div className="lotes__filters" role="search" aria-label="Filtrar los lotes registrados">
                <div className="lotes__filter-field">
                  <label htmlFor="lots-search">Buscar por código</label>
                  <input id="lots-search" type="search" placeholder="Ej.: LOTE-001" value={lotSearch} onChange={(event) => setLotSearch(event.target.value)} />
                </div>
                <div className="lotes__filter-field">
                  <label htmlFor="lots-status-filter">Estado</label>
                  <select id="lots-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as LotStatusFilter)}>
                    <option value="all">Todos</option>
                    <option value="open">Abiertos</option>
                    <option value="closed">Cerrados</option>
                  </select>
                </div>
              </div>
            )}

            {listState.kind === 'loading' && <p role="status" className="lotes__hint">Consultando lotes guardados…</p>}

            {(listState.kind === 'offline' || listState.kind === 'error') && (
              <div className="lotes__vacio" role="alert">
                <span className="lotes__vacio-icon" aria-hidden="true"><Icon name="alert" size={20} /></span>
                <strong>No se pudo consultar el listado</strong>
                <p>{listState.message}</p>
                <button className="action-button action-button--secondary" type="button" onClick={retryList}>Reintentar</button>
              </div>
            )}

            {listState.kind === 'ready' && listState.lots.length === 0 && (
              <div className="lotes__vacio" role="status">
                <span className="lotes__vacio-icon" aria-hidden="true"><Icon name="boxes" size={20} /></span>
                <strong>Sin lotes registrados</strong>
                <p>La API respondió correctamente, pero todavía no se han creado lotes.</p>
              </div>
            )}

            {listState.kind === 'ready' && listState.lots.length > 0 && visibleLots.length === 0 && (
              <div className="lotes__vacio" role="status">
                <span className="lotes__vacio-icon" aria-hidden="true"><Icon name="search" size={20} /></span>
                <strong>No hay coincidencias</strong>
                <p>Hay lotes registrados, pero ninguno coincide con estos filtros.</p>
                <button className="action-button action-button--secondary" type="button" onClick={resetFilters}>Limpiar filtros</button>
              </div>
            )}

            {listState.kind === 'ready' && visibleLots.length > 0 && (
              <>
                <p className="lotes__results-count" role="status">Mostrando {visibleLots.length} de {listState.lots.length} lotes</p>
                <ul className="lotes__registros" aria-label="Lotes de la base de datos">
                  {visibleLots.map((lot) => (
                    <li key={lot.id} className={`lotes__registro${selectedLot?.id === lot.id ? ' lotes__registro--selected' : ''}`}>
                      <div className="lotes__registro-info">
                        <strong>{lot.code}</strong>
                        <span>
                          {lot.product === 'mango' ? 'Mango' : 'Tomate'} ·{' '}
                          <span className={`lotes__estado lotes__estado--${lot.status}`}>{lot.status === 'open' ? 'Abierto' : 'Cerrado'}</span>
                        </span>
                      </div>
                      <button type="button" className="action-button action-button--secondary" aria-pressed={selectedLot?.id === lot.id} onClick={() => selectExisting(lot)} disabled={lot.status !== 'open' || creating}>{selectedLot?.id === lot.id ? 'Seleccionado' : lot.status === 'open' ? 'Seleccionar' : 'No disponible'}</button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <section className="lotes__panel lotes__guia" aria-labelledby="lots-guide-title">
            <div className="lotes__panel-head">
              <span className="lotes__panel-icon" aria-hidden="true"><Icon name="info" size={18} /></span>
              <h2 id="lots-guide-title">Flujo de trabajo</h2>
            </div>
            <ol className="lotes__flujo">
              <li><span className="lotes__num" aria-hidden="true">01</span><span>Registrar o seleccionar un lote abierto desde la API.</span></li>
              <li><span className="lotes__num" aria-hidden="true">02</span><span>Elegir la pieza en Evaluación.</span></li>
              <li><span className="lotes__num" aria-hidden="true">03</span><span>Integrar pesaje e imágenes después de verificar los sensores.</span></li>
            </ol>
            <p className="lotes__guia-nota">El registro de lotes se confirma mediante FastAPI. La disponibilidad de pesaje, imágenes y clasificación depende de las integraciones que se hayan verificado.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
