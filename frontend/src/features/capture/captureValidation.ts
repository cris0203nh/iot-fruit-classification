
/** AGROP-28: validación técnica y visual de capturas RGB. */

export const MAX_CAPTURE_BYTES = 5 * 1024 * 1024

const MAX_SIDE = 512
const BLUR_THRESHOLD = 12
const MIN_COMPONENT_FRACTION = 0.025

export type CaptureQualityStatus = 'valid' | 'invalid' | 'review'

export interface CaptureQualityResult {
  status: CaptureQualityStatus
  issues: string[]
  metrics: {
    width: number
    height: number
    laplacianVariance: number | null
    meanBrightness: number | null
    foregroundCount: number | null
  }
}

export function captureFileError(
  file: Pick<File, 'size' | 'type'>
): string | null {
  if (file.type !== 'image/jpeg' && file.type !== 'image/png') {
    return 'Selecciona una fotografía JPG o PNG.'
  }

  if (file.size <= 0) {
    return 'La fotografía está vacía.'
  }

  if (file.size > MAX_CAPTURE_BYTES) {
    return 'La fotografía supera el máximo de 5 MB.'
  }

  return null
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length / 2)]
}

/**
 * Estimación experimental del fondo.
 * Si la fruta está sostenida con la mano o el fondo
 * no es uniforme, devuelve null.
 */
function estimateBackground(
  pixels: Uint8ClampedArray,
  width: number,
  height: number
): number[] | null {
  const cw = Math.max(2, Math.floor(width / 12))
  const ch = Math.max(2, Math.floor(height / 12))

  const samples: number[][] = []

  for (const [x0, y0] of [
    [0, 0],
    [width - cw, 0],
    [0, height - ch],
    [width - cw, height - ch],
  ]) {
    for (let y = y0; y < y0 + ch; y += 2) {
      for (let x = x0; x < x0 + cw; x += 2) {
        const i = (y * width + x) * 4

        const rgb = [
          pixels[i],
          pixels[i + 1],
          pixels[i + 2],
        ]

        if (Math.max(...rgb) - Math.min(...rgb) <= 28) {
          samples.push(rgb)
        }
      }
    }
  }

  const expected =
    4 * Math.ceil(cw / 2) * Math.ceil(ch / 2)

  if (samples.length / expected < 0.85) {
    return null
  }

  const background = [0, 1, 2].map(channel =>
    median(samples.map(p => p[channel]))
  )

  for (let channel = 0; channel < 3; channel++) {
    const mean =
      samples.reduce((sum, p) => sum + p[channel], 0) /
      samples.length

    const deviation = Math.sqrt(
      samples.reduce(
        (sum, p) => sum + (p[channel] - mean) ** 2,
        0
      ) / samples.length
    )

    if (deviation > 42) {
      return null
    }
  }

  return background
}

interface Component {
  area: number
  touchesBorder: boolean
}

/**
 * Segmentación experimental de regiones cromáticas.
 * No equivale a un detector de frutas entrenado.
 */
function findComponents(
  mask: Uint8Array,
  width: number,
  height: number
): Component[] {
  const visited = new Uint8Array(mask.length)
  const queue = new Int32Array(mask.length)

  const minimum = Math.max(
    48,
    Math.ceil(mask.length * MIN_COMPONENT_FRACTION)
  )

  const components: Component[] = []

  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || visited[start]) continue

    let head = 0
    let tail = 0
    let area = 0

    let x0 = width
    let y0 = height
    let x1 = 0
    let y1 = 0

    queue[tail++] = start
    visited[start] = 1

    while (head < tail) {
      const index = queue[head++]

      const x = index % width
      const y = Math.floor(index / width)

      area++

      x0 = Math.min(x0, x)
      y0 = Math.min(y0, y)
      x1 = Math.max(x1, x)
      y1 = Math.max(y1, y)

      const neighbors = [
        x > 0 ? index - 1 : -1,
        x < width - 1 ? index + 1 : -1,
        y > 0 ? index - width : -1,
        y < height - 1 ? index + width : -1,
      ]

      for (const next of neighbors) {
        if (
          next >= 0 &&
          mask[next] &&
          !visited[next]
        ) {
          visited[next] = 1
          queue[tail++] = next
        }
      }
    }

    if (area >= minimum) {
      components.push({
        area,
        touchesBorder:
          x0 <= 1 ||
          y0 <= 1 ||
          x1 >= width - 2 ||
          y1 >= height - 2,
      })
    }
  }

  return components
}

export async function analyzeCaptureQuality(
  file: File
): Promise<CaptureQualityResult> {
  const issues: string[] = []

  const fallback = (): CaptureQualityResult => ({
    status: 'review',
    issues: [
      'No se pudo analizar automáticamente la imagen. Requiere revisión visual.',
    ],
    metrics: {
      width: 0,
      height: 0,
      laplacianVariance: null,
      meanBrightness: null,
      foregroundCount: null,
    },
  })

  let bitmap: ImageBitmap | null = null

  try {
    bitmap = await createImageBitmap(file)

    const scale = Math.min(
      1,
      MAX_SIDE / Math.max(bitmap.width, bitmap.height)
    )

    const width = Math.max(1, Math.round(bitmap.width * scale))
    const height = Math.max(1, Math.round(bitmap.height * scale))

    const canvas = document.createElement('canvas')

    canvas.width = width
    canvas.height = height

    const context = canvas.getContext('2d', {
      willReadFrequently: true,
    })

    if (!context) {
      return fallback()
    }

    context.drawImage(bitmap, 0, 0, width, height)

    const pixels = context.getImageData(
      0,
      0,
      width,
      height
    ).data

    const total = width * height
    const gray = new Float32Array(total)

    // 1. Conversión RGB a escala de grises.
    for (let i = 0; i < total; i++) {
      const p = i * 4

      gray[i] =
        0.299 * pixels[p] +
        0.587 * pixels[p + 1] +
        0.114 * pixels[p + 2]
    }

    // 2. Estimación experimental del fondo.
    const background = estimateBackground(
      pixels,
      width,
      height
    )

    let mask: Uint8Array | null = null
    let components: Component[] = []

    if (background !== null) {
      mask = new Uint8Array(total)

      for (let i = 0; i < total; i++) {
        const p = i * 4

        const r = pixels[p]
        const g = pixels[p + 1]
        const b = pixels[p + 2]

        const chroma =
          Math.max(r, g, b) - Math.min(r, g, b)

        const distance =
          Math.abs(r - background[0]) +
          Math.abs(g - background[1]) +
          Math.abs(b - background[2])

        if (chroma >= 40 && distance >= 65) {
          mask[i] = 1
        }
      }

      components = findComponents(
        mask,
        width,
        height
      )
    }

    // 3. Evaluación de nitidez independiente del fondo.
    let sum = 0
    let sumSquares = 0
    let sharpnessSamples = 0

    const sharpXStart = Math.max(
      1,
      Math.floor(width * 0.10)
    )

    const sharpXEnd = Math.min(
      width - 1,
      Math.ceil(width * 0.90)
    )

    const sharpYStart = Math.max(
      1,
      Math.floor(height * 0.10)
    )

    const sharpYEnd = Math.min(
      height - 1,
      Math.ceil(height * 0.90)
    )

    for (let y = sharpYStart; y < sharpYEnd; y++) {
      for (let x = sharpXStart; x < sharpXEnd; x++) {
        const i = y * width + x

        const laplacian =
          4 * gray[i] -
          gray[i - 1] -
          gray[i + 1] -
          gray[i - width] -
          gray[i + width]

        sum += laplacian
        sumSquares += laplacian * laplacian

        sharpnessSamples++
      }
    }

    const laplacianMean = sharpnessSamples
      ? sum / sharpnessSamples
      : 0

    const variance = sharpnessSamples
      ? Math.max(
          0,
          sumSquares / sharpnessSamples -
          laplacianMean * laplacianMean
        )
      : null

    const isBlurry =
      variance !== null &&
      variance < BLUR_THRESHOLD

    if (isBlurry) {
      issues.push(
        'Posible desenfoque: se requiere repetir la fotografía.'
      )
    }

    // 4. Evaluación de iluminación independiente del fondo.
    let brightnessSum = 0
    let darkPixels = 0
    let brightPixels = 0
    let brightnessSamples = 0

    const xStart = Math.floor(width * 0.15)
    const xEnd = Math.ceil(width * 0.85)
    const yStart = Math.floor(height * 0.15)
    const yEnd = Math.ceil(height * 0.85)

    for (let y = yStart; y < yEnd; y++) {
      for (let x = xStart; x < xEnd; x++) {
        const value = gray[y * width + x]

        brightnessSum += value
        brightnessSamples++

        if (value < 35) darkPixels++
        if (value > 235) brightPixels++
      }
    }

    const brightness = brightnessSamples > 0
      ? brightnessSum / brightnessSamples
      : null

    const insufficientLighting =
      brightness !== null &&
      (
        brightness < 50 ||
        darkPixels / brightnessSamples > 0.45
      )

    const excessiveLighting =
      brightness !== null &&
      (
        brightness > 220 ||
        brightPixels / brightnessSamples > 0.45
      )

    if (insufficientLighting) {
      issues.push(
        'Iluminación insuficiente: imagen demasiado oscura.'
      )
    }

    if (excessiveLighting) {
      issues.push(
        'Iluminación excesiva: imagen demasiado brillante.'
      )
    }

    // 5. Evaluación experimental de regiones visuales.
    if (background !== null && components.length > 1) {
      issues.push(
        'Se detectaron varias regiones visuales. Comprueba manualmente la cantidad de piezas.'
      )
    }

    if (
      background !== null &&
      components.length === 1 &&
      components[0].touchesBorder
    ) {
      issues.push(
        'Una región visual toca el borde. Comprueba que el producto esté completo.'
      )
    }

    if (background !== null && components.length === 0) {
      issues.push(
        'No se pudo separar una región visual del fondo. Requiere revisión.'
      )
    }

    // 6. Clasificación de calidad y composición.
    // Desenfoque e iluminación incorrecta:
    // rechazo automático según los umbrales experimentales.
    const hardQualityFailure =
      isBlurry ||
      insufficientLighting ||
      excessiveLighting

    // Si no existe un fondo uniforme, la composición
    // debe ser confirmada manualmente.
    // Esta segmentación no reconoce frutas individualmente.
    const compositionNeedsReview =
      background === null ||
      components.length !== 1 ||
      components.some(component => component.touchesBorder)

    const status: CaptureQualityStatus =
      hardQualityFailure
        ? 'invalid'
        : compositionNeedsReview
          ? 'review'
          : 'valid'

    return {
      status,
      issues,

      metrics: {
        width,
        height,

        laplacianVariance:
          variance === null
            ? null
            : Number(variance.toFixed(2)),

        meanBrightness:
          brightness === null
            ? null
            : Number(brightness.toFixed(2)),

        foregroundCount:
          background !== null
            ? components.length
            : null,
      },
    }
  } catch {
    return fallback()
  } finally {
    bitmap?.close()
  }
}
