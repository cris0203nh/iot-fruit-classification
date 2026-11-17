import { useEffect, useRef, useState } from 'react'
import { googleChallenge, googleConfiguration, linkGoogle } from '../../services/agroscanApi'
import { loadGoogleSdk } from './googleGis'

export function GoogleAccessButton({ onCredential }: { onCredential: (credential: string) => Promise<void> }) {
  const element = useRef<HTMLDivElement>(null)
  const callback = useRef(onCredential)
  const [state, setState] = useState<'checking' | 'ready' | 'unconfigured' | 'failed'>('checking')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [working, setWorking] = useState(false)
  useEffect(() => { callback.current = onCredential }, [onCredential])
  useEffect(() => {
    let active = true
    let cleanup: (() => void) | undefined
    async function initialize() {
      try {
        const config = await googleConfiguration()
        if (!active) return
        if (!config.enabled || !config.clientId) { setState('unconfigured'); return }
        const nonce = await googleChallenge()
        const sdk = await loadGoogleSdk()
        if (!active || !element.current) return
        sdk.accounts.id.initialize({ client_id: config.clientId, nonce, auto_select: false,
          callback: (response) => {
            if (!active || typeof response.credential !== 'string') return
            setWorking(true)
            setError('')
            callback.current(response.credential).catch((failure: unknown) => {
              if (active) {
                setError(failure instanceof Error ? failure.message : 'No se pudo validar Google.')
                setWorking(false)
                setState('checking')
                setAttempt((value) => value + 1)
              }
            }).finally(() => { if (active) setWorking(false) })
          } })
        element.current.replaceChildren()
        sdk.accounts.id.renderButton(element.current, { type: 'standard', theme: 'outline', size: 'large', text: 'continue_with', locale: 'es' })
        cleanup = () => sdk.accounts.id.cancel()
        setState('ready')
      } catch (failure) {
        if (active) { setError(failure instanceof Error ? failure.message : 'Google no está disponible.'); setState('failed') }
      }
    }
    void initialize()
    return () => { active = false; cleanup?.() }
  }, [attempt])
  return <div className="google-access">
    <div ref={element} inert={working || state !== 'ready'} />
    {state !== 'ready' && <button type="button" disabled>Continuar con Google</button>}
    {state === 'unconfigured' && <p>Google no está disponible. Puedes usar tu usuario y contraseña.</p>}
    {working && <p role="status">Verificando Google…</p>}
    {error && <p role="alert">{error}</p>}
    {state === 'failed' && <button type="button" onClick={() => {
      setError(''); setState('checking'); setAttempt((value) => value + 1)
    }}>Reintentar Google</button>}
  </div>
}

export function GoogleLinkAccount() {
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [linked, setLinked] = useState(false)
  return <details open={open} onToggle={(event) => { setOpen(event.currentTarget.open); if (!event.currentTarget.open) setPassword('') }}>
    <summary>Vincular Google a mi cuenta</summary>
    {open && <div className="users-field">
      <label htmlFor="google-link-password">Confirma la contraseña de tu cuenta actual</label>
      <input id="google-link-password" type="password" value={password} maxLength={128} autoComplete="current-password"
        onChange={(event) => setPassword(event.target.value)} />
      {password && !linked && <GoogleAccessButton onCredential={async (credential) => {
        await linkGoogle(credential, password); setPassword(''); setLinked(true)
      }} />}
      {linked && <p role="status">Cuenta Google vinculada. Tus roles se conservan.</p>}
    </div>}
  </details>
}
