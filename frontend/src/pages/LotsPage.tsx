import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { isValidReference, type FruitProduct, type LotDraft } from '../app/lotDraft'
import { Icon } from '../components/layout/Icon'
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

  function retryList() {
    setListState({ kind: 'loading' })
    setRevision((value) => value + 1)
  }

  return (
    <div className="page-stack lots-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de lotes</span>
        <h1>Gestión de lotes</h1>
        <p>Registra un lote o selecciona uno existente para preparar la identificación de una pieza.</p>
      </div>

      {listState.kind === 'offline' && (
        <div className="notice notice--warning" role="status">
          <Icon name="alert" size={19} />
          <span><strong>Backend no disponible:</strong> no es posible consultar ni guardar lotes. Comprueba que FastAPI esté iniciado.</span>
        </div>
      )}

      <div className="lots-grid">
        <section className="panel lots-form-panel" aria-labelledby="lots-prepare-title">
          <div className="panel-heading">
            <span className="round-icon round-icon--green"><Icon name="boxes" size={21} /></span>
            <h2 id="lots-prepare-title">Crear lote</h2>
          </div>
          <p className="lots-intro">Al pulsar «Crear lote», se enviarán los datos a la API y se guardarán en SQLite si la operación es aceptada.</p>

          <form noValidate onSubmit={saveLot} className="lots-form">
            <fieldset className="lots-fieldset" disabled={creating}>
              <legend>Producto del lote <span aria-hidden="true">*</span></legend>
              <div className="lots-product-options">
                {(['mango', 'tomate'] as const).map((product) => (
                  <button
                    type="button"
                    key={product}
                    className={`lots-product${form.product === product ? ' lots-product--selected' : ''}`}
                    aria-pressed={form.product === product}
                    onClick={() => changeForm({ ...form, product })}
                  >
                    <span aria-hidden="true">{product === 'mango' ? '🥭' : '🍅'}</span>
                    <strong>{product === 'mango' ? 'Mango' : 'Tomate'}</strong>
                  </button>
                ))}
              </div>
              {attempted && !form.product && <p role="alert" className="lots-error">Selecciona mango o tomate.</p>}
            </fieldset>

            <div className="lots-field">
              <label htmlFor="lots-reference">Referencia del lote <span aria-hidden="true">*</span></label>
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
              {attempted && !referenceValid ? (
                <p className="lots-error" id="lots-reference-error" role="alert">Usa entre 2 y 32 caracteres: letras, números, guion o guion bajo; inicia con letra o número.</p>
              ) : <p className="lots-hint" id="lots-reference-hint">La referencia debe ser única. Solo se crea cuando el servidor confirma el guardado.</p>}
            </div>

            <div className="lots-actions">
              <button className="action-button action-button--primary" type="submit" disabled={creating || listState.kind === 'offline'}>
                <Icon name="clipboard" size={18} /> {creating ? 'Guardando…' : 'Crear lote'}
              </button>
              <button className="action-button action-button--secondary" type="button" onClick={clearForm} disabled={creating}>Limpiar</button>
            </div>
            {createError && <p className="lots-error" role="alert">{createError}</p>}
          </form>

          <div className="lots-prepared" aria-live="polite" aria-atomic="true">
            {selectedLot && selectedDraft ? (
              <>
                <strong>Lote confirmado por el backend</strong>
                <p>{selectedLot.product === 'mango' ? 'Mango' : 'Tomate'} · {selectedLot.code} · ID interno: {selectedLot.id}</p>
                <span>El lote existe en la base de datos. La pantalla de Evaluación todavía requiere integrar la creación y adquisición de evaluaciones.</span>
                <Link className="action-button action-button--primary lots-continue" to="/evaluacion" state={{ lotDraft: selectedDraft }}>
                  Continuar a Evaluación <Icon name="arrow-right" size={17} />
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

        <div className="lots-side">
          <section className="panel lots-list" aria-labelledby="lots-list-title">
            <div className="panel-heading">
              <span className="round-icon round-icon--blue"><Icon name="database" size={20} /></span>
              <h2 id="lots-list-title">Lotes registrados</h2>
            <button type="button" className="action-button action-button--secondary lots-refresh" onClick={retryList} disabled={listState.kind === 'loading'}>Actualizar</button>
            </div>
            {listState.kind === 'loading' && <p role="status" className="lots-hint">Consultando lotes guardados…</p>}
            {(listState.kind === 'offline' || listState.kind === 'error') && (
              <div className="lots-unavailable" role="alert">
                <Icon name="alert" size={30} />
                <strong>No se pudo consultar el listado</strong>
                <p>{listState.message}</p>
                <button className="action-button action-button--secondary" type="button" onClick={retryList}>Reintentar</button>
              </div>
            )}
            {listState.kind === 'ready' && listState.lots.length === 0 && (
              <div className="lots-unavailable" role="status">
                <Icon name="boxes" size={30}/><strong>Sin lotes registrados</strong>
                <p>La API respondió correctamente, pero todavía no se han creado lotes.</p>
              </div>
            )}
            {listState.kind === 'ready' && listState.lots.length > 0 && (
              <ul className="lots-records" aria-label="Lotes de la base de datos">
                {listState.lots.map((lot) => (
                  <li key={lot.id} className="lots-record">
                    <div><strong>{lot.code}</strong><span>{lot.product === 'mango' ? 'Mango' : 'Tomate'} · {lot.status === 'open' ? 'Abierto' : 'Cerrado'}</span></div>
                    <button type="button" className="action-button action-button--secondary" onClick={() => selectExisting(lot)} disabled={lot.status !== 'open' || creating}>Seleccionar</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel lots-guide" aria-labelledby="lots-guide-title">
            <div className="panel-heading">
              <span className="round-icon round-icon--green"><Icon name="info" size={20} /></span>
              <h2 id="lots-guide-title">Flujo de trabajo</h2>
            </div>
            <ol>
              <li>Registrar o seleccionar un lote abierto desde la API.</li>
              <li>Elegir la pieza en Evaluación.</li>
              <li>Integrar pesaje e imágenes después de verificar los sensores.</li>
            </ol>
            <p>El registro del lote es real; la evaluación todavía no guarda datos.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
