import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { invitationFromLocation } from '../auth/googleGis'
import { CommercialLanding } from '../../pages/CommercialLanding'

export function PublicEntry() {
  const [invitation, setInvitation] = useState(() => Boolean(invitationFromLocation()))
  const location = useLocation()
  useEffect(() => {
    const receive = () => { if (invitationFromLocation()) setInvitation(true) }
    window.addEventListener('hashchange', receive)
    return () => window.removeEventListener('hashchange', receive)
  }, [])
  useEffect(() => {
    const id = location.hash.slice(1)
    if (['beneficios','como-funciona','planes','preguntas'].includes(id)) {
      const target = document.getElementById(id)
      target?.scrollIntoView({ block: 'start' }); target?.focus({ preventScroll: true })
    }
  }, [location.hash])
  // Conserva el token solo en la memoria del mecanismo SaaS-06, nunca en query/path.
  return invitation ? <Navigate to="/acceso" replace /> : <CommercialLanding />
}
