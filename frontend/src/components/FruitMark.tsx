import type { FruitProduct } from '../app/lotDraft'

/** Ilustración de espécimen dibujada con el color del texto, para adaptarse al estado. */
export function FruitMark({ product, size = 56 }: { product: FruitProduct; size?: number }) {
  if (product === 'mango') {
    return (
      <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true" focusable="false">
        <g transform="rotate(-28 24 28)">
          <ellipse cx="24" cy="28" rx="13.4" ry="9.6" fill="currentColor" fillOpacity=".18" stroke="currentColor" strokeWidth="1.7" />
        </g>
        <path d="M35.8 20.9c.9-1.4 1.6-2.9 2-4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path
          d="M37.4 18.1c.9-2.6 2.9-4.4 5.6-5-.2 2.7-1.7 4.9-4.1 5.9-1 .4-1.7-.2-1.5-1Z"
          fill="currentColor" fillOpacity=".18" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"
        />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true" focusable="false">
      <circle cx="24" cy="28" r="13.4" fill="currentColor" fillOpacity=".18" stroke="currentColor" strokeWidth="1.7" />
      <path d="M24 14.6V9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M24 14.6c-2-2-4.6-3.2-7.5-3.4M24 14.6c2-2 4.6-3.2 7.5-3.4M24 14.6c-1.3-2.6-3.3-4.7-6.1-5.8M24 14.6c1.3-2.6 3.3-4.7 6.1-5.8"
        fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
      />
    </svg>
  )
}
