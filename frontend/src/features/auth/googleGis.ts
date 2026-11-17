type Credential = { credential: string }
type GoogleSdk = { accounts: { id: {
  initialize: (options: { client_id: string; nonce: string; auto_select: boolean; callback: (response: Credential) => void }) => void
  renderButton: (element: HTMLElement, options: { type: string; theme: string; size: string; text: string; locale: string }) => void
  cancel: () => void
} } }

let sdkPromise: Promise<GoogleSdk> | null = null
export function loadGoogleSdk(): Promise<GoogleSdk> {
  const current = (window as Window & { google?: GoogleSdk }).google
  if (current) return Promise.resolve(current)
  if (sdkPromise) return sdkPromise
  sdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client?hl=es'
    script.async = true
    script.onload = () => {
      const sdk = (window as Window & { google?: GoogleSdk }).google
      if (sdk) resolve(sdk)
      else { script.remove(); sdkPromise = null; reject(new Error('Google no está disponible.')) }
    }
    script.onerror = () => { script.remove(); sdkPromise = null; reject(new Error('No se pudo conectar con Google.')) }
    document.head.append(script)
  })
  return sdkPromise
}

let initialInvitation: string | null | undefined
export function invitationFromLocation(): string | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.hash.slice(1))
  const token = params.get('invitation')
  if (token !== null) {
    initialInvitation = /^[A-Za-z0-9_-]{43}$/.test(token) ? token : null
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
  return initialInvitation ?? null
}
export function forgetInvitation(): void { initialInvitation = null }

export function invitationLink(origin: string, token: string): string {
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('Invitación no válida.')
  return `${new URL(origin).origin}/#invitation=${encodeURIComponent(token)}`
}
