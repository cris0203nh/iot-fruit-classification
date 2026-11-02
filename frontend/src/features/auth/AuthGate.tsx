import { useState, type FormEvent, type ReactNode } from 'react'
import { ApiConnectionError, ApiResponseError, clearOperatorSession, isOperatorAuthenticated, loginOperator } from '../../services/agroscanApi'
import './AuthGate.css'

/** Sesión de operador limitada a la pestaña. No persiste credenciales en el navegador. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(isOperatorAuthenticated)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (working || !username.trim() || !password) return
    setWorking(true)
    setError(null)
    try {
      await loginOperator(username, password)
      setPassword('')
      setAuthenticated(true)
    } catch (failure) {
      setError(failure instanceof ApiResponseError
        ? failure.status === 401 ? 'Usuario o contraseña incorrectos.' : failure.message
        : failure instanceof ApiConnectionError
          ? 'No se pudo contactar con FastAPI. Comprueba que esté ejecutándose.'
          : 'No fue posible validar el inicio de sesión.')
    } finally {
      setWorking(false)
    }
  }

  if (authenticated) {
    return (
      <>
        <div className="agroscan-session">
          <span>Sesión de operador activa</span>
          <button type="button" onClick={() => { clearOperatorSession(); setAuthenticated(false); setPassword(''); setError(null) }}>Cerrar sesión</button>
        </div>
        {children}
      </>
    )
  }

  return (
    <main className="agroscan-login">
      <form onSubmit={submit} className="agroscan-login__panel">
        <h1>Ingresar a AgroScan</h1>
        <p>Inicia sesión con tu cuenta de operador o administrador para registrar evaluaciones y fotografías.</p>
        <label htmlFor="agroscan-login-user">Usuario</label>
        <input id="agroscan-login-user" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} disabled={working} />
        <label htmlFor="agroscan-login-pass">Contraseña</label>
        <input id="agroscan-login-pass" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} disabled={working} />
        {error && <p role="alert" className="agroscan-login__error">{error}</p>}
        <button type="submit" disabled={working || !username.trim() || !password}>{working ? 'Validando…' : 'Iniciar sesión'}</button>
        <small>La sesión no se guarda al recargar la página. No compartas tus credenciales.</small>
      </form>
    </main>
  )
}
