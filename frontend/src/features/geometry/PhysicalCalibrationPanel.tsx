import { useEffect, useState } from 'react'
import {
  listPlanarMeasurements, createPlanarMeasurement,
  type PlanarMeasurement,
} from '../../services/agroscanApi'
import './PhysicalCalibrationPanel.css'

type Props = { evaluationId: string; imageId: string; onMeasured?: (value: PlanarMeasurement | null) => void }

const reasonLabels: Record<string, string> = {
  marker_not_found: 'No se detectó el marcador ArUco indicado en la fotografía.',
  marker_ambiguous: 'Se detectaron varios marcadores con la misma identidad.',
  marker_cropped: 'El marcador está recortado o demasiado cerca del borde.',
  marker_too_small: 'El marcador es demasiado pequeño en la imagen.',
  marker_perspective_excessive: 'El marcador está demasiado inclinado o deformado en la perspectiva.',
  marker_overlaps_fruit: 'La referencia se superpone al contorno de la fruta.',
  fruit_partially_out_of_frame: 'La fruta está parcialmente fuera del encuadre.',
  fruit_too_far_from_marker: 'La fruta está demasiado alejada del marcador para estimar una escala local.',
  invalid_projected_geometry: 'No se pudo proyectar una geometría coherente.',
}

export function PhysicalCalibrationPanel({ evaluationId, imageId, onMeasured }: Props) {
  const [sideMm, setSideMm] = useState('')
  const [samePlane, setSamePlane] = useState(false)
  const [data, setData] = useState<PlanarMeasurement[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setData([])
    setError(null)
    listPlanarMeasurements(evaluationId, imageId).then(items => {
      if (!active) return
      setData(items)
      onMeasured?.(items.at(-1) ?? null)
    }).catch(() => { if (active) setError('No se pudieron consultar las estimaciones existentes.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evaluationId, imageId]) // onMeasured es callback de presentación

  async function calculate() {
    const value = Number(sideMm)
    if (!Number.isFinite(value) || value < 15 || value > 150 || !samePlane || running) return
    setRunning(true)
    setError(null)
    try {
      const item = await createPlanarMeasurement(evaluationId, imageId, {
        markerId: 0,
        markerSideMm: value,
        markerAtPlatformLevel: true,
      })
      setData(old => [...old.filter(row => row.id !== item.id), item])
      onMeasured?.(item)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo calcular la referencia.')
    } finally { setRunning(false) }
  }
  const latest = data.at(-1)
  return <section className="ag054-plane" aria-label="Escala física ArUco">
    <h4>Escala de referencia ArUco (plano 2D)</h4>
    <p>Utiliza un marcador ArUco 4×4, ID 0, impreso al 100 % y medido con regla. Debe estar al nivel de la plataforma de pesaje, visible y separado de la fruta.</p>
    {loading && <p role="status">Buscando estimaciones guardadas…</p>}
    {latest && <div role="status">
      {latest.status === 'reference_plane_estimate' && latest.measurements ? <>
        <p><strong>Proyección en el plano del marcador:</strong></p>
        <dl className="ag054-plane__metrics">
          <div><dt>Eje mayor</dt><dd>{latest.measurements.majorAxisCm.toFixed(2)} cm</dd></div>
          <div><dt>Eje menor</dt><dd>{latest.measurements.minorAxisCm.toFixed(2)} cm</dd></div>
          <div><dt>Ancho proyectado</dt><dd>{latest.measurements.widthCm.toFixed(2)} cm</dd></div>
          <div><dt>Alto proyectado</dt><dd>{latest.measurements.heightCm.toFixed(2)} cm</dd></div>
        </dl>
      </> : <p><strong>Sin medición:</strong> {reasonLabels[latest.reason] || latest.reason}</p>}
      <p className="ag054-plane__caution">Proyección sobre plano de referencia, no tamaño físico real acreditado de la fruta. El marcador puede estar a distinta profundidad que su superficie. Sin corrección 3D ni calibración de distorsión óptica. No determina E0/E1/E2.</p>
      <small>Marcador ID {latest.markerId} · Lado declarado {latest.markerSideMm} mm · Foto {latest.imageId} · Modelo {latest.modelVersion}</small>
    </div>}
    <label className="ag054-plane__field">Lado negro exterior del marcador, medido (mm)
      <input type="number" min="15" max="150" step="0.1" value={sideMm}
        placeholder="Ej. 50" onChange={event => setSideMm(event.target.value)} />
    </label>
    <label className="ag054-plane__check">
      <input type="checkbox" checked={samePlane} onChange={event => setSamePlane(event.target.checked)} />
      Confirmo que el marcador está a la altura de la plataforma, la cámara permanece fija y medí su lado real.
    </label>
    <button type="button" className="action-button action-button--secondary"
      disabled={running || loading || !samePlane || !Number.isFinite(Number(sideMm)) || Number(sideMm) < 15 || Number(sideMm) > 150}
      onClick={() => void calculate()}>{running ? 'Calculando escala…' : 'Calcular proyección en cm'}</button>
    {error && <p role="alert">{error}</p>}
  </section>
}
