import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { primaryNavigation, secondaryNavigation } from '../../app/navigation'
import type { NavigationItem } from '../../app/navigation'
import { Icon } from './Icon'
import './AppLayout.css'

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)

  function renderLinks(items: NavigationItem[]) {
    return items.map(({ path, label, icon }) => (
      <NavLink
        key={path}
        to={path}
        end={path === '/'}
        className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}
        onClick={() => setMenuOpen(false)}
      >
        <Icon name={icon} size={19} />
        <span>{label}</span>
      </NavLink>
    ))
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Saltar al contenido</a>

      {menuOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Cerrar menú de navegación"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside className={`sidebar${menuOpen ? ' sidebar--open' : ''}`} id="primary-sidebar">
        <div className="brand">
          <div className="brand-mark"><Icon name="leaf" size={21} /></div>
          <div>
            <strong>AgroScan</strong>
            <span>Evaluación externa</span>
          </div>
        </div>

        <div className="station-context">
          <span className="station-context__marker" aria-hidden="true" />
          <div>
            <strong>Estación local</strong>
            <span>Mango y tomate</span>
          </div>
        </div>

        <nav aria-label="Navegación principal" className="sidebar-nav">
          {renderLinks(primaryNavigation)}
        </nav>

        <div className="sidebar-bottom">
          <nav aria-label="Configuración de la estación" className="sidebar-nav">
            {renderLinks(secondaryNavigation)}
          </nav>
          <div className="sidebar-disclaimer">
            <Icon name="info" size={17} />
            <span>Integración por módulos<br />Hardware sin verificar</span>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar__main">
            <button
              className="mobile-menu-button"
              type="button"
              aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
              aria-controls="primary-sidebar"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <Icon name={menuOpen ? 'close' : 'menu'} size={22} />
            </button>
            <span className="topbar__badge" aria-hidden="true"><Icon name="leaf" size={15} /></span>
            <span>Plataforma de evaluación externa</span>
          </div>
          <span className="topbar__context">Integración en desarrollo</span>
        </header>
        <main id="main-content" className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
