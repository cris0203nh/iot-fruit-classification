import { useEffect, useState } from 'react'
import {
  analyzeFruitGeometry, createApproxA4Estimate, isOperatorAuthenticated,
  listBoardEstimates, listFruitGeometries,
} from '../../services/agroscanApi.ts'
import { type Result } from './approxA4Flow.ts'
import { runAutoApproxA4 } from './autoApproxA4Runner.ts'

type Evidence = { id: string; view: string }
type Props = { evaluationId: string; evidence: readonly Evidence[] }

const reasonText: Record<string, string> = {
  board_markers_insufficient: 'No se detectaron tres marcadores ArUco completos.',
  board_marker_cropped: 'Hay marcadores recortados.',
  board_marker_deformed: 'Los marcadores aparecen demasiado deformados.',
  board_marker_duplicated: 'Hay IDs ArUco repetidos.',
  board_marker_overlaps_fruit: 'La fruta tapa algún marcador.',
  board_coverage_insufficient: 'Los marcadores no cubren ambas direcciones.',
  board_marker_scale_extreme: 'La variación de escala entre marcadores es excesiva.',
  fruit_polygon_invalid: 'El contorno YOLOE no es válido.',
  fruit_partially_out_of_frame: 'La fruta está parcialmente fuera de encuadre.',
  board_projection_invalid: 'No se pudo obtener una estimación válida.',
}

const dependencies = {
  getBoards: listBoardEstimates,
  getGeometries: listFruitGeometries,
  analyzeGeometry: analyzeFruitGeometry,
  estimate: createApproxA4Estimate,
}

/** Escala nominal por imagen, automática y separada de calibración física. */
export function ApproxA4Panel({ evaluationId, evidence }: Props) {
  const [rows, setRows] = useState<Result[]>(() => evidence.map(item =>
    ({ imageId: item.id, view: item.view, status: 'pending' })))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const operator = isOperatorAuthenticated()

  useEffect(() => {
    let current = true
    void runAutoApproxA4(evaluationId, evidence, operator, dependencies)
      .then(value => { if (current) setRows(value) })
      .catch((failure: unknown) => {
        if (current) setError(failure instanceof Error ? failure.message : 'No se pudo calcular la escala.')
      })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [evaluationId, evidence, operator])

  return <section className="capture__a4-panel" aria-label="Dimensiones aproximadas automáticas ArUco A4">
    <h4>Dimensiones aproximadas · ArUco A4</h4>
    <p>Estimación automática al guardar dos fotografías. Se usa la dimensión <strong>nominal de 30 mm</strong>
      de los marcadores detectados, sin afirmar que se haya comprobado con una regla.
      <strong> No es una medida física validada.</strong></p>
    {loading && <p role="status">Calculando automáticamente las dos vistas…</p>}
    {!loading && !operator && <p role="status">Inicia sesión como operador para generar nuevas estimaciones.
      Las estimaciones anteriores siguen disponibles.</p>}
    <ul className="capture__a4-views">
      {rows.map(row => <li key={row.imageId}>
        <strong>{row.view} · {row.imageId}</strong>
        {row.status === 'estimated' && row.record?.measurements ? <>
          <span>Eje mayor ≈ <strong>{row.record.measurements.majorAxisCm.toFixed(2)} cm</strong> ·
            eje menor ≈ <strong>{row.record.measurements.minorAxisCm.toFixed(2)} cm</strong></span>
          <small>Ancho ≈ {row.record.measurements.widthCm.toFixed(2)} cm · alto ≈ {row.record.measurements.heightCm.toFixed(2)} cm</small>
          <small>Escala nominal por {row.record.markerIds.length} marcadores. Sin verificación física de exactitud.</small>
          {Number(row.record.measurements.markerScaleVariationPct ?? 0) > 15 &&
            <small>Variación de perspectiva: la estimación puede presentar error elevado.</small>}
        </> : <span>{loading && row.status === 'pending' ? 'Calculando…' : row.status === 'pending'
          ? 'Pendiente de estimación' : row.status === 'error' ? `Error: ${row.reason}` :
            `Revisión necesaria: ${reasonText[row.reason ?? ''] ?? row.reason}`}</span>}
      </li>)}
    </ul>
    {error && <p role="alert" className="capture__error">{error}</p>}
    <p className="capture__hint">Aproximación óptica 2D sin precisión acreditada.
      No corrige profundidad de la fruta, diferencia de altura con el tablero ni distorsión de cámara.
      Las vistas no se promedian. No modifica la sugerencia E0/E1/E2, el peso ni la adquisición.</p>
  </section>
}
