import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '../components/layout/AppLayout'
import { AccountIdentity } from '../components/layout/SidebarAccount'
import { CommercialDashboard } from '../features/commercial/Commercial'
import { PlatformDashboard } from './PlatformDashboard'
import { CommercialApplicationsDashboard } from '../features/commercial/Applications'

export function OwnerWorkspace({ onLogout, sessionActions }: { onLogout: () => void; sessionActions?: ReactNode }) {
  return <AppLayout owner account={<AccountIdentity platformOwner />}
    actions={<>{sessionActions}<button type="button" className="owner-logout" onClick={onLogout}>Cerrar sesión</button></>}>
    <Routes>
      <Route path="/plataforma/solicitudes" element={<CommercialApplicationsDashboard />} />
      <Route path="/plataforma/empresas" element={<PlatformDashboard key="companies" section="companies" />} />
      <Route path="/plataforma/administradores" element={<PlatformDashboard key="administrators" section="administrators" />} />
      <Route path="/plataforma/planes" element={<CommercialDashboard />} />
      <Route path="*" element={<Navigate to="/plataforma/empresas" replace />} />
    </Routes>
  </AppLayout>
}
