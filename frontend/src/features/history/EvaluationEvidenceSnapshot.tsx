import { useEffect, useState } from 'react'
import { listBoardEstimates, type BoardEstimate, type QualityProposal } from '../../services/agroscanApi.ts'
import { summarizeEvidenceI04, type EvidenceI04 } from './evaluationEvidenceSnapshot.ts'
import './EvaluationEvidenceSnapshot.css'

type Props = {
  evaluationId: string
  evidence: readonly EvidenceI04[]
  proposals: readonly QualityProposal[] | null
}
type ViewState = {
  loading: boolean
  groups: BoardEstimate[][]
  unavailableImages: ReadonlySet<string>
}

/** Reutiliza la consulta V2 del panel padre; solo lee proyecciones guardadas. */
export function EvaluationEvidenceSnapshot({ evaluationId, evidence, proposals }: Props) {
  const [state, setState] = useState<ViewState>({ loading: true, groups: [], unavailableImages: new Set() })

  useEffect(() => {
    let active = true
    void Promise.allSettled(evidence.map(image => listBoardEstimates(evaluationId, image.id))).then(results => {
      if (!active) return
      const groups = results.map(result => result.status === 'fulfilled' ? result.value : [])
      const unavailableImages = new Set(evidence.filter((_, index) =>
        results[index]?.status !== 'fulfilled').map(image => image.id))
      setState({ loading: false, groups, unavailableImages })
    })
    return () => { active = false }
  }, [evaluationId, evidence])

  const snapshot = state.loading ? null : summarizeEvidenceI04(evaluationId, evidence, proposals ?? [], state.groups)
  const quality = snapshot?.quality
  return <section className="agroscan-evidence-i04" aria-label="Resultados IA y dimensiones por fotografía">
    <h4>Resultados por fotografía · solo lectura</h4>
    <p>Datos recuperados de FastAPI. No se ejecuta una inferencia nueva ni se confirma la clasificación.</p>
    {state.loading ? <p role="status">Consultando evidencia persistida…</p> : <>
      <p className="agroscan-evidence-i04__headline">
        {proposals === null ? 'No se pudo consultar la propuesta V2.' :
          quality?.status === 'suggested' && quality.grade
            ? `Calidad sugerida: ${quality.grade} · experimental`
            : quality?.status === 'needs_review' ? 'Calidad: requiere revisión humana'
              : 'Sin propuesta V2 completa para las fotos actuales'}
      </p>
      <div className="agroscan-evidence-i04__table-wrap">
        <table>
          <caption>Calidad experimental y proyección óptica nominal por vista</caption>
          <thead><tr><th scope="col">Fotografía</th><th scope="col">Calidad V2</th>
            <th scope="col">Eje mayor</th><th scope="col">Eje menor</th><th scope="col">Estado dimensional</th></tr></thead>
          <tbody>{evidence.map(image => {
            const predicted = quality?.views.find(v => v.id === image.id)
            const dimension = snapshot?.dimensions.find(row => row.imageId === image.id)
            const measured = dimension?.status === 'estimated' ? dimension.record?.measurements : null
            const dimensionState = state.unavailableImages.has(image.id) ? 'Consulta no disponible' :
              dimension?.status === 'needs_review' ? 'Revisión requerida' :
                measured ? 'Estimación nominal 2D' : 'Sin estimación registrada'
            return <tr key={image.id}>
              <th scope="row">{image.view} · {image.id}</th>
              <td>{proposals === null ? 'Sin consulta' : predicted ?
                predicted.grade ? `${predicted.grade} · preliminar` : 'No evaluable' : 'Sin propuesta'}</td>
              <td>{measured ? `≈ ${measured.majorAxisCm.toFixed(2)} cm` : '—'}</td>
              <td>{measured ? `≈ ${measured.minorAxisCm.toFixed(2)} cm` : '—'}</td>
              <td>{dimensionState}{measured && Number(measured.markerScaleVariationPct ?? 0) > 15
                ? ' · perspectiva variable' : ''}</td>
            </tr>
          })}</tbody>
        </table>
      </div>
      <p className="agroscan-evidence-i04__caution">V2 es experimental y exige revisión humana. Los centímetros son aproximaciones
        con escala nominal ArUco de 30 mm: no son dimensiones 3D validadas ni acreditan precisión.
        Las vistas no se promedian. El pesaje y la adquisición conservan sus requisitos independientes.</p>
    </>}
  </section>
}
