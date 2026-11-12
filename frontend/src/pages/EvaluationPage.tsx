import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { readLotDraftState, type FruitProduct } from '../app/lotDraft'
import { FruitMark } from '../components/FruitMark'
import { Icon, type IconName } from '../components/layout/Icon'
import { EvaluationGuidedAcquisition } from '../features/evaluation/EvaluationGuidedAcquisition'
import { AutoRegistrationPanel } from '../features/registration/AutoRegistrationPanel'
import { GUIDED_STEP_LABELS, type GuidedStep } from '../features/evaluation/evaluationFlow'
import '../features/evaluation/EvaluationProgress.css'
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

const STEP_ICONS: readonly IconName[] = ['clipboard', 'scale', 'camera', 'check', 'boxes']

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
      <span className="evaluation-product__figure"><FruitMark product={value} /></span>
      <span className="evaluation-product__text">
        <span className="evaluation-product__code" aria-hidden="true">{value === 'mango' ? 'M-01' : 'T-01'}</span>
        <span className="evaluation-product__label">{value === 'mango' ? 'Mango' : 'Tomate'}</span>
        <span className="evaluation-product__hint">Evaluación externa</span>
      </span>
      {selected && <span className="evaluation-product__check" aria-hidden="true"><Icon name="check" size={14} /></span>}
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
  const [guideStep, setGuideStep] = useState<GuidedStep>(1)
  const [manualMode, setManualMode] = useState(false)

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
  const readyToRegister = draft.product !== '' && selectedLot !== null && pieceValid
  const currentStepLabel = GUIDED_STEP_LABELS[guideStep - 1]
  const relevantLotCount = draft.product ? availableLots.length : openLots.length
  const lotAvailabilityLabel = lotsState.kind === 'loading'
    ? 'Cargando lotes registrados…'
    : lotsState.kind === 'ready'
      ? `${relevantLotCount} lote${relevantLotCount === 1 ? '' : 's'} abierto${relevantLotCount === 1 ? '' : 's'} ${draft.product ? `para ${draft.product}` : 'en total'}`
      : 'No se pudo verificar la disponibilidad de lotes'

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
    setGuideStep(1)
    setManualMode(false)
    setSubmitError(null)
  }

  return (
    <div className="evaluacion">
      <header className="evaluacion__head">
        <p className="evaluacion__kicker">Módulo de evaluación</p>
        <h1 className="evaluacion__title">Evaluación externa de frutas</h1>
        <p className="evaluacion__lede">Identifica primero la fruta con YOLOE, selecciona un lote compatible y registra una pieza con referencia automática. También está disponible el registro manual por excepción.</p>
      </header>

      <section className="evaluation-current-step" role="status" aria-live="polite">
        <span className="evaluation-current-step__counter">Etapa {guideStep} de {GUIDED_STEP_LABELS.length}</span>
        <strong>{currentStepLabel}</strong>
        <span>La etapa indica la posición en la guía, no confirma automáticamente una medición o clasificación.</span>
      </section>

      <nav className="evaluation-progress" aria-label="Pasos para evaluar una pieza">
        <ol>
          {GUIDED_STEP_LABELS.map((label, index) => {
            const number = (index + 1) as GuidedStep
            return (
              <li key={label} className={number === guideStep ? 'evaluation-progress__active' : number < guideStep ? 'evaluation-progress__passed' : ''} aria-current={number === guideStep ? 'step' : undefined} aria-label={`${label}, ${number === guideStep ? 'etapa actual' : number < guideStep ? 'etapa visitada' : 'etapa siguiente'}`}>
                <span className="evaluation-progress__number">{number}</span>
                <span className="evaluation-progress__icon" aria-hidden="true"><Icon name={STEP_ICONS[index]} size={15} /></span>
                <span className="evaluation-progress__label">{label}</span>
              </li>
            )
          })}
        </ol>
      </nav>

      <div className="evaluacion__aviso" role="status">
        <span className="evaluacion__aviso-mark" aria-hidden="true" />
        <p><strong>Qué se registra ahora:</strong> la pieza quedará registrada con estado «En proceso» únicamente cuando FastAPI confirme el registro. El pesaje, las fotografías y la clasificación se verifican por separado.</p>
      </div>

      <div className="evaluation-grid">
        {!manualMode ? (
          <AutoRegistrationPanel
            lots={openLots}
            lotsLoading={lotsState.kind === 'loading'}
            lotsError={lotsState.kind === 'error' || lotsState.kind === 'offline' ? lotsState.message : null}
            preferredLot={draft.lot}
            registered={created}
            onRefreshLots={refreshLots}
            onManual={() => setManualMode(true)}
            onRegistered={(saved) => {
              setDraft({ product: saved.product, lot: saved.lotId, piece: saved.pieceId })
              setCreated(saved)
              setGuideStep(2)
            }}
          />
        ) : (
        <form className="evaluation-form" noValidate onSubmit={handleCreate}>
          <div className="evaluation-section-heading">
            <span className="evaluation-step" aria-hidden="true">01</span>
            <div>
              <h2>Identificar y registrar la muestra</h2>
              <p>Completa los tres datos y registra una única pieza. El identificador se genera al guardar.</p>
            </div>
          </div>

          {!created && <button type="button" className="action-button action-button--secondary" onClick={() => setManualMode(false)}>Volver a identificación automática</button>}
          <fieldset className="evaluation-fieldset" disabled={locked}>
            <legend>Tipo de producto <span aria-hidden="true">*</span></legend>
            <div className="evaluation-products">
              <ProductOption value="mango" selected={draft.product === 'mango'} disabled={locked} onSelect={(product) => updateDraft({ ...draft, product, lot: '' })} />
              <ProductOption value="tomate" selected={draft.product === 'tomate'} disabled={locked} onSelect={(product) => updateDraft({ ...draft, product, lot: '' })} />
            </div>
            {attempted && !draft.product && <p className="evaluation-error" role="alert">Selecciona mango o tomate.</p>}
          </fieldset>

          <div className="evaluation-lot-tools">
            <span role="status">{lotAvailabilityLabel}</span>
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
              <div className="evaluation-field__control">
                <select
                  id="lot-reference"
                  name="lotReference"
                  value={selectedLot?.code ?? ''}
                  disabled={locked || lotsState.kind !== 'ready' || !draft.product}
                  aria-invalid={attempted && !selectedLot}
                  aria-describedby={attempted && !selectedLot ? 'lot-reference-error lot-reference-hint' : 'lot-reference-hint'}
                  onChange={(event) => updateDraft({ ...draft, lot: event.target.value })}
                >
                  <option value="">{lotsState.kind === 'loading' ? 'Consultando lotes…' : 'Selecciona un lote abierto'}</option>
                  {availableLots.map((lot) => <option key={lot.id} value={lot.code}>{lot.code}</option>)}
                </select>
                <span className="evaluation-field__caret" aria-hidden="true">▾</span>
              </div>
              {attempted && !selectedLot && <p id="lot-reference-error" className="evaluation-error" role="alert">Selecciona un lote abierto confirmado por el servidor.</p>}
              <p id="lot-reference-hint" className="evaluation-help">
                {!draft.product
                  ? 'Primero elige Mango o Tomate para consultar sus lotes.'
                  : lotsState.kind === 'ready' && availableLots.length === 0
                    ? 'Este producto no tiene lotes abiertos.'
                    : selectedLot
                      ? `Lote ${selectedLot.code} · Abierto y disponible para nuevas evaluaciones.`
                      : 'Elige un lote abierto de la lista verificada por el servidor.'}
                {draft.product && lotsState.kind === 'ready' && availableLots.length === 0 && (
                  <>{' '}<Link className="evaluation-inline-link" to="/lotes">Crear un lote <Icon name="arrow-right" size={13} /></Link></>
                )}
              </p>
            </div>
            <div className="evaluation-field">
              <label htmlFor="piece-reference">Referencia de pieza <span aria-hidden="true">*</span></label>
              <div className="evaluation-field__control">
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
              </div>
              {attempted && !pieceValid ? (
                <p id="piece-reference-error" className="evaluation-error" role="alert">Entre 1 y 64 caracteres: letras, números, punto, guion o guion bajo; inicia con letra o número.</p>
              ) : <p id="piece-reference-hint" className="evaluation-help">Identificador de la pieza; verifica que no se haya registrado ya para evitar evaluaciones involuntarias.</p>}
            </div>
          </div>

          <div className={`evaluation-readiness${readyToRegister ? ' evaluation-readiness--ready' : ''}`} aria-label="Comprobación de datos para registrar la pieza">
            <span className="evaluation-readiness__title">{created ? 'Registro confirmado' : readyToRegister ? 'Datos preparados para registrar' : 'Antes de registrar'}</span>
            <ul>
              <li className={draft.product ? 'evaluation-readiness__done' : ''}>{draft.product ? <Icon name="check" size={14} /> : <span className="evaluation-readiness__pending" aria-hidden="true" />} Producto elegido</li>
              <li className={selectedLot ? 'evaluation-readiness__done' : ''}>{selectedLot ? <Icon name="check" size={14} /> : <span className="evaluation-readiness__pending" aria-hidden="true" />} Lote abierto seleccionado</li>
              <li className={pieceValid ? 'evaluation-readiness__done' : ''}>{pieceValid ? <Icon name="check" size={14} /> : <span className="evaluation-readiness__pending" aria-hidden="true" />} Referencia de pieza válida</li>
            </ul>
            <p>Estos controles validan el formulario; el registro solo se confirma con la respuesta del servidor.</p>
          </div>

          <div className="evaluation-form__actions">
            <button className="action-button action-button--primary" type="submit" disabled={locked || lotsState.kind !== 'ready'}>
              <Icon name="clipboard" size={16} /> {creating ? 'Registrando…' : 'Registrar evaluación'}
            </button>
            <button className="action-button action-button--secondary" type="button" onClick={clearForm} disabled={creating}>
              {created ? 'Nueva evaluación' : 'Limpiar'}
            </button>
            <Link className="action-button action-button--secondary" to="/lotes">Ir a lotes</Link>
          </div>

          {submitError && (
            <div className="evaluation-submit-error" role="alert">
              <strong>{submitError.message}</strong>
              {submitError.uncertain && <Link className="text-link" to="/historial">Consultar Historial <Icon name="arrow-right" size={15} /></Link>}
            </div>
          )}

          <div className={`evaluation-preparation${created ? ' evaluation-preparation--confirmed' : ''}`} aria-live="polite" aria-atomic="true">
            {created ? (
              <>
                <strong>Evaluación registrada correctamente</strong>
                <dl className="evaluation-prep__grid">
                  <div><dt>ID</dt><dd>{created.id}</dd></div>
                  <div><dt>Producto</dt><dd>{created.product === 'mango' ? 'Mango' : 'Tomate'}</dd></div>
                  <div><dt>Lote</dt><dd>{created.lotId}</dd></div>
                  <div><dt>Pieza</dt><dd>{created.pieceId}</dd></div>
                </dl>
                <p>
                  Estado inicial: <b>En proceso</b>. La evaluación existe en SQLite.
                  Los pesos y fotografías deben asociarse a esta misma evaluación.
                  No se ha registrado clasificación.
                </p>
                <div className="evaluation-record-links">
                  <Link className="action-button action-button--primary" to={`/historial/${created.id}`}>
                    Ver detalle <Icon name="arrow-right" size={15} />
                  </Link>
                  <Link className="action-button action-button--secondary" to={`/trazabilidad/${created.id}`}>
                    Ver trazabilidad
                  </Link>
                </div>
              </>
            ) : (
              <>
                <strong>La evaluación aún no se ha creado</strong>
                <p>Completa los campos y pulsa «Registrar evaluación». No se creará ningún registro hasta que el servidor confirme la operación.</p>
              </>
            )}
          </div>
        </form>
        )}

        <EvaluationGuidedAcquisition
          key={created?.id ?? 'sin-evaluacion'}
          evaluation={created}
          onStepChange={setGuideStep}
          onNextEvaluation={clearForm}
        />
      </div>

      <section className="evaluacion__nota" aria-labelledby="next-steps-heading">
        <h2 className="evaluacion__kicker" id="next-steps-heading">Siguiente etapa</h2>
        <div className="evaluacion__nota-body">
          <span className="evaluacion__nota-icon" aria-hidden="true"><Icon name="info" size={18} /></span>
          <p>La identificación se registra mediante FastAPI. La visualización del peso ya consulta la API local, pero Fernando debe validar físicamente el HX711 y la calibración; la captura RGB inicial requiere verificación con un teléfono real y el análisis automático continúa pendiente. La evaluación no se considerará completada hasta que el backend confirme el flujo de adquisición y clasificación.</p>
        </div>
        <Link to="/historial" className="evaluacion__link">Ver historial de evaluaciones <Icon name="arrow-right" size={15} /></Link>
      </section>
    </div>
  )
}
