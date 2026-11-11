import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getSessionRole, getReviewDecisions, postReviewDecision, type ReviewDecisionLedger } from '../../services/agroscanApi'
import { canSubmitDecision, gradeOptions, possibleActions, type ReviewAction } from './reviewDecisionPolicy'
import type { TraceabilityRecord } from './traceabilityService'
import './ReviewDecisionPanel.css'

const ACTION_LABELS: Record<ReviewAction, string> = {
  confirm: 'Confirmar resultado vigente',
  correct: 'Corregir resultado',
  initial_label: 'Registrar primera etiqueta humana',
  no_evaluable: 'Declarar no evaluable',
}

type Props = { record: TraceabilityRecord; onUpdated: () => void }

export function ReviewDecisionPanel(props: Props) {
  // Cada revisión o evaluación tiene su propio ciclo de carga y formulario.
  // La clave reinicia el estado sin setState sincrónico dentro de useEffect.
  return <ReviewDecisionPanelContent
    key={JSON.stringify([props.record.evaluation.id, props.record.reviews.length])}
    {...props}
  />
}

function ReviewDecisionPanelContent({ record, onUpdated }: Props) {
  const evaluation = record.evaluation
  const [ledger, setLedger] = useState<ReviewDecisionLedger | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<ReviewAction>('initial_label')
  const [grade, setGrade] = useState('E0')
  const [imageId, setImageId] = useState(evaluation.evidence[0]?.id ?? '')
  const [reason, setReason] = useState('')
  // Keep the same UUID for a retry after a lost response; refresh it on edits.
  const requestKey = useRef<string | null>(null)
  const reviewer = ['revisor', 'administrador'].includes(getSessionRole() ?? '')
  const eligible = ['completed', 'pending_review'].includes(evaluation.status)

  useEffect(() => {
    let active = true
    getReviewDecisions(evaluation.id).then(value => {
      if (!active) return
      setLedger(value)
      setError(null)
      const choices = possibleActions(value.currentValue)
      setAction(choices[0])
      setGrade(value.currentValue && value.currentValue !== 'no_evaluable'
        ? value.currentValue : 'E0')
      requestKey.current = null
    }).catch(failure => {
      if (active) setError(failure instanceof Error ? failure.message : 'No se recuperó la bitácora')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluation.id, record.reviews.length])

  function edit() { requestKey.current = null; setError(null) }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!reviewer || !eligible || !ledger || busy || reason.trim().length < 10 || !imageId) return
    const newValue = action === 'no_evaluable' ? 'no_evaluable'
      : action === 'confirm' ? ledger.currentValue ?? '' : grade
    if (!canSubmitDecision(action, ledger.currentValue, newValue)) return
    setBusy(true)
    setError(null)
    if (!requestKey.current) requestKey.current = crypto.randomUUID()
    try {
      await postReviewDecision(evaluation.id, {
        action, imageId, newValue, reason: reason.trim(),
        expectedReviewId: ledger.revisionId,
        requestId: requestKey.current,
      })
      requestKey.current = null
      setReason('')
      onUpdated()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se confirmó la decisión')
    } finally { setBusy(false) }
  }
  const available = ledger ? possibleActions(ledger.currentValue) : []
  const grades = gradeOptions(ledger?.currentValue ?? null)
  const newValue = action === 'no_evaluable' ? 'no_evaluable'
    : action === 'confirm' ? ledger?.currentValue ?? '' : grade
  return (
    <section className="trace-record__section ag038-review" aria-label="AG-038: bitácora de decisiones humanas">
      <h3>AG-038 · Confirmación, corrección y bitácora</h3>
      {loading && <p role="status">Recuperando decisiones registradas…</p>}
      {error && <p role="alert" className="trace-message--error">{error}</p>}
      {ledger && <>
        <dl className="trace-data-grid">
          <div><dt>Valor original (no modificable)</dt><dd>{ledger.originalValue ?? 'Sin etiqueta inicial'}</dd></div>
          <div><dt>Valor vigente según bitácora</dt><dd>{ledger.currentValue ?? 'Sin dictamen'}</dd></div>
          <div><dt>Última revisión</dt><dd>{ledger.revisionId ?? 'Sin eventos'}</dd></div>
        </dl>
        <h4>Decisiones auditables ({ledger.decisions.length})</h4>
        {ledger.decisions.length === 0
          ? <p>No hay decisiones AG-038 todavía. Las revisiones anteriores permanecen en el historial general.</p>
          : <ol className="ag038-review__history">{ledger.decisions.map(entry => <li key={entry.id}>
              <strong>{ACTION_LABELS[entry.action]} · {entry.id}</strong>
              <p>{entry.previousValue ?? 'Sin etiqueta'} → {entry.newValue}</p>
              <p>Responsable: {entry.actorId} · Fecha: {new Date(entry.performedAt).toLocaleString('es-PE')}</p>
              <p>Motivo: {entry.reason}</p>
              <p>Evidencia: {entry.imageId} · SHA256: <code>{entry.imageSha256}</code></p>
            </li>)}</ol>}
        {reviewer && eligible && evaluation.evidence.length > 0 && <form className="ag038-review__form" onSubmit={event => void submit(event)}>
          <label htmlFor="ag038-action">Acción humana</label>
          <select id="ag038-action" value={action} disabled={busy} onChange={event => {
            edit(); setAction(event.target.value as ReviewAction)
            if (event.target.value === 'correct') {
              setGrade(grades.find(value => value !== ledger.currentValue) ?? grades[0])
            }
          }}>
            {available.map(option => <option key={option} value={option}>{ACTION_LABELS[option]}</option>)}
          </select>
          <label htmlFor="ag038-image">Fotografía inspeccionada</label>
          <select id="ag038-image" value={imageId} disabled={busy} onChange={event => { edit(); setImageId(event.target.value) }}>
            {evaluation.evidence.map(image => <option key={image.id} value={image.id}>{image.view} · {image.id}</option>)}
          </select>
          {action !== 'no_evaluable' && <>
            <label htmlFor="ag038-grade">Resultado {action === 'confirm' ? 'que se confirma' : 'propuesto'}</label>
            <select id="ag038-grade" value={action === 'confirm' ? ledger.currentValue ?? '' : grade}
              disabled={busy || action === 'confirm'}
              onChange={event => { edit(); setGrade(event.target.value) }}>
              {action === 'confirm' && ledger.currentValue === 'no_evaluable'
                ? <option value="no_evaluable">No evaluable</option>
                : grades.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </>}
          <label htmlFor="ag038-reason">Justificación (mínimo 10 caracteres)</label>
          <textarea id="ag038-reason" value={reason} maxLength={500} rows={3}
            onChange={event => { edit(); setReason(event.target.value) }} disabled={busy}
            placeholder="Describa qué observa en la fotografía y por qué confirma o corrige" />
          <p>La fotografía y el valor original se mantienen. El servidor registra el usuario y la fecha.</p>
          <button type="submit" className="action-button action-button--primary"
            disabled={busy || reason.trim().length < 10 || !canSubmitDecision(action, ledger.currentValue, newValue)}>
            {busy ? 'Registrando…' : 'Guardar decisión y evidencia'}
          </button>
        </form>}
        {!reviewer && <p>Solo el rol revisor o administrador puede registrar decisiones.</p>}
      </>}
    </section>
  )
}
