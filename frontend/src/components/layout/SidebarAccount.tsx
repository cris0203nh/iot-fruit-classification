import { useEffect, useState, type ReactNode } from 'react'
import { ApiDataError, request } from '../../services/agroscanApi'
import { Icon } from './Icon'

export function AccountIdentity({ platformOwner = false }: { platformOwner?: boolean }) {
  const [account, setAccount] = useState<{ username: string; fullName: string } | null>(null)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    request(platformOwner ? '/api/platform/me' : '/api/auth/me').then(value => {
      if (typeof value !== 'object' || value === null || !('username' in value) || !('fullName' in value)
        || typeof value.username !== 'string' || typeof value.fullName !== 'string') throw new ApiDataError()
      if (active) { setAccount({ username: value.username, fullName: value.fullName }); setFailed(false) }
    }).catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [platformOwner, retry])
  return account ? <><strong>{account.fullName}</strong><span>@{account.username}</span></>
    : failed ? <button type="button" onClick={() => setRetry(v => v + 1)}>Reintentar cuenta</button>
      : <span role="status">Consultando cuenta…</span>
}

export function SidebarAccount({ role, identity, actions, organizationSelector }: {
  role: string; identity: ReactNode; actions?: ReactNode; organizationSelector?: ReactNode
}) {
  return <section className="owner-sidebar-account" aria-label="Mi cuenta">
    <p className="sidebar-session-status"><span aria-hidden="true" />Sesión activa</p>
    <div className="owner-sidebar-account__identity"><span className="owner-sidebar-avatar"><Icon name="user" size={20} /></span>
      <div className="owner-account"><small>{role}</small>{identity}</div></div>
    {organizationSelector && <div className="sidebar-account-company">{organizationSelector}</div>}
    <div className="owner-session__actions">{actions}</div>
  </section>
}
