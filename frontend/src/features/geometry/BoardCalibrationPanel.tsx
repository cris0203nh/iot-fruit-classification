import { useEffect, useState } from 'react'
import {
  createBoardEstimate, listBoardEstimates, getSessionRole,
  createDimensionalComparison, listDimensionalComparisons,
  type BoardEstimate, type DimensionalComparison,
} from '../../services/agroscanApi'
import './BoardCalibrationPanel.css'

type Props = {
  evaluationId: string
  imageId: string
  onMeasured?: (measurement: BoardEstimate | null) => void
}

const explanation: Record<string, string> = {
  board_markers_insufficient: 'Se necesitan al menos tres de los cuatro marcadores del tablero, visibles y sin obstrucciones.',
  board_marker_duplicated: 'Hay marcadores duplicados; usa solamente los IDs 0, 1, 2 y 3 del tablero seleccionado.',
  board_version_unsupported: 'Versión de tablero desconocida: selecciona A4 o A3 oficial.',
  board_marker_invalid: 'Uno de los marcadores está corrupto.',
  board_marker_cropped: 'Un marcador está recortado en la fotografía.',
  board_marker_deformed: 'Los marcadores están demasiado pequeños o deformados.',
  board_marker_overlaps_fruit: 'La fruta oculta parte de un marcador; aumenta la separación o modifica el encuadre.',
  board_coverage_insufficient: 'Los marcadores detectados no cubren ambas direcciones de la plataforma.',
  board_inconsistent_markers: 'Las posiciones de los marcadores no coinciden con el diseño fijo del tablero.',
  board_reprojection_error: 'El error de reproyección supera el límite de coherencia geométrica.',
  board_homography_invalid: 'No pudo calcularse la transformación de perspectiva.',
  board_projection_invalid: 'La proyección no tiene geometría válida.',
  fruit_outside_board_area: 'El contorno sale del área espacial calibrada por el tablero.',
  fruit_partially_out_of_frame: 'Una parte de la fruta sale del encuadre de la cámara.',
  fruit_polygon_invalid: 'La segmentación de YOLOE no es válida.',
  image_invalid: 'La fotografía no tiene una resolución válida.',
}

export function BoardCalibrationPanel({ evaluationId, imageId, onMeasured }: Props) {
  const [records, setRecords] = useState<BoardEstimate[]>([])
  const [boardVersion, setBoardVersion] = useState<'ag054-board-a4-v1' | 'ag054-board-a3-v1'>('ag054-board-a4-v1')
  const [comparisons, setComparisons] = useState<DimensionalComparison[]>([])
  const [conditions, setConditions] = useState({ level: false, independent: false, print: false, fixed: false })
  const [major, setMajor] = useState('')
  const [minor, setMinor] = useState('')
  const [instrument, setInstrument] = useState('Calibrador manual')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    Promise.all([listBoardEstimates(evaluationId, imageId), listDimensionalComparisons(evaluationId, imageId)])
      .then(([calibrations, samples]) => {
        if (!active) return
        setRecords(calibrations)
        setComparisons(samples)
        onMeasured?.(calibrations.at(-1) ?? null)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Error consultando calibración del tablero.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluationId, imageId])

  const matching = records.filter(row => row.boardVersion === boardVersion)
  const selected = matching.at(-1)
  const latest = selected ?? records.at(-1)
  const role = getSessionRole()
  const canOperate = role === 'operador' || role === 'administrador'
  const ready = canOperate && Object.values(conditions).every(Boolean)
  const allowReference = selected?.status === 'reference_plane_estimate' && selected.measurements !== null
  const refMajor = Number(major)
  const refMinor = Number(minor)
  const canCompare = canOperate && allowReference && !working && refMinor > 0 && refMinor <= refMajor && refMajor <= 60 && instrument.trim().length >= 2

  async function estimate() {
    if (working || !ready) return
    setWorking(true)
    setError(null)
    try {
      const outcome = await createBoardEstimate(evaluationId, imageId, {
        boardVersion, markerAtPlatformLevel: true,
        independentSupport: true, printedDimensionsVerified: true, fixedCamera: true,
      })
      setRecords(old => [...old.filter(item => item.id !== outcome.id), outcome])
      onMeasured?.(outcome)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo registrar la calibración.')
    } finally { setWorking(false) }
  }

  async function compare() {
    if (!canCompare) return
    setWorking(true)
    setError(null)
    try {
      const sample = await createDimensionalComparison(evaluationId, imageId, {
        boardCalibrationId: selected?.id,
        referenceMajorCm: refMajor, referenceMinorCm: refMinor, instrumentId: instrument.trim(),
      })
      setComparisons(old => [...old.filter(item => item.id !== sample.id), sample])
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo registrar el contraste físico.')
    } finally { setWorking(false) }
  }

  return <section className="ag054-board" aria-label="Calibración con tablero independiente">
    <h4>AG-054 · Marco multimarcas para balanza circular</h4>
    <p>Selecciona el patrón realmente impreso. A4 compacto: cuatro marcadores ArUco 4×4 (ID 0–3) de 30 mm. A3 histórico: cuatro ArUco de 40 mm. No reduzcas una lámina A3 al tamaño A4.</p>
    {canOperate && <label>Formato de tablero
      <select value={boardVersion} onChange={event => setBoardVersion(event.target.value as typeof boardVersion)}>
        <option value="ag054-board-a4-v1">A4 horizontal · 30 mm · recomendado</option>
        <option value="ag054-board-a3-v1">A3 horizontal · 40 mm · histórico</option>
      </select>
    </label>}
    <p className="ag054-board__notice">El marco permanece independiente de la balanza WSS-5KG/HX711, a la altura de su plataforma superior. <strong>No se admite una foto del marcador sobre la mesa a otro nivel.</strong></p>
    {loading && <p role="status">Consultando referencias y comparaciones…</p>}
    {latest && <div role="status" className="ag054-board__result">
      {latest.boardVersion !== boardVersion && <small>Resultado histórico de {latest.boardVersion}. Selecciona ese formato para consultar sus contrastes.</small>}
      {latest.status === 'reference_plane_estimate' && latest.measurements ? <>
        <strong>Proyección sobre el plano de la plataforma</strong>
        <dl className="ag054-board__metrics">
          <div><dt>Eje mayor</dt><dd>{latest.measurements.majorAxisCm.toFixed(2)} cm</dd></div>
          <div><dt>Eje menor</dt><dd>{latest.measurements.minorAxisCm.toFixed(2)} cm</dd></div>
          <div><dt>Ancho proyectado</dt><dd>{latest.measurements.widthCm.toFixed(2)} cm</dd></div>
          <div><dt>Alto proyectado</dt><dd>{latest.measurements.heightCm.toFixed(2)} cm</dd></div>
        </dl>
        <small>Marcadores: {latest.markerIds.join(', ')} · Error de reproyección: {latest.rmsReprojectionMm?.toFixed(2)} mm · {latest.boardVersion}</small>
      </> : <p><strong>Estimación no disponible:</strong> {explanation[latest.reason] ?? latest.reason}</p>}
      <p className="ag054-board__notice"><strong>No es diámetro real validado.</strong> La fruta sobresale del plano de la plataforma y su altura no ha sido corregida. Este módulo no determina E0/E1/E2.</p>
    </div>}
    {!selected && !loading && canOperate && <fieldset className="ag054-board__checks">
      <legend>Verificación del montaje</legend>
      {([['print', boardVersion === 'ag054-board-a4-v1'
          ? 'Imprimí A4 al 100 %, medí cada ArUco de 30 mm y comprobé la línea de 100 mm.'
          : 'Imprimí A3 al 100 %, medí cada ArUco de 40 mm y comprobé las distancias.'],
        ['level', 'Los marcadores están en el mismo plano de referencia que la parte superior de la plataforma.'],
        ['independent', 'El marco está en soporte independiente, sin tocar el disco móvil ni la fruta.'],
        ['fixed', 'La webcam está fija y enfoca completamente el marco y la fruta.']] as const).map(([key, label]) =>
        <label key={key}><input type="checkbox" checked={conditions[key]}
          onChange={event => setConditions(old => ({ ...old, [key]: event.target.checked }))} /> {label}</label>
      )}
    </fieldset>}
    {!selected && canOperate && <button className="action-button action-button--secondary" type="button"
      disabled={loading || working || !ready} onClick={() => void estimate()}>
      {working ? 'Comprobando tablero…' : 'Calcular proyección con tablero'}</button>}
    {allowReference && selected && canOperate && <div className="ag054-board__compare">
      <h5>Contrastar con calibrador físico</h5>
      <p>Introduce el eje mayor y el menor de <strong>esta misma fruta</strong>, medidos físicamente. Se registra el error; no se corrige automáticamente el resultado de la cámara.</p>
      <div className="ag054-board__inputs">
        <label>Eje mayor real (cm)<input type="number" min="0.1" max="60" step="0.01"
          value={major} onChange={event => setMajor(event.target.value)} /></label>
        <label>Eje menor real (cm)<input type="number" min="0.1" max="60" step="0.01"
          value={minor} onChange={event => setMinor(event.target.value)} /></label>
      </div>
      <label>Instrumento utilizado<input type="text" maxLength={120} value={instrument}
        onChange={event => setInstrument(event.target.value)} /></label>
      <button className="action-button action-button--secondary" type="button"
        disabled={!canCompare} onClick={() => void compare()}>Registrar contraste dimensional</button>
      {comparisons.length > 0 && <ul className="ag054-board__comparisons">{comparisons
        .filter(sample => sample.boardCalibrationId === selected.id).map(sample =>
        <li key={sample.id}>Muestra #{sample.id} · error absoluto eje mayor: {sample.comparison.major.absoluteErrorCm.toFixed(2)} cm
          ({sample.comparison.major.relativeAbsoluteErrorPct.toFixed(2)} %) · menor: {sample.comparison.minor.absoluteErrorCm.toFixed(2)} cm · Instrumento: {sample.instrumentId}</li>)}</ul>}
    </div>}
    {error && <p role="alert" className="ag054-board__error">{error}</p>}
    <p className="ag054-board__footnote">La comparación almacena evidencia de error. La acreditación dimensional requiere un estudio de repetibilidad, varios tamaños y mediciones físicas verificadas por producto.</p>
  </section>
}
