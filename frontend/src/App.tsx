import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { EvaluationPage } from './pages/EvaluationPage'
import { HomePage } from './pages/HomePage'
import { HistoryDetailPage, HistoryPage } from './pages/HistoryPage'
import { LotsPage } from './pages/LotsPage'
import { NotFoundPage, SectionPage } from './pages/SectionPage'
import { TraceabilityPage, TraceabilityDetailPage } from './pages/TraceabilityPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="evaluacion" element={<EvaluationPage />} />
          <Route path="historial" element={<HistoryPage />} />
          <Route path="historial/:evaluationId" element={<HistoryDetailPage />} />
          <Route path="trazabilidad" element={<TraceabilityPage />} />
          <Route path="trazabilidad/:evaluationId" element={<TraceabilityDetailPage />} />
          <Route path="estadisticas" element={<SectionPage section="estadisticas" />} />
          <Route path="lotes" element={<LotsPage />} />
          <Route path="mantenimiento" element={<SectionPage section="mantenimiento" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
