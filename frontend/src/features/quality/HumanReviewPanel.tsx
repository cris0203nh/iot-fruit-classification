import { useEffect, useRef, useState } from 'react'
import { getQualityReviewQueue, saveQualityHumanReview, loadProtectedEvidence, type QualityReviewQueue } from '../../services/agroscanApi'
import type { ExploratoryView } from './exploratoryPolicy'
import './quality.css'

export function HumanReviewPanel({ evaluationId, predictionId, view }: { evaluationId: string; predictionId: number; view: Pick<ExploratoryView, 'imageId' | 'roi'> }) {
  const [queue, setQueue] = useState<QualityReviewQueue | null>(null)
  const [url, setUrl] = useState('')
  const [roi, setRoi] = useState(JSON.stringify(view.roi ?? []))
  const [grade, setGrade] = useState('')
  const [rubric, setRubric] = useState('')
  const [evidence, setEvidence] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [human, setHuman] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const canvas = useRef<HTMLCanvasElement>(null)
  const image = queue?.images.find(i => i.imageId === view.imageId)
  useEffect(() => {
    let active = true; let objectUrl = ''
    getQualityReviewQueue(evaluationId).then(async q => {
      const item = q.images.find(i => i.imageId === view.imageId)
      if (!item) throw Error('Fotografía no disponible en la cola')
      const blob = await loadProtectedEvidence(item.imageUrl)
      if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); setQueue(q) }
    }).catch((e: unknown) => { if (active) setMessage(e instanceof Error ? e.message : 'No se pudo abrir la fotografía') })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [evaluationId, view.imageId])
  useEffect(() => {
    if (!url) return
    const im = new Image(); let active = true
    im.onload = () => {
      if (!active || !canvas.current) return
      try {
        const box: unknown = JSON.parse(roi)
        if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isInteger)) return
        const [x,y,w,h] = box as number[]
        if (x<0 || y<0 || w<=0 || h<=0 || x+w>im.naturalWidth || y+h>im.naturalHeight) return
        canvas.current.width = w; canvas.current.height = h
        canvas.current.getContext('2d')?.drawImage(im,x,y,w,h,0,0,w,h)
      } catch { /* El backend valida de nuevo el rango al guardar. */ }
    }
    im.src = url
    return () => { active = false }
  }, [url,roi])
  async function save() {
    if (busy) return
    setBusy(true); setMessage('')
    try {
      await saveQualityHumanReview(evaluationId, { imageId: view.imageId, predictionId, grade,
        roi: JSON.parse(roi) as number[], roiConfirmed: confirmed, humanConfirmed: human,
        rubricVersion: rubric, evidence, expectedLastEventId: image?.history.at(-1)?.eventId ?? null })
      setQueue(await getQualityReviewQueue(evaluationId)); setConfirmed(false); setHuman(false)
      setMessage('Revisión guardada como nuevo evento. Sin acreditación automática.')
    } catch (e) { setMessage(e instanceof Error ? e.message : 'No se pudo guardar la revisión') }
    finally { setBusy(false) }
  }
  return <section className="quality-review" aria-label={`Revisión humana ${view.imageId}`}>
    <h5>Revisión humana · {view.imageId} · {image?.status === 'reviewed' ? 'Revisado' : image?.status === 'declared_pending_metadata' ? 'Revisión declarada; metadatos pendientes' : 'Pendiente'}</h5>
    <p>E0: sin defecto externo relevante visible. E1: defecto visible que requiere valoración.
      E2: indicio grave que requiere revisión prioritaria. Usar la rúbrica aprobada del producto.</p>
    <div className="quality-review__photos">{url && <img src={url} alt={`Original ${view.imageId}`} />}
      <figure><canvas ref={canvas} aria-label="ROI de la fotografía" /><figcaption>ROI observada</figcaption></figure></div>
    <label>ROI x,y,ancho,alto<input aria-label="ROI x,y,ancho,alto" value={roi} onChange={e => { setRoi(e.target.value); setConfirmed(false) }} /></label>
    <label>Grado de revisión<select aria-label="Grado de revisión" value={grade} onChange={e => setGrade(e.target.value)}>
      <option value="">Seleccionar…</option><option>E0</option><option>E1</option><option>E2</option><option value="no_evaluable">No evaluable</option></select></label>
    <label>Versión de rúbrica<input aria-label="Versión de rúbrica" value={rubric} onChange={e => setRubric(e.target.value)} placeholder="tomato-ext-… / mango-ext-…" /></label>
    <label>Justificación y evidencia<textarea aria-label="Justificación y evidencia" value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="Defecto, ubicación visible y criterio Rxx para E1/E2" /></label>
    <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />He observado y confirmado la ROI</label>
    <label><input type="checkbox" checked={human} onChange={e => setHuman(e.target.checked)} />Declaro que esta revisión es humana</label>
    <button type="button" className="action-button action-button--secondary" disabled={busy || !image || !grade || !human || !confirmed} onClick={() => void save()}>
      {busy ? 'Guardando…' : image?.history.length ? 'Guardar corrección como nuevo evento' : 'Guardar revisión humana'}</button>
    {message && <p role="status">{message}</p>}
    <h5>Historial de revisión</h5><ol>{image?.history.map(event => <li key={event.eventId}>
      {event.grade} · {event.reviewer ?? 'Revisor no declarado'} · {event.reviewedAt ?? 'Fecha de revisión no declarada'} · {event.rubricVersion ?? 'Rúbrica no declarada'}
      <p>{event.evidence ?? 'Sin evidencia individual aportada'}</p>
      {event.annotationPurpose === 'human_label_declaration_import' && <small>Primera revisión humana declarada. Importación: {event.importedAt}; no es la fecha de revisión.</small>}
      <small>{event.supersedesEventId ? 'Corrección; conserva el evento anterior.' : 'Primer evento.'} Etiqueta no acreditada.</small>
    </li>)}</ol>
  </section>
}
