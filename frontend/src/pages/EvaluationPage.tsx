import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { isValidReference, readLotDraftState } from '../app/lotDraft'
import { Icon } from '../components/layout/Icon'
import './EvaluationPage.css'

type Product = '' | 'mango' | 'tomate'

type Draft = {
  product: Product
  lot: string
  piece: string
}

const EMPTY_DRAFT: Draft = { product: '', lot: '', piece: '' }
function ProductOption({
  value,
  label,
  selected,
  onSelect,
}: {
  value: Exclude<Product, ''>
  label: string
  selected: boolean
  onSelect: (value: Exclude<Product, ''>) => void
}) {
  return (
    <button
      type="button"
      className={`evaluation-product${selected ? ' evaluation-product--selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(value)}
    >
      <span className="evaluation-product__symbol" aria-hidden="true">{value === 'mango' ? '🥭' : '🍅'}</span>
      <span className="evaluation-product__label">{label}</span>
      <span className="evaluation-product__hint">Evaluación externa</span>
    </button>
  )
}

export function EvaluationPage() {
  const location = useLocation()
  const [draft, setDraft] = useState<Draft>(() => {
    const lotDraft = readLotDraftState(location.state)
    return lotDraft ? { ...EMPTY_DRAFT, product: lotDraft.product, lot: lotDraft.lot } : EMPTY_DRAFT
  })
  const [attempted, setAttempted] = useState(false)
  const [prepared, setPrepared] = useState<Draft | null>(null)

  const lotValid = isValidReference(draft.lot)
  const pieceValid = isValidReference(draft.piece)
  const isValid = draft.product !== '' && lotValid && pieceValid

  function updateDraft(next: Draft) {
    setDraft(next)
    setPrepared(null)
  }

  function handlePrepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttempted(true)
    if (!isValid) return

    // Only prepares UI state. No API call, hardware acquisition or persistence.
    setPrepared({ ...draft, lot: draft.lot.trim(), piece: draft.piece.trim() })
  }

  function handleClear() {
    setDraft(EMPTY_DRAFT)
    setAttempted(false)
    setPrepared(null)
  }

  return (
    <div className="page-stack evaluation-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de evaluación</span>
        <h1>Evaluación externa de frutas</h1>
        <p>Prepara la identificación de una pieza. El pesaje, la captura y el guardado se habilitarán tras integrar los servicios reales.</p>
      </div>

      <div className="notice notice--warning" role="status">
        <Icon name="alert" size={19} />
        <span><strong>Modo de preparación:</strong> el lote y la pieza se introducen como referencias locales, sin verificar su existencia. No se capturan imágenes, no se obtienen lecturas del sensor y no se guarda ninguna evaluación.</span>
      </div>

      <div className="evaluation-grid">
        <form className="panel evaluation-form" noValidate onSubmit={handlePrepare}>
          <div className="evaluation-section-heading">
            <span className="evaluation-step" aria-hidden="true">1</span>
            <div>
              <h2>Identificar la muestra</h2>
              <p>Una sola pieza por evaluación.</p>
            </div>
          </div>

          <fieldset className="evaluation-fieldset">
            <legend>Tipo de producto <span aria-hidden="true">*</span></legend>
            <div className="evaluation-products">
              <ProductOption value="mango" label="Mango" selected={draft.product === 'mango'} onSelect={(product) => updateDraft({ ...draft, product })} />
              <ProductOption value="tomate" label="Tomate" selected={draft.product === 'tomate'} onSelect={(product) => updateDraft({ ...draft, product })} />
            </div>
            {attempted && !draft.product && <p className="evaluation-error" role="alert">Selecciona mango o tomate.</p>}
          </fieldset>

          <div className="evaluation-inputs">
            <div className="evaluation-field">
              <label htmlFor="lot-reference">Referencia de lote <span aria-hidden="true">*</span></label>
              <input
                id="lot-reference"
                name="lotReference"
                placeholder="Ej.: LOTE-001"
                autoComplete="off"
                maxLength={32}
                value={draft.lot}
                aria-invalid={attempted && !lotValid}
                aria-describedby={attempted && !lotValid ? 'lot-reference-error' : 'lot-reference-hint'}
                onChange={(event) => updateDraft({ ...draft, lot: event.target.value })}
              />
              {attempted && !lotValid ? (
                <p id="lot-reference-error" className="evaluation-error" role="alert">Utiliza entre 2 y 32 caracteres: letras, números, guion o guion bajo; comienza con letra o número.</p>
              ) : <p id="lot-reference-hint" className="evaluation-help">Referencia provisional, sin consulta al backend.</p>}
            </div>
            <div className="evaluation-field">
              <label htmlFor="piece-reference">Referencia de pieza <span aria-hidden="true">*</span></label>
              <input
                id="piece-reference"
                name="pieceReference"
                placeholder="Ej.: P-001"
                autoComplete="off"
                maxLength={32}
                value={draft.piece}
                aria-invalid={attempted && !pieceValid}
                aria-describedby={attempted && !pieceValid ? 'piece-reference-error' : 'piece-reference-hint'}
                onChange={(event) => updateDraft({ ...draft, piece: event.target.value })}
              />
              {attempted && !pieceValid ? (
                <p id="piece-reference-error" className="evaluation-error" role="alert">Utiliza entre 2 y 32 caracteres: letras, números, guion o guion bajo; comienza con letra o número.</p>
              ) : <p id="piece-reference-hint" className="evaluation-help">Identificador local de una sola fruta.</p>}
            </div>
          </div>

          <div className="evaluation-form__actions">
            <button className="action-button action-button--primary" type="submit">
              <Icon name="clipboard" size={18} /> Preparar datos
            </button>
            <button className="action-button action-button--secondary" type="button" onClick={handleClear}>Limpiar</button>
          </div>

          <div className="evaluation-preparation" aria-live="polite" aria-atomic="true">
            {prepared ? (
              <>
                <strong>Datos preparados localmente</strong>
                <p>{prepared.product === 'mango' ? 'Mango' : 'Tomate'} · Lote: {prepared.lot} · Pieza: {prepared.piece}</p>
                <span>No existe una evaluación iniciada ni guardada. La identificación deberá validarse con el backend antes de adquirir datos.</span>
              </>
            ) : (
              <>
                <strong>Sin preparación confirmada</strong>
                <p>Completa los campos y pulsa «Preparar datos». No se enviará información a ningún servicio.</p>
              </>
            )}
          </div>
        </form>

        <section className="panel evaluation-acquisition" aria-labelledby="acquisition-heading">
          <div className="evaluation-section-heading">
            <span className="evaluation-step evaluation-step--muted" aria-hidden="true">2</span>
            <div>
              <h2 id="acquisition-heading">Adquisición de datos</h2>
              <p>Funciones aún no conectadas.</p>
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
            <button type="button" className="action-button action-button--primary" disabled>Guardar evaluación</button>
          </div>
          <p className="evaluation-help">Acciones deshabilitadas hasta que los módulos de hardware, visión y almacenamiento estén integrados y verificados.</p>
        </section>
      </div>

      <section className="panel evaluation-next" aria-labelledby="next-steps-heading">
        <div className="panel-heading"><span className="round-icon round-icon--green"><Icon name="info" size={20} /></span><h2 id="next-steps-heading">Siguiente etapa</h2></div>
        <p>Josmely integrará la validación de lotes y la persistencia; Fernando proporcionará las lecturas verificadas del ESP32; Renzo incorporará la captura y el análisis RGB. La interfaz solo declarará una evaluación completada después de recibir confirmación de guardado del backend.</p>
        <Link to="/lotes" className="text-link">Ver módulo de lotes <Icon name="arrow-right" size={16} /></Link>
      </section>
    </div>
  )
}
