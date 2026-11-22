
import { useEffect, useState } from 'react'
import {
  listBoardEstimates,
  listFruitGeometries,
  analyzeFruitGeometry,
  createApproxA4Estimate,
  isOperatorAuthenticated,
  type BoardEstimate,
  type FruitGeometryResult,
  type QualityProposal,
} from '../../services/agroscanApi.ts'
import { runAutoApproxA4 } from '../geometry/autoApproxA4Runner.ts'
import {
  summarizeEvidenceI04,
  type EvidenceI04,
} from './evaluationEvidenceSnapshot.ts'
import './EvaluationEvidenceSnapshot.css'

export type DimensionCardRow = {
  imageId: string
  view: string
  lengthCm: number
  widthCm: number
}

type Props = {
  evaluationId: string
  evidence: readonly EvidenceI04[]
  proposals: readonly QualityProposal[] | null
  onDimensionsLoaded?: (rows: readonly DimensionCardRow[]) => void
}

type ViewState = {
  loading: boolean
  groups: BoardEstimate[][]
  unavailableImages: ReadonlySet<string>
  geometry: FruitGeometryResult[]
  geometryUnavailable: boolean
}

export function EvaluationEvidenceSnapshot({
  evaluationId,
  evidence,
  proposals,
  onDimensionsLoaded,
}: Props) {
  const [state, setState] = useState<ViewState>({
    loading: true,
    groups: [],
    unavailableImages: new Set(),
    geometry: [],
    geometryUnavailable: false,
  })

  const [revision, setRevision] = useState(0)
  const [estimating, setEstimating] = useState(false)
  const [estimateError, setEstimateError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    void Promise.all([
      Promise.allSettled(
        evidence.map(image => listBoardEstimates(evaluationId, image.id))
      ),
      Promise.allSettled([listFruitGeometries(evaluationId)]),
    ]).then(([results, [geometry]]) => {
      if (!active) return

      const groups = results.map(result =>
        result.status === 'fulfilled' ? result.value : []
      )

      const dimensions = summarizeEvidenceI04(
        evaluationId,
        evidence,
        [],
        groups
      )

      const cardRows: DimensionCardRow[] = []

      for (const image of evidence) {
        const row = dimensions.dimensions.find(
          item => item.imageId === image.id
        )

        const metrics =
          row?.status === 'estimated'
            ? row.record?.measurements
            : null

        if (!metrics) continue

        cardRows.push({
          imageId: image.id,
          view: image.view,
          lengthCm: metrics.majorAxisCm,
          widthCm: metrics.minorAxisCm,
        })
      }

      onDimensionsLoaded?.(cardRows)

      const unavailableImages = new Set(
        evidence
          .filter((_, index) => results[index]?.status !== 'fulfilled')
          .map(image => image.id)
      )

      setState({
        loading: false,
        groups,
        unavailableImages,
        geometry: geometry.status === 'fulfilled' ? geometry.value : [],
        geometryUnavailable: geometry.status === 'rejected',
      })
    })

    return () => {
      active = false
    }
  }, [evaluationId, evidence, revision, onDimensionsLoaded])

  async function calculateDimensions() {
    if (estimating) return

    setEstimating(true)
    setEstimateError(null)

    try {
      const results = await runAutoApproxA4(
        evaluationId,
        evidence,
        isOperatorAuthenticated(),
        {
          getBoards: listBoardEstimates,
          getGeometries: listFruitGeometries,
          analyzeGeometry: analyzeFruitGeometry,
          estimate: (evId, imgId) =>
            createApproxA4Estimate(evId, imgId, true),
        }
      )

      const failures = results.filter(row => row.status === 'error')

      if (failures.length > 0) {
        setEstimateError(
          failures
            .map(row =>
              `${row.imageId}: ${row.reason ?? 'Error de calibración'}`
            )
            .join('; ')
        )
      }

      setRevision(value => value + 1)
    } catch (error) {
      setEstimateError(
        error instanceof Error
          ? error.message
          : 'No se pudieron calcular las dimensiones.'
      )
    } finally {
      setEstimating(false)
    }
  }

  const snapshot = state.loading
    ? null
    : summarizeEvidenceI04(
        evaluationId,
        evidence,
        proposals ?? [],
        state.groups
      )

  const quality = snapshot?.quality

  return (
    <section
      className="agroscan-evidence-i04"
      aria-label="Calidad y dimensiones estimadas por fotografía"
    >
      <h4>Resultados por fotografía</h4>

      <p>
        Resultados registrados por AgroScan.
        La clasificación requiere revisión humana.
      </p>

      {state.loading ? (
        <p role="status">Consultando resultados…</p>
      ) : (
        <>
          <p className="agroscan-evidence-i04__headline">
            {proposals === null
              ? 'No se pudo consultar la clasificación.'
              : quality?.status === 'suggested' && quality.grade
                ? `Calidad sugerida: ${quality.grade} · preliminar`
                : quality?.status === 'needs_review'
                  ? 'Calidad: requiere revisión humana'
                  : 'Sin clasificación completa para las fotografías actuales'}
          </p>
          {isOperatorAuthenticated() && evidence.length > 0 && (
            <button
              type="button"
              onClick={() => void calculateDimensions()}
              disabled={estimating}
            >
              {estimating
                ? 'Calculando dimensiones...'
                : 'Calcular largo y ancho en cm'}
            </button>
          )}
          {estimateError && (
            <p role="alert" className="capture__error">
              {estimateError}
            </p>
          )}

          <div className="agroscan-evidence-i04__table-wrap">
            <table>
              <caption>
                Clasificación y dimensiones ópticas aproximadas por vista
              </caption>

              <thead>
                <tr>
                  <th scope="col">Fotografía</th>
                  <th scope="col">Calidad IA</th>
                  <th scope="col">Largo estimado (cm)</th>
                  <th scope="col">Ancho estimado (cm)</th>
                  <th scope="col">Estado de medición</th>
                </tr>
              </thead>

              <tbody>
                {evidence.map(image => {
                  const predicted = quality?.views.find(
                    view => view.id === image.id
                  )

                  const dimension = snapshot?.dimensions.find(
                    row => row.imageId === image.id
                  )

                  const measured =
                    dimension?.status === 'estimated'
                      ? dimension.record?.measurements
                      : null

                  const perspectiveWarning =
                    measured &&
                    Number(measured.markerScaleVariationPct ?? 0) > 15

                  const dimensionState =
                    state.unavailableImages.has(image.id)
                      ? 'Consulta no disponible'
                      : dimension?.status === 'needs_review'
                        ? 'Revisión necesaria'
                        : dimension?.status === 'error'
                          ? 'Error de estimación'
                          : measured
                            ? perspectiveWarning
                              ? 'Estimación 2D · perspectiva variable'
                              : 'Estimación 2D aproximada'
                            : 'Pendiente de estimación'

                  return (
                    <tr key={image.id}>
                      <th scope="row">
                        {image.view} · {image.id}
                      </th>

                      <td>
                        {proposals === null
                          ? 'Sin consulta'
                          : predicted
                            ? predicted.grade
                              ? `${predicted.grade} · preliminar`
                              : 'No evaluable'
                            : 'Sin propuesta'}
                      </td>

                      <td>
                        {measured
                          ? `≈ ${measured.majorAxisCm.toFixed(2)} cm`
                          : '—'}
                      </td>

                      <td>
                        {measured
                          ? `≈ ${measured.minorAxisCm.toFixed(2)} cm`
                          : '—'}
                      </td>

                      <td>{dimensionState}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <p className="agroscan-evidence-i04__caution">
            El largo y ancho son estimaciones ópticas obtenidas
            mediante marcadores ArUco A4 de 30 mm.
            No constituyen dimensiones físicas verificadas.
            La altura de la fruta, la perspectiva y la cámara
            pueden introducir errores.

            Las dos vistas se presentan por separado y no se promedian.
            La clasificación E0/E1/E2 es preliminar y requiere
            revisión humana.
          </p>
        </>
      )}
    </section>
  )
}

/**
 * Componente técnico conservado por compatibilidad.
 * No aparece en la tabla principal del operador.
 */
export function PixelGeometryCells({
  result,
  unavailable = false,
}: {
  result?: FruitGeometryResult
  unavailable?: boolean
}) {
  const metrics =
    !unavailable && result?.status === 'measured'
      ? result.measurements
      : null

  return (
    <>
      <td>
        {metrics
          ? `${metrics.majorAxisPx.toFixed(1)} px`
          : '—'}
      </td>

      <td>
        {metrics
          ? `${metrics.minorAxisPx.toFixed(1)} px`
          : '—'}
      </td>

      <td>
        {unavailable
          ? 'Consulta no disponible'
          : metrics
            ? `Área: ${metrics.areaPx2.toFixed(0)} px² · Perímetro: ${metrics.perimeterPx.toFixed(1)} px`
            : result
              ? `No evaluable: ${result.reason}`
              : 'Sin geometría registrada'}
      </td>
    </>
  )
}
