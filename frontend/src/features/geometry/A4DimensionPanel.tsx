import { useEffect, useState } from 'react'
import {
  analyzeFruitGeometry, createBoardEstimate, isOperatorAuthenticated,
  listBoardEstimates, listFruitGeometries,
} from '../../services/agroscanApi.ts'
import { A4_MARKER_SIDE_MM, measureA4, pendingA4, readStoredA4,
  type A4Evidence, type A4View } from './a4MeasurementFlow.ts'

type Props = { evaluationId: string; evidence: readonly A4Evidence[] }

const gateway = { analyzeFruitGeometry, createBoardEstimate, listBoardEstimates, listFruitGeometries }

const explanations: Record<string, string> = {
  board_markers_insufficient: 'No se identificaron al menos tres ArUco 0–3. Revisa enfoque, tamaño y visibilidad.',
  board_marker_deformed: 'Los marcadores son pequeños o están demasiado deformados en la foto.',
  board_marker_cropped: 'Un ArUco está cortado por el borde de la fotografía.',
  board_marker_overlaps_fruit: 'La fruta oculta un ArUco. Separa el marco de la fruta.',
  board_coverage_insufficient: 'Los marcadores visibles no cubren ambas direcciones.',
  board_inconsistent_markers: 'Los marcadores no concuerdan con el diseño físico del A4.',
  board_reprojection_error: 'La proyección geométrica no es suficientemente consistente.',
  board_homography_invalid: 'No se pudo calcular la transformación del tablero.',
  board_projection_invalid: 'No se pudo obtener una proyección coherente.',
  fruit_outside_board_area: 'La fruta excede la región cubierta por el tablero.',
  fruit_partially_out_of_frame: 'La fruta está parcialmente fuera de la fotografía.',
  fruit_polygon_invalid: 'No se dispone de un contorno de fruta válido.',
}
const fmt = (value: number) => `${value.toFixed(2)} cm`

/** Integra AG-054 A4 con las fotos persistidas, sin reformular su método físico. */
export function A4DimensionPanel({ evaluationId, evidence }: Props) {
  const [verified, setVerified] = useState(false)
  const [rows, setRows] = useState<A4View[]>(() => evidence.map(pendingA4))
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const operator = isOperatorAuthenticated()

  useEffect(() => {
    let active = true
    void readStoredA4(evaluationId, evidence, gateway)
      .then(result => { if (active) setRows(result) })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudieron recuperar las mediciones.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluationId, evidence])

  async function calculate() {
    if (!operator || !verified || loading || running) return
    setRunning(true)
    setError(null)
    try {
      setRows(await measureA4(evaluationId, evidence, verified, gateway))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo calcular A4.')
    } finally { setRunning(false) }
  }

  const projected = rows.filter(row => row.status === 'projected').length
  return <section className="capture__a4-panel" aria-label="Proyección dimensional con ArUco A4">
    <h4>Dimensiones · tablero ArUco A4</h4>
    <p>Patrón A4 horizontal: ArUco 4×4, ID 0–3, de <strong>{A4_MARKER_SIDE_MM} mm</strong> cada uno.
      La escala está definida por el diseño; no tienes que ingresar milímetros.</p>
    {loading ? <p role="status">Buscando estimaciones A4 guardadas…</p> : <>
      {projected > 0 && <p role="status">{projected} de {evidence.length} vistas con proyección A4 guardada.</p>}
      <ul className="capture__a4-views">{rows.map(row => <li key={row.imageId}>
        <strong>{row.view} · {row.imageId}</strong>
        {row.status === 'projected' && row.measurement ? <>
          <span>Eje mayor: <strong>{fmt(row.measurement.majorAxisCm)}</strong> · eje menor: <strong>{fmt(row.measurement.minorAxisCm)}</strong></span>
          <span>Ancho: {fmt(row.measurement.widthCm)} · alto: {fmt(row.measurement.heightCm)}</span>
          <small>Proyección 2D · ArUco: {row.markerIds.join(', ')} · {row.modelVersion}</small>
        </> : <span>{row.status === 'pending' ? 'Sin medición A4' :
          row.status === 'needs_review' ? `Revisión necesaria: ${explanations[row.reason || ''] ?? row.reason}` :
            `Error: ${row.reason || 'No se pudo consultar la medición.'}`}</span>}
      </li>)}</ul>
    </>}
    {operator && <>
      <label className="capture__a4-check"><input type="checkbox" checked={verified}
        disabled={loading || running} onChange={event => setVerified(event.target.checked)} />
        <span>Confirmo que <strong>medí los marcadores de 30 mm</strong> de una impresión A4 al 100 %;
          el marco tiene soporte independiente, está al nivel superior de la plataforma y la cámara permaneció fija.
          Lo verifiqué físicamente en esta evaluación.</span></label>
      <button type="button" className="action-button action-button--secondary"
        disabled={!verified || loading || running} onClick={() => void calculate()}>
        {running ? 'Calculando proyección de las vistas…' : projected === evidence.length
          ? 'Comprobar estimaciones guardadas' : 'Medir vistas con ArUco A4'}
      </button>
    </>}
    {error && <p role="alert" className="capture__error">{error}</p>}
    <p className="capture__hint">Resultado: <strong>proyección sobre el plano del tablero, NO tamaño físico real 3D acreditado</strong>.
      La fruta sobresale del plano y no se ha corregido su altura. Las vistas se muestran por separado; no se promedian.
      No cambia E0/E1/E2, el peso ni la confirmación de adquisición.</p>
  </section>
}
