/** AGROP-33: estados de presentación; nunca sustituyen el estado persistido del backend. */
export type GuidedStep = 1 | 2 | 3 | 4 | 5

export const GUIDED_STEP_LABELS = [
  'Identificar pieza',
  'Colocar y pesar',
  'Capturar imágenes',
  'Confirmar adquisición',
  'Retirar pieza',
] as const

export function hasConfirmedImages(count: number): boolean {
  return Number.isInteger(count) && count > 0
}

/** "confirmed" describe únicamente las adquisiciones de peso e imagen, no una clasificación. */
export function acquisitionOutcome(input: {
  imageCount: number
  initialWeightConfirmed: boolean
  finalWeightConfirmed: boolean
}): 'without-images' | 'partial' | 'confirmed' {
  if (!hasConfirmedImages(input.imageCount)) return 'without-images'
  return input.initialWeightConfirmed && input.finalWeightConfirmed ? 'confirmed' : 'partial'
}

export type AcquisitionProcessStatus =
  | 'ready'
  | 'capturing'
  | 'processing'
  | 'pending'
  | 'error'

export type AcquisitionProcessState = {
  hasError: boolean
  processing: boolean
  confirmed: boolean
  capturing: boolean
}

export function resolveAcquisitionProcessStatus(
  state: AcquisitionProcessState,
): AcquisitionProcessStatus {
  if (state.hasError) return 'error'
  if (state.processing) return 'processing'
  if (state.confirmed) return 'pending'
  if (state.capturing) return 'capturing'
  return 'ready'
}

