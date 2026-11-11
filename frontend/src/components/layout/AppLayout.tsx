
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  operatorNavigation,
  reviewerNavigation,
  administratorNavigation,
} from '../../app/navigation'
import type { NavigationItem } from '../../app/navigation'
import { getSessionRole } from '../../services/agroscanApi'
import { Icon } from './Icon'
import './AppLayout.css'

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)

  const role = getSessionRole()

  let roleTitle = 'Panel de operaciones'
  let roleDescription = 'Gestión de productos agrícolas'
  let roleBadge = 'OPERADOR'
  let navigation: NavigationItem[] = operatorNavigation

  if (role === 'revisor') {
    roleTitle = 'Panel de revisión'
    roleDescription = 'Control de evaluaciones'
    roleBadge = 'REVISOR'
    navigation = reviewerNavigation
  } else if (role === 'administrador') {
    roleTitle = 'Panel administrativo'
    roleDescription = 'Supervisión de AgroScan'
    roleBadge = 'ADMINISTRADOR'
    navigation = administratorNavigation
  }

  function renderLinks(items: NavigationItem[]) {
    return items.map(({ path, label, icon }) => (
      <NavLink
        key={path}
        to={path}
        end={path === '/'}
        className={({ isActive }) =>
          `nav-link${isActive ? ' nav-link--active' : ''}`
        }
        onClick={() => setMenuOpen(false)}
      >
        <Icon name={icon} size={19} />
        <span>{label}</span>
      </NavLink>
    ))
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>

      {menuOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Cerrar menú de navegación"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={`sidebar${menuOpen ? ' sidebar--open' : ''}`}
        id="primary-sidebar"
      >
        <div className="brand">
          <div className="brand-mark">
            <Icon name="leaf" size={22} />
          </div>

          <div>
            <strong>AgroScan</strong>
            <span>Inteligencia agrícola</span>
          </div>
        </div>

        <div className="station-context">
          <span className="station-context__marker" />

          <div>
            <strong>{roleTitle}</strong>
            <span>{roleDescription}</span>
          </div>
        </div>

        <div className="sidebar-section-label">
          MENÚ PRINCIPAL
        </div>

        <nav
          aria-label="Navegación principal"
          className="sidebar-nav"
        >
          {renderLinks(navigation)}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-role-card">
            <div className="sidebar-role-icon">
              <Icon name="info" size={19} />
            </div>

            <div>
              <strong>Sesión activa</strong>
              <span>{roleBadge}</span>
            </div>
          </div>

          <div className="sidebar-disclaimer">
            <Icon name="info" size={17} />
            <span>
              AgroScan · Evaluación de mango y tomate
            </span>
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
              onClick={() => setMenuOpen(value => !value)}
            >
              <Icon
                name={menuOpen ? 'close' : 'menu'}
                size={22}
              />
            </button>

            <span className="topbar__badge">
              <Icon name="leaf" size={16} />
            </span>

            <span>
              AgroScan / {roleBadge}
            </span>
          </div>

          <span className="topbar__context">
            {roleDescription}
          </span>
        </header>

        <main
          id="main-content"
          className="page-content"
        >
          <Outlet />
        </main>
      </div>
    </div>
  )
}
