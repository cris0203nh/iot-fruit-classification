/** AGROP-26: validación técnica de archivo, distinta de la legibilidad visual. */
export const MAX_CAPTURE_BYTES = 5 * 1024 * 1024

export function captureFileError(file: Pick<File, 'size' | 'type'>): string | null {
  if (file.type !== 'image/jpeg' && file.type !== 'image/png') {
    return 'Selecciona una fotografía JPG o PNG. El formato HEIC no se admite todavía.'
  }
  if (file.size <= 0) return 'La fotografía está vacía.'
  if (file.size > MAX_CAPTURE_BYTES) return 'La fotografía supera el máximo de 5 MB.'
  return null
}
