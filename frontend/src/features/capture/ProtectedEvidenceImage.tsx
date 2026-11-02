import { useEffect, useState } from 'react'
import { loadProtectedEvidence } from '../../services/agroscanApi'

type Props = { path: string; alt: string; className?: string }
type ImageState = { status: 'loading' | 'error' | 'ready'; url?: string }

/** No usa <img src="/api/...">: FastAPI requiere Authorization Bearer. */
export function ProtectedEvidenceImage({ path, alt, className }: Props) {
  const [state, setState] = useState<ImageState>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    loadProtectedEvidence(path, controller.signal).then(
      (blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setState({ status: 'ready', url: objectUrl })
      },
      () => { if (!controller.signal.aborted) setState({ status: 'error' }) },
    )
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])
  if (state.status === 'error') return <span role="status">No se pudo mostrar la fotografía autenticada.</span>
  if (state.status !== 'ready' || !state.url) return <span role="status">Cargando fotografía…</span>
  return <img src={state.url} alt={alt} className={className} loading="lazy" />
}
