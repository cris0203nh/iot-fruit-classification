import { useEffect, useRef, useState } from 'react'
import { googleChallenge, googleConfiguration, linkGoogle } from '../../services/agroscanApi'
import { loadGoogleSdk } from './googleGis'
import './GoogleAccess.css'

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
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => { if (open && !dialog.current?.open) dialog.current?.showModal() }, [open])
  useEffect(() => {
    if (!open) return
    if (linked) dialog.current?.querySelector<HTMLButtonElement>('footer button')?.focus()
    else if (confirmed) dialog.current?.querySelector<HTMLElement>('section[aria-label]')?.focus()
  }, [open, confirmed, linked])
  function close() {
    if (busy) return
    dialog.current?.close()
  }
  return <>
    <button ref={trigger} type="button" className="google-link-trigger" aria-haspopup="dialog" onClick={() => { setPassword(''); setConfirmed(false); setOpen(true) }}>Vincular Google a mi cuenta</button>
    <dialog ref={dialog} className="google-link-dialog" aria-labelledby="google-link-title" aria-describedby="google-link-description"
      onCancel={event => { if (busy) event.preventDefault() }} onClose={() => { setOpen(false); setPassword(''); setConfirmed(false); trigger.current?.focus() }}>
      {open && <><header><span className="google-link-eyebrow">Seguridad de tu cuenta</span><h2 id="google-link-title">Accede también con Google</h2>
        <p id="google-link-description">Vincula una cuenta Google para iniciar sesión con ella en AgroScan. Tus empresas, roles y permisos se conservan.</p></header>
        {linked ? <div className="google-link-success" role="status"><strong>Cuenta Google vinculada</strong><p>Ya puedes usar esa cuenta para iniciar sesión. Tu acceso con usuario y contraseña sigue disponible.</p></div>
          : <><ol className="google-link-steps" aria-label="Pasos de vinculación"><li aria-current={!confirmed ? 'step' : undefined}>1. Confirma tu identidad</li><li aria-current={confirmed ? 'step' : undefined}>2. Elige tu cuenta Google</li></ol>
            {!confirmed ? <form onSubmit={event => { event.preventDefault(); if (password) setConfirmed(true) }}><label htmlFor="google-link-password">Contraseña actual de AgroScan</label>
              <input id="google-link-password" type="password" value={password} required maxLength={128} autoComplete="current-password"
                onChange={event => setPassword(event.target.value)} aria-describedby="google-link-help" />
              <p id="google-link-help">La contraseña y tu identidad Google se comprobarán juntas antes de vincularlas.</p>
              <button className="action-button action-button--primary" disabled={!password}>Confirmar y elegir cuenta Google</button>
            </form> : <section tabIndex={-1} aria-label="Confirmar cuenta Google"><p>Continúa con la cuenta Google que deseas vincular. Al seleccionarla, autorizas expresamente esta vinculación.</p>
              <GoogleAccessButton onCredential={async credential => {
                setBusy(true)
                try { await linkGoogle(credential, password); setPassword(''); setLinked(true) }
                finally { setBusy(false) }
              }} />
              <button type="button" disabled={busy} onClick={() => { setConfirmed(false); setPassword('') }}>Volver a la contraseña</button>
            </section>}</>}
        <footer><p>No se vinculan cuentas automáticamente por coincidencia de correo.</p><button type="button" className="action-button action-button--secondary" disabled={busy} onClick={close}>{linked ? 'Cerrar' : 'Cancelar'}</button></footer>
      </>}
    </dialog>
  </>
}
