import { useEffect, useState } from 'react'
import {
  loadProtectedEvidence,
  type FruitGeometryResult,
  type FruitPrecheck,
} from '../../services/agroscanApi'
import { projectedBoundingSize } from './geometryView.ts'
import { ProtectedEvidenceImage } from '../capture/ProtectedEvidenceImage'
import { PhysicalCalibrationPanel } from './PhysicalCalibrationPanel'
import { BoardCalibrationPanel } from './BoardCalibrationPanel'
import type { PlanarMeasurement, BoardEstimate } from '../../services/agroscanApi'
import './GeometryEvidence.css'

type Visual = Pick<FruitPrecheck,
  'frameWidth' | 'frameHeight' | 'box' | 'polygon' | 'confidence' | 'product' | 'reason' | 'modelVersion'
> & { measurements?: FruitGeometryResult['measurements'] }

type Props = {
  path?: string
  previewUrl?: string
  result?: Visual | null
  alt: string
  compact?: boolean
}

/** Renderiza fotografía autenticada y superposición en el MISMO viewBox. */
export function GeometryEvidence({ path, previewUrl, result, alt, compact = false }: Props) {
  const [protectedUrl, setProtectedUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [plane, setPlane] = useState<PlanarMeasurement | null>(null)
  const [board, setBoard] = useState<BoardEstimate | null>(null)

  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    let blobUrl: string | null = null
    setProtectedUrl(null)
    setFailed(false)
    loadProtectedEvidence(path, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      blobUrl = URL.createObjectURL(blob)
      setProtectedUrl(blobUrl)
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => { controller.abort(); if (blobUrl) URL.revokeObjectURL(blobUrl) }
  }, [path])

  const url = previewUrl ?? protectedUrl
  const validFrame = Boolean(result && Number.isFinite(result.frameWidth) && result.frameWidth > 0
    && Number.isFinite(result.frameHeight) && result.frameHeight > 0)
  const showMask = validFrame && result !== null && result !== undefined && result.polygon.length >= 3
  const bounds = result?.box ? projectedBoundingSize(result.box) : null
  const metrics = result?.measurements

  return (
    <div className={`ag054 ${compact ? 'ag054--compact' : ''}`}>
      {path && failed && <p role="alert">No se pudo consultar la fotografía original.</p>}
      {path && !url && !failed && <p role="status">Cargando fotografía autenticada…</p>}
      {url && validFrame && result ? (
        <svg className="ag054__canvas" role="img" aria-label={`${alt}. Superposición de YOLOE si existe detección.`}
          viewBox={`0 0 ${result.frameWidth} ${result.frameHeight}`} xmlns="http://www.w3.org/2000/svg">
          <image href={url} x={0} y={0} width={result.frameWidth} height={result.frameHeight} />
          {showMask && <polygon points={result.polygon.map(([x, y]) => `${x},${y}`).join(' ')}
            fill="rgba(68,177,122,0.18)" stroke="#3ff1a0" strokeWidth={Math.max(2, result.frameWidth / 240)} />}
          {plane?.markerCornersPx && plane.markerCornersPx.length === 4 &&
            <polygon points={plane.markerCornersPx.map(([x, y]) => `${x},${y}`).join(' ')}
              fill="rgba(86,161,255,0.12)" stroke="#579bf0" strokeWidth={Math.max(2,result.frameWidth/270)} />}
          {board?.markerCornersPx && Object.entries(board.markerCornersPx).map(([markerId, points]) =>
            <polygon key={markerId} points={points.map(([x,y]) => `${x},${y}`).join(' ')}
              fill="rgba(71,138,236,0.12)" stroke="#428be1" strokeWidth={Math.max(2,result.frameWidth/270)} />)}
          {result.box && <rect x={result.box[0]} y={result.box[1]}
            width={Math.max(0, result.box[2] - result.box[0])}
            height={Math.max(0, result.box[3] - result.box[1])}
            fill="none" stroke="#ffdb65" strokeDasharray="9 6" strokeWidth={Math.max(2, result.frameWidth / 270)} />}
        </svg>
      ) : url ? (
        <img className="ag054__plain" src={url} alt={alt} loading="lazy" />
      ) : !path && !previewUrl ? (
        <p>No se dispone de fotografía.</p>
      ) : null}

      {result && (
        <div className="ag054__details">
          <span className="ag054__label">{result.product === 'mango' ? 'Mango' : result.product === 'tomate' ? 'Tomate' : 'Producto no confirmado'}
            {typeof result.confidence === 'number' && Number.isFinite(result.confidence)
              ? ` · Confianza ${(result.confidence * 100).toFixed(1)} %` : ''}</span>
          {metrics && <dl className="ag054__metrics">
            <div><dt>Ancho proyectado</dt><dd>{metrics.widthPx.toFixed(1)} px</dd></div>
            <div><dt>Alto proyectado</dt><dd>{metrics.heightPx.toFixed(1)} px</dd></div>
            <div><dt>Eje mayor</dt><dd>{metrics.majorAxisPx.toFixed(1)} px</dd></div>
            <div><dt>Eje menor</dt><dd>{metrics.minorAxisPx.toFixed(1)} px</dd></div>
            <div><dt>Área de máscara</dt><dd>{metrics.areaPx2.toFixed(0)} px²</dd></div>
            <div><dt>Perímetro estimado</dt><dd>{metrics.perimeterPx.toFixed(1)} px</dd></div>
          </dl>}
          {!metrics && bounds && <p>Encuadre preliminar: {bounds.widthPx.toFixed(1)} × {bounds.heightPx.toFixed(1)} px. Las medidas definitivas se registran al analizar la imagen guardada.</p>}
          {!metrics && !bounds && <p>Geometría no confirmada: {result.reason}.</p>}
          <p className="ag054__caution">Medidas proyectadas en 2D. Si existe calibración ArUco, los cm corresponden al plano del patrón; NO a dimensiones reales 3D validadas. No genera E0/E1/E2.</p>
          <small>Modelo: {result.modelVersion}</small>
          {'imageId' in result && 'evaluationId' in result &&
            typeof result.imageId === 'string' && typeof result.evaluationId === 'string' &&
            <>
            <BoardCalibrationPanel evaluationId={result.evaluationId} imageId={result.imageId} onMeasured={setBoard} />
            <PhysicalCalibrationPanel evaluationId={result.evaluationId} imageId={result.imageId}
              onMeasured={setPlane} />
            </>}
        </div>
      )}
    </div>
  )
}

/** Fotografía sin geometría: mantiene el componente autenticado existente. */
export function GeometryOrOriginal({ path, alt, result, className }: {
  path: string
  alt: string
  result?: FruitGeometryResult | null
  className?: string
}) {
  return result ? <GeometryEvidence path={path} result={result} alt={alt} compact />
    : <ProtectedEvidenceImage path={path} alt={alt} className={className} />
}
