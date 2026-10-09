import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { isValidReference, type FruitProduct, type LotDraft } from '../app/lotDraft'
import { Icon } from '../components/layout/Icon'
import './LotsPage.css'

type LotForm = { product: FruitProduct | ''; lot: string }
const EMPTY_FORM: LotForm = { product: '', lot: '' }

export function LotsPage() {
  const [form, setForm] = useState<LotForm>(EMPTY_FORM)
  const [attempted, setAttempted] = useState(false)
  const [prepared, setPrepared] = useState<LotDraft | null>(null)

  const referenceValid = isValidReference(form.lot)
  const formValid = form.product !== '' && referenceValid

  function changeForm(next: LotForm) {
    setForm(next)
    setPrepared(null)
  }

  function prepareLot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttempted(true)
    if (!formValid || form.product === '') return
    // Estado transitorio: no crea lotes ni consulta el backend.
    setPrepared({ product: form.product, lot: form.lot.trim() })
  }

  function clearForm() {
    setForm(EMPTY_FORM)
    setAttempted(false)
    setPrepared(null)
  }

  return (
    <div className="page-stack lots-page">
      <div className="page-heading">
        <span className="eyebrow">Módulo de lotes</span>
        <h1>Gestión de lotes</h1>
        <p>Prepara una referencia de lote para identificar una pieza en la pantalla de Evaluación.</p>
      </div>

      <div className="notice notice--warning" role="status">
        <Icon name="alert" size={19} />
        <span><strong>Modo sin conexión:</strong> no es posible consultar, crear ni guardar lotes todavía. Las referencias preparadas aquí solo sirven para completar el formulario de Evaluación.</span>
      </div>

      <div className="lots-grid">
        <section className="panel lots-form-panel" aria-labelledby="lots-prepare-title">
          <div className="panel-heading">
            <span className="round-icon round-icon--green"><Icon name="boxes" size={21} /></span>
            <h2 id="lots-prepare-title">Preparar referencia de lote</h2>
          </div>
          <p className="lots-intro">Introduce datos provisionales para continuar a Evaluación. No se añadirá ningún lote al sistema.</p>

          <form noValidate onSubmit={prepareLot} className="lots-form">
            <fieldset className="lots-fieldset">
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
                aria-invalid={attempted && !referenceValid}
                aria-describedby={attempted && !referenceValid ? 'lots-reference-error' : 'lots-reference-hint'}
                onChange={(event) => changeForm({ ...form, lot: event.target.value })}
              />
              {attempted && !referenceValid ? (
                <p className="lots-error" id="lots-reference-error" role="alert">Usa entre 2 y 32 caracteres: letras, números, guion o guion bajo; inicia con letra o número.</p>
              ) : (
                <p className="lots-hint" id="lots-reference-hint">Referencia provisional. Su existencia no se verifica hasta integrar el backend.</p>
              )}
            </div>

            <div className="lots-actions">
              <button className="action-button action-button--primary" type="submit"><Icon name="clipboard" size={18} /> Preparar referencia</button>
              <button className="action-button action-button--secondary" type="button" onClick={clearForm}>Limpiar</button>
            </div>
          </form>

          <div className="lots-prepared" aria-live="polite" aria-atomic="true">
            {prepared ? (
              <>
                <strong>Referencia preparada localmente</strong>
                <p>{prepared.product === 'mango' ? 'Mango' : 'Tomate'} · Lote: {prepared.lot}</p>
                <span>No se creó ni guardó un lote. La referencia se transferirá al formulario de Evaluación.</span>
                <Link className="action-button action-button--primary lots-continue" to="/evaluacion" state={{ lotDraft: prepared }}>
                  Continuar a Evaluación <Icon name="arrow-right" size={17} />
                </Link>
              </>
            ) : (
              <>
                <strong>Sin referencia preparada</strong>
                <p>Selecciona el producto, escribe una referencia y pulsa «Preparar referencia».</p>
              </>
            )}
          </div>
        </section>

        <div className="lots-side">
          <section className="panel lots-list" aria-labelledby="lots-list-title">
            <div className="panel-heading">
              <span className="round-icon round-icon--blue"><Icon name="database" size={20} /></span>
              <h2 id="lots-list-title">Lotes registrados</h2>
            </div>
            <div className="lots-unavailable">
              <Icon name="boxes" size={33} />
              <strong>Listado no disponible</strong>
              <p>No hay una conexión al backend para consultar lotes. Esto no significa que no existan lotes almacenados.</p>
            </div>
          </section>
          <section className="panel lots-guide" aria-labelledby="lots-guide-title">
            <div className="panel-heading">
              <span className="round-icon round-icon--green"><Icon name="info" size={20} /></span>
              <h2 id="lots-guide-title">Flujo previsto</h2>
            </div>
            <ol>
              <li>Consultar o crear un lote real con el backend.</li>
              <li>Seleccionar el lote antes de evaluar una pieza.</li>
              <li>Asociar peso e imágenes solo tras verificar la referencia.</li>
            </ol>
            <p>Estas funciones se habilitarán con la API y persistencia de Josmely.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
