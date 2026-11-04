import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { readLotDraftState, type FruitProduct } from '../app/lotDraft'
import { Icon } from '../components/layout/Icon'
import { WeightCaptureCard } from '../features/iot/WeightCaptureCard'
import { EvaluationImageCapture } from '../features/capture/EvaluationImageCapture'
import { EvaluationGuidedAcquisition } from '../features/evaluation/EvaluationGuidedAcquisition'
import { GUIDED_STEP_LABELS, type GuidedStep } from '../features/evaluation/evaluationFlow'
import '../features/evaluation/EvaluationProgress.css'
import { isValidPieceId } from '../features/evaluation/pieceValidation'
import {
  ApiConnectionError, ApiDataError, ApiResponseError, createEvaluation, listLots, confirmEvaluationAcquisition,
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
      <span className="evaluation-product__symbol" aria-hidden="true">{value === 'mango' ? 'ðŸ¥­' : 'ðŸ…'}</span>
      <span className="evaluation-product__label">{value === 'mango' ? 'Mango' : 'Tomate'}</span>
      <span className="evaluation-product__hint">EvaluaciÃ³n externa</span>
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
const [acquisitionConfirmed, setAcquisitionConfirmed] = useState(false)
const [confirmingAcquisition, setConfirmingAcquisition] = useState(false)
const [acquisitionError, setAcquisitionError] = useState<string | null>(null)

const [acquisitionResult, setAcquisitionResult] =
  useState<Awaited<ReturnType<typeof confirmEvaluationAcquisition>> | null>(null)

const [weightComplete, setWeightComplete] = useState(false)
const [savedImageCount, setSavedImageCount] = useState(0)

const [guideStep, setGuideStep] = useState<GuidedStep>(1)

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
      setGuideStep(2)
    } catch (error) {
      const uncertain = error instanceof ApiConnectionError || error instanceof ApiDataError
      const message = uncertain
        ? 'No se pudo confirmar si la evaluaciÃ³n se registrÃ³. Consulta Historial antes de volver a intentarlo para evitar duplicados.'
        : error instanceof ApiResponseError && error.status === 404
          ? 'El lote ya no existe en el backend. Actualiza el listado y selecciona otro lote.'
          : error instanceof ApiResponseError && error.status === 409
            ? 'El lote estÃ¡ cerrado y no permite iniciar evaluaciones. Actualiza el listado.'
            : error instanceof Error ? `No se creÃ³ la evaluaciÃ³n: ${error.message}` : 'No fue posible crear la evaluaciÃ³n.'
      setSubmitError({ message, uncertain })
    } finally {
      submitting.current = false
      setCreating(false)
    }
  }

  async function handleConfirmAcquisition() {
    if (!created || !weightComplete || savedImageCount < 1 || confirmingAcquisition || acquisitionConfirmed) return

    setConfirmingAcquisition(true)
    setAcquisitionError(null)

    try {
      const result = await confirmEvaluationAcquisition(created.id)
      setAcquisitionResult(result)
      setAcquisitionConfirmed(true)
    } catch (error) {
      setAcquisitionError(
        error instanceof Error
          ? error.message
          : 'No fue posible confirmar la adquisicion.'
      )
    } finally {
      setConfirmingAcquisition(false)
    }
  }

  function clearForm() {
    if (creating) return
    setDraft(EMPTY_DRAFT)
    setAttempted(false)
    setCreated(null)
    setGuideStep(1)
    setSubmitError(null)
    setAcquisitionConfirmed(false)
    setConfirmingAcquisition(false)
    setAcquisitionError(null)
    setAcquisitionResult(null)
    setWeightComplete(false)
    setSavedImageCount(0)
  }

  return (
    <div className="page-stack evaluation-page">
      <div className="page-heading">
        <span className="eyebrow">MÃ³dulo de evaluaciÃ³n</span>
        <h1>EvaluaciÃ³n externa de frutas</h1>
        <p>Registra la identificaciÃ³n de una pieza en un lote existente. El peso se consulta desde FastAPI; las fotografÃ­as pueden capturarse y vincularse a una evaluaciÃ³n en proceso. El pesaje fÃ­sico y la clasificaciÃ³n requieren validaciÃ³n independiente.</p>
      </div>

      <nav className="evaluation-progress" aria-label="Pasos para evaluar una pieza">
        <ol>
          {GUIDED_STEP_LABELS.map((label, index) => {
            const number = (index + 1) as GuidedStep
            return (
              <li key={label} className={number === guideStep ? 'evaluation-progress__active' : number < guideStep ? 'evaluation-progress__passed' : ''} aria-current={number === guideStep ? 'step' : undefined}>
                <span className="evaluation-progress__number">{number}</span>
                <span>{label}</span>
              </li>
            )
          })}
        </ol>
      </nav>

      <div className="notice notice--warning" role="status">
        <Icon name="alert" size={19} />
        <span><strong>Registro conectado:</strong> crear una evaluaciÃ³n guarda un registro real en SQLite con estado Â«En procesoÂ». No implica que se haya pesado, fotografiado o clasificado la fruta.</span>
      </div>

      <div className="evaluation-grid">
        <form className="panel evaluation-form" noValidate onSubmit={handleCreate}>
          <div className="evaluation-section-heading">
            <span className="evaluation-step" aria-hidden="true">1</span>
            <div>
              <h2>Identificar y registrar la muestra</h2>
              <p>Una solicitud crea una evaluaciÃ³n. El backend asigna el identificador.</p>
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
                <option value="">{lotsState.kind === 'loading' ? 'Consultando lotesâ€¦' : 'Selecciona un lote abierto'}</option>
                {availableLots.map((lot) => <option key={lot.id} value={lot.code}>{lot.code}</option>)}
              </select>
              {attempted && !selectedLot && <p className="evaluation-error" role="alert">Selecciona un lote abierto confirmado por la API.</p>}
              <p id="lot-reference-hint" className="evaluation-help">
                {lotsState.kind === 'ready' && availableLots.length === 0
                  ? 'No hay lotes abiertos para este producto. Registra uno en GestiÃ³n de lotes.'
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
                <p id="piece-reference-error" className="evaluation-error" role="alert">Entre 1 y 64 caracteres: letras, nÃºmeros, punto, guion o guion bajo; inicia con letra o nÃºmero.</p>
              ) : <p id="piece-reference-hint" className="evaluation-help">Identificador de la pieza; verifica que no se haya registrado ya para evitar evaluaciones involuntarias.</p>}
            </div>
          </div>

          <div className="evaluation-form__actions">
            <button className="action-button action-button--primary" type="submit" disabled={locked || lotsState.kind !== 'ready'}>
              <Icon name="clipboard" size={18} /> {creating ? 'Registrandoâ€¦' : 'Registrar evaluaciÃ³n'}
            </button>
            <button className="action-button action-button--secondary" type="button" onClick={clearForm} disabled={creating}>
              {created ? 'Nueva evaluaciÃ³n' : 'Limpiar'}
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
<div className="evaluation-preparation">
  {created ? (
    <>
      <strong>Evaluación registrada en el backend</strong>

      <p>
        ID: <b>{created.id}</b> ·
        {created.product === 'mango' ? 'Mango' : 'Tomate'} ·
        Lote: {created.lotId} ·
        Pieza: {created.pieceId}
      </p>

      <p>
        Estado inicial: <b>En proceso</b>. La evaluación existe en SQLite.
        Los pesos y fotografías deben asociarse a la misma evaluación.
        No se ha registrado clasificación.
      </p>

      <div className="evaluation-record-links">
        <Link
          className="action-button action-button--primary"
          to={`/historial/${created.id}`}
        >
          Ver detalle <Icon name="arrow-right" size={16} />
        </Link>

        <Link
          className="action-button action-button--secondary"
          to={`/trazabilidad/${created.id}`}
        >
          Ver trazabilidad
        </Link>
      </div>
    </>
  ) : (
    <>
      <strong>Sin evaluación iniciada</strong>
      <p>
        Selecciona un lote abierto, identifica la pieza y pulsa
        «Registrar evaluación».
      </p>
      <span>
        El registro solo se confirma cuando FastAPI devuelve su identificador real.
      </span>
    </>
  )}
</div>
        </form>


      </div>

      <section className="panel evaluation-next" aria-labelledby="next-steps-heading">
        <div className="panel-heading"><span className="round-icon round-icon--green"><Icon name="info" size={20} /></span><h2 id="next-steps-heading">Siguiente etapa</h2></div>
        <p>La identificaciÃ³n se registra mediante FastAPI. La visualizaciÃ³n del peso ya consulta la API local, pero Fernando debe validar fÃ­sicamente el HX711 y la calibraciÃ³n; la captura RGB inicial requiere verificaciÃ³n con un telÃ©fono real y el anÃ¡lisis automÃ¡tico continÃºa pendiente. La evaluaciÃ³n no se considerarÃ¡ completada hasta que el backend confirme el flujo de adquisiciÃ³n y clasificaciÃ³n.</p>
        <Link to="/historial" className="text-link">Ver historial de evaluaciones <Icon name="arrow-right" size={16} /></Link>
      </section>
    </div>
  )
}
