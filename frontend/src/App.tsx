import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AppLayout } from './components/layout/AppLayout'
import { AuthGate } from './features/auth/AuthGate'
import { getSessionRole } from './services/agroscanApi'
import { EvaluationPage } from './pages/EvaluationPage'
import { HomePage } from './pages/HomePage'
import { HistoryDetailPage, HistoryPage } from './pages/HistoryPage'
import { LotsPage } from './pages/LotsPage'
import { NotFoundPage, SectionPage } from './pages/SectionPage'
import { TraceabilityPage, TraceabilityDetailPage } from './pages/TraceabilityPage'
import './App.css'

function OperatorRoute({ children }: { children: ReactNode }) {
  if (getSessionRole() === 'revisor') {
    return (
      <section className="panel" aria-label="Acceso restringido">
        <h1>Solo consulta</h1>
        <p>El rol revisor no puede registrar evaluaciones ni modificar lotes. Puedes consultar el historial sin alterar los registros.</p>
        <Link className="action-button action-button--primary" to="/historial">Abrir historial</Link>
      </section>
    )
  }
  return children
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AuthGate><AppLayout /></AuthGate>}>
          <Route index element={<HomePage />} />
          <Route path="evaluacion" element={<OperatorRoute><EvaluationPage /></OperatorRoute>} />
          <Route path="historial" element={<HistoryPage />} />
          <Route path="historial/:evaluationId" element={<HistoryDetailPage />} />
          <Route path="trazabilidad" element={<TraceabilityPage />} />
          <Route path="trazabilidad/:evaluationId" element={<TraceabilityDetailPage />} />
          <Route path="estadisticas" element={<SectionPage section="estadisticas" />} />
          <Route path="lotes" element={<OperatorRoute><LotsPage /></OperatorRoute>} />
          <Route path="mantenimiento" element={<OperatorRoute><SectionPage section="mantenimiento" /></OperatorRoute>} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
