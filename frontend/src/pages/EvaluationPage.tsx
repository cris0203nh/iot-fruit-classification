import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { readLotDraftState, type FruitProduct } from '../app/lotDraft'
import { Icon } from '../components/layout/Icon'
import { isValidPieceId } from '../features/evaluation/pieceValidation'
import {
  ApiConnectionError, ApiDataError, ApiResponseError, createEvaluation, listLots,
  type LotRecord,
} from '../services/agroscanApi'
import type { EvaluationDetail } from '../features/history/historyService'
import './EvaluationPage.css'

type Product = FruitProduct | ''
type Draft = { product: Product; lot: string; piece: string }
type LotsState =
  | { kind: 'loading' }
  | { kind: 'ready'; lots: LotRecord[] }
  | { kind: 'offline' | 'error'; message: string }

type SubmissionError = { message: string; uncertain: boolean }

const EMPTY_DRAFT: Draft = { product: '', lot: '', piece: '' }

function ProductOption({ value, selected, disabled, onSelect }: {
  value: FruitProduct
  selected: boolean
  disabled: boolean
  onSelect: (value: FruitProduct) => void
}) {
  return (
    <button
      type="button"
      className={`evaluation-product${selected ? ' evaluation-product--selected' : ''}`}
      aria-pressed={selected}
      disabled={disabled}
      onClick={() => onSelect(value)}
    >
      <span className="evaluation-product__symbol" aria-hidden="true">{value === 'mango' ? '🥭' : '🍅'}</span>
      <span className="evaluation-product__label">{value === 'mango' ? 'Mango' : 'Tomate'}</span>
      <span className="evaluation-product__hint">Evaluación externa</span>
    </button>
  )
}

export function EvaluationPage() {
  const location = useLocation()
  const [draft, setDraft] = useState<Draft>(() => {
    const lotDraft = readLotDraftState(location.state)
    return lotDraft ? { product: lotDraft.product, lot: lotDraft.lot, piece: '' } : EMPTY_DRAFT
  })
  const [lotsState, setLotsState] = useState<LotsState>({ kind: 'loading' })
  const [revision, setRevision] = useState(0)
  const [attempted, setAttempted] = useState(false)
  const [creating, setCreating] = useState(false)
  const submitting = useRef(false)
  const [created, setCreated] = useState<EvaluationDetail | null>(null)
  const [submitError, setSubmitError] = useState<SubmissionError | null>(null)

  useEffect(() => {
    let active = true
    listLots().then(
      (lots) => { if (active) setLotsState({ kind: 'ready', lots }) },
      (error: unknown) => {
        if (active) setLotsState({
          kind: error instanceof ApiConnectionError ? 'offline' : 'error',
          message: error instanceof Error ? error.message : 'No fue posible consultar los lotes.',
        })
      },
    )
    return () => { active = false }
  }, [revision])

  const openLots = lotsState.kind === 'ready' ? lotsState.lots.filter((lot) => lot.status === 'open') : []
  const availableLots = openLots.filter((lot) => lot.product === draft.product)
  const selectedLot = availableLots.find((lot) => lot.code === draft.lot) ?? null
  const pieceValid = isValidPieceId(draft.piece)
  const canCreate = selectedLot !== null && pieceValid && !creating && !created
  const locked = creating || created !== null

  function updateDraft(next: Draft) {
    if (locked) return
    setDraft(next)
    setSubmitError(null)
  }

  function refreshLots() {
    if (locked) return
    setLotsState({ kind: 'loading' })
    setRevision((value) => value + 1)
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttempted(true)
    if (!canCreate || selectedLot === null || submitting.current) return
    submitting.current = true
    setCreating(true)
    setSubmitError(null)
    try {
      const saved = await createEvaluation({ lotId: selectedLot.code, pieceId: draft.piece.trim() })
      if (saved.product !== selectedLot.product) throw new ApiDataError()
      setCreated(saved)
    } catch (error) {
      const uncertain = error instanceof ApiConnectionError || error instanceof ApiDataError
      const message = uncertain
        ? 'No se pudo confirmar si la evaluación se registró. Consulta Historial antes de volver a intentarlo para evitar duplicados.'
        : error instanceof ApiResponseError && error.status === 404
          ? 'El lote ya no existe en el backend. Actualiza el listado y selecciona otro lote.'
          : error instanceof ApiResponseError && error.status === 409
            ? 'El lote está cerrado y no permite iniciar evaluaciones. Actualiza el listado.'
            : error instanceof Error ? `No se creó la evaluación: ${error.message}` : 'No fue posible crear la evaluación.'
      setSubmitError({ message, uncertain })
    } finally {
      submitting.current = false
      setCreating(false)
    }
  }

  function clearForm() {
    if (creating) return
    setDraft(EMPTY_DRAFT)
    setAttempted(false)
    setCreated(null)
    setSubmitError(null)
  }

  return (
    <div className="page-stack evaluation-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de evaluación</span>
        <h1>Evaluación externa de frutas</h1>
        <p>Registra la identificación de una pieza en un lote existente. La adquisición de peso e imágenes se integrará posteriormente.</p>
      </div>

      <div className="notice notice--warning" role="status">
        <Icon name="alert" size={19} />
        <span><strong>Registro conectado:</strong> crear una evaluación guarda un registro real en SQLite con estado «En proceso». No implica que se haya pesado, fotografiado o clasificado la fruta.</span>
      </div>

      <div className="evaluation-grid">
        <form className="panel evaluation-form" noValidate onSubmit={handleCreate}>
          <div className="evaluation-section-heading">
            <span className="evaluation-step" aria-hidden="true">1</span>
            <div>
              <h2>Identificar y registrar la muestra</h2>
              <p>Una solicitud crea una evaluación. El backend asigna el identificador.</p>
            </div>
          </div>

          <fieldset className="evaluation-fieldset" disabled={locked}>
            <legend>Tipo de producto <span aria-hidden="true">*</span></legend>
            <div className="evaluation-products">
              <ProductOption value="mango" selected={draft.product === 'mango'} disabled={locked} onSelect={(product) => updateDraft({ ...draft, product, lot: '' })} />
              <ProductOption value="tomate" selected={draft.product === 'tomate'} disabled={locked} onSelect={(product) => updateDraft({ ...draft, product, lot: '' })} />
            </div>
            {attempted && !draft.product && <p className="evaluation-error" role="alert">Selecciona mango o tomate.</p>}
          </fieldset>

          <div className="evaluation-lot-tools">
            <span>Los lotes disponibles se obtienen de SQLite mediante FastAPI.</span>
            <button type="button" className="action-button action-button--secondary" onClick={refreshLots} disabled={locked || lotsState.kind === 'loading'}>Actualizar lotes</button>
          </div>

          {lotsState.kind === 'offline' || lotsState.kind === 'error' ? (
            <div className="evaluation-lots-feedback" role="alert">
              <strong>No se pudieron consultar los lotes.</strong>
              <p>{lotsState.message}</p>
              <button type="button" className="action-button action-button--secondary" onClick={refreshLots} disabled={locked}>Reintentar</button>
            </div>
          ) : null}

          <div className="evaluation-inputs">
            <div className="evaluation-field">
              <label htmlFor="lot-reference">Lote registrado y abierto <span aria-hidden="true">*</span></label>
              <select
                id="lot-reference"
                name="lotReference"
                value={selectedLot?.code ?? ''}
                disabled={locked || lotsState.kind !== 'ready' || !draft.product}
                aria-invalid={attempted && !selectedLot}
                aria-describedby="lot-reference-hint"
                onChange={(event) => updateDraft({ ...draft, lot: event.target.value })}
              >
                <option value="">{lotsState.kind === 'loading' ? 'Consultando lotes…' : 'Selecciona un lote abierto'}</option>
                {availableLots.map((lot) => <option key={lot.id} value={lot.code}>{lot.code}</option>)}
              </select>
              {attempted && !selectedLot && <p className="evaluation-error" role="alert">Selecciona un lote abierto confirmado por la API.</p>}
              <p id="lot-reference-hint" className="evaluation-help">
                {lotsState.kind === 'ready' && availableLots.length === 0
                  ? 'No hay lotes abiertos para este producto. Registra uno en Gestión de lotes.'
                  : 'Solo se muestran lotes abiertos recuperados de FastAPI.'}
              </p>
            </div>
            <div className="evaluation-field">
              <label htmlFor="piece-reference">Referencia de pieza <span aria-hidden="true">*</span></label>
              <input
                id="piece-reference"
                name="pieceReference"
                placeholder="Ej.: P-001"
                autoComplete="off"
                maxLength={64}
                value={draft.piece}
                disabled={locked}
                aria-invalid={attempted && !pieceValid}
                aria-describedby={attempted && !pieceValid ? 'piece-reference-error' : 'piece-reference-hint'}
                onChange={(event) => updateDraft({ ...draft, piece: event.target.value })}
              />
              {attempted && !pieceValid ? (
                <p id="piece-reference-error" className="evaluation-error" role="alert">Entre 1 y 64 caracteres: letras, números, punto, guion o guion bajo; inicia con letra o número.</p>
              ) : <p id="piece-reference-hint" className="evaluation-help">Identificador de la pieza; verifica que no se haya registrado ya para evitar evaluaciones involuntarias.</p>}
            </div>
          </div>

          <div className="evaluation-form__actions">
            <button className="action-button action-button--primary" type="submit" disabled={locked || lotsState.kind !== 'ready'}>
              <Icon name="clipboard" size={18} /> {creating ? 'Registrando…' : 'Registrar evaluación'}
            </button>
            <button className="action-button action-button--secondary" type="button" onClick={clearForm} disabled={creating}>
              {created ? 'Nueva evaluación' : 'Limpiar'}
            </button>
            <Link className="action-button action-button--secondary" to="/lotes">Ir a lotes</Link>
          </div>

          {submitError && (
            <div className="evaluation-submit-error" role="alert">
              <strong>{submitError.message}</strong>
              {submitError.uncertain && <Link className="text-link" to="/historial">Consultar Historial <Icon name="arrow-right" size={16} /></Link>}
            </div>
          )}

          <div className={`evaluation-preparation${created ? ' evaluation-preparation--confirmed' : ''}`} aria-live="polite" aria-atomic="true">
            {created ? (
              <>
                <strong>Evaluación registrada en el backend</strong>
                <p>ID: <b>{created.id}</b> · {created.product === 'mango' ? 'Mango' : 'Tomate'} · Lote: {created.lotId} · Pieza: {created.pieceId}</p>
                <p>Estado inicial: <b>En proceso</b>. La evaluación existe en SQLite, pero aún no cuenta con adquisición física ni resultado final.</p>
                <div className="evaluation-record-links">
                  <Link className="action-button action-button--primary" to={`/historial/${created.id}`}>Ver detalle <Icon name="arrow-right" size={16} /></Link>
                  <Link className="action-button action-button--secondary" to={`/trazabilidad/${created.id}`}>Ver trazabilidad</Link>
                </div>
              </>
            ) : (
              <>
                <strong>Sin evaluación iniciada</strong>
                <p>Selecciona un lote abierto, identifica la pieza y pulsa «Registrar evaluación».</p>
                <span>El registro solo se confirma cuando FastAPI devuelve su identificador real.</span>
              </>
            )}
          </div>
        </form>

        <section className="panel evaluation-acquisition" aria-labelledby="acquisition-heading">
          <div className="evaluation-section-heading">
            <span className="evaluation-step evaluation-step--muted" aria-hidden="true">2</span>
            <div>
              <h2 id="acquisition-heading">Adquisición de datos</h2>
              <p>Integración con el hardware y la cámara pendiente.</p>
            </div>
          </div>
          <div className="evaluation-acquisition__card">
            <div className="evaluation-acquisition__top"><Icon name="scale" size={21} /><strong>Pesaje ESP32</strong></div>
            <span className="evaluation-unknown">Sin lectura disponible</span>
            <p>Se requiere comunicación activa, calibración vigente y peso estable.</p>
          </div>
          <div className="evaluation-acquisition__card">
            <div className="evaluation-acquisition__top"><Icon name="camera" size={21} /><strong>Cámara RGB</strong></div>
            <div className="evaluation-camera-empty"><Icon name="camera" size={30} /><span>Sin imagen capturada</span></div>
            <p>La futura captura podrá incluir vistas adicionales de la misma pieza.</p>
          </div>
          <div className="evaluation-disabled-actions">
            <button type="button" className="action-button action-button--secondary" disabled>Capturar imagen</button>
            <button type="button" className="action-button action-button--primary" disabled>Finalizar evaluación</button>
          </div>
          <p className="evaluation-help">Acciones deshabilitadas hasta que los módulos de hardware, visión y finalización estén integrados y verificados.</p>
        </section>
      </div>

      <section className="panel evaluation-next" aria-labelledby="next-steps-heading">
        <div className="panel-heading"><span className="round-icon round-icon--green"><Icon name="info" size={20} /></span><h2 id="next-steps-heading">Siguiente etapa</h2></div>
        <p>La identificación se registra mediante FastAPI. Fernando proporcionará lecturas verificadas del ESP32 y Renzo incorporará la captura y el análisis RGB. La evaluación no se considerará completada hasta que el backend confirme el flujo de adquisición y clasificación.</p>
        <Link to="/historial" className="text-link">Ver historial de evaluaciones <Icon name="arrow-right" size={16} /></Link>
      </section>
    </div>
  )
}
