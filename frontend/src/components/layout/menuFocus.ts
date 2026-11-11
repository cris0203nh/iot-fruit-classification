/** Selección del destino de foco al tabular dentro del menú móvil.
 *  Es una función pura; no consulta el DOM ni altera el foco por sí misma. */
export function menuTabTarget<T>(
  items: readonly T[],
  active: T | null,
  reverse: boolean,
): T | null {
  if (items.length === 0) return null
  const isInside = active !== null && items.includes(active)
  if (reverse) return !isInside || active === items[0] ? items[items.length - 1] : null
  return !isInside || active === items[items.length - 1] ? items[0] : null
}
