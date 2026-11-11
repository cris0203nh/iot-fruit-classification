
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'

import { AppLayout } from './components/layout/AppLayout'
import { Icon } from './components/layout/Icon'
import { AuthGate } from './features/auth/AuthGate'
import { getSessionRole } from './services/agroscanApi'

import { EvaluationPage } from './pages/EvaluationPage'
import { HomePage } from './pages/HomePage'
import { AdminDashboard } from './pages/AdminDashboard'
import { UsersPage } from './pages/UsersPage'

import {
  HistoryDetailPage,
  HistoryPage,
} from './pages/HistoryPage'

import { LotsPage } from './pages/LotsPage'

import {
  NotFoundPage,
  SectionPage,
} from './pages/SectionPage'

import {
  TraceabilityPage,
  TraceabilityDetailPage,
} from './pages/TraceabilityPage'

import './App.css'

// ==========================================
// PÁGINA DE INICIO SEGÚN EL ROL
// ==========================================

function RoleHome() {
  const role = getSessionRole()

  if (role === 'administrador') {
    return <AdminDashboard />
  }

  return <HomePage />
}

// ==========================================
// PROTECCIÓN DE FUNCIONES DEL OPERADOR
// ==========================================

function OperatorRoute({ children }: { children: ReactNode }) {
  if (getSessionRole() === 'revisor') {
    return (
      <section className="seccion" aria-label="Acceso restringido">
        <header className="seccion__head">
          <p className="seccion__kicker">Acceso restringido</p>
          <h1 className="seccion__title">Solo consulta</h1>
          <p className="seccion__lede">El rol revisor no puede registrar evaluaciones ni modificar lotes. Puedes consultar el historial sin alterar los registros.</p>
        </header>
        <div className="seccion__estado seccion__estado--restringido">
          <span className="seccion__estado-icon" aria-hidden="true"><Icon name="info" size={22} /></span>
          <div className="seccion__estado-body">
            <p className="seccion__estado-kicker">Rol revisor</p>
            <h2>Tu cuenta no tiene permisos de operación</h2>
            <p>Las altas, ediciones y capturas están deshabilitadas para este perfil. La consulta de historial y trazabilidad sigue disponible.</p>
          </div>
        </div>
        <Link to="/historial" className="action-button action-button--primary">Abrir historial</Link>
      </section>
    )
  }
  return children
}

function AdminRoute({ children }: { children: ReactNode }) {
  const role = getSessionRole()

  if (role !== 'administrador') {
    return <NotFoundPage />
  }

  return children
}

// ==========================================
// APLICACIÓN PRINCIPAL
// ==========================================

function App() {
  return (
    <BrowserRouter>
      <Routes>

        <Route
          element={
            <AuthGate>
              <AppLayout />
            </AuthGate>
          }
        >

          {/* INICIO */}

          <Route
            index
            element={<RoleHome />}
          />

          {/* OPERADOR */}

          <Route
            path="evaluacion"
            element={
              <OperatorRoute>
                <EvaluationPage />
              </OperatorRoute>
            }
          />

          <Route
            path="lotes"
            element={
              <OperatorRoute>
                <LotsPage />
              </OperatorRoute>
            }
          />

          {/* HISTORIAL */}

          <Route
            path="historial"
            element={<HistoryPage />}
          />

          <Route
            path="historial/:evaluationId"
            element={<HistoryDetailPage />}
          />

          {/* TRAZABILIDAD */}

          <Route
            path="trazabilidad"
            element={<TraceabilityPage />}
          />

          <Route
            path="trazabilidad/:evaluationId"
            element={<TraceabilityDetailPage />}
          />

          {/* ADMINISTRADOR */}

          <Route
            path="usuarios"
            element={
              <AdminRoute>
                <UsersPage />
              </AdminRoute>
            }
          />

          <Route
            path="estadisticas"
            element={
              <AdminRoute>
                <SectionPage section="estadisticas" />
              </AdminRoute>
            }
          />

          {/* RUTA NO ENCONTRADA */}

          <Route
            path="*"
            element={<NotFoundPage />}
          />

        </Route>

      </Routes>
    </BrowserRouter>
  )
}

export default App
