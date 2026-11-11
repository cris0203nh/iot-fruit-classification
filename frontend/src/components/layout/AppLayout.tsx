import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { operatorNavigation, reviewerNavigation, administratorNavigation } from '../../app/navigation'
import type { NavigationItem } from '../../app/navigation'
import { getSessionRole } from '../../services/agroscanApi'
import { Icon } from './Icon'
import { menuTabTarget } from './menuFocus'
import './AppLayout.css'

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const role = getSessionRole()
  const reviewer = role === 'revisor'
  const administrator = role === 'administrador'
  const roleTitle = reviewer ? 'Panel de revisión' : administrator ? 'Panel administrativo' : 'Panel de operaciones'
  const roleDescription = reviewer ? 'Control de evaluaciones' : administrator ? 'Supervisión de AgroScan' : 'Gestión de productos agrícolas'
  const roleBadge = reviewer ? 'REVISOR' : administrator ? 'ADMINISTRADOR' : 'OPERADOR'
  const navigation: NavigationItem[] = reviewer
    ? reviewerNavigation
    : administrator ? administratorNavigation : operatorNavigation
  const { pathname } = useLocation()
  const sidebarRef = useRef<HTMLElement>(null)
  const mobileMenuButtonRef = useRef<HTMLButtonElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const previousPathname = useRef(pathname)
  const closeDestination = useRef<'button' | 'content' | null>(null)

  // En cambios de ruta, el lector de pantalla llega al contenido nuevo.
  // No se roba el foco en la primera carga ni al alternar pestañas por query.
  useEffect(() => {
    if (previousPathname.current === pathname) return
    previousPathname.current = pathname
    mainRef.current?.focus()
  }, [pathname])

  // El menú móvil funciona como diálogo: foco inicial, Tab confinado y Escape.
  useEffect(() => {
    if (!menuOpen) return
    const sidebar = sidebarRef.current
    sidebar?.querySelector<HTMLElement>('.nav-link')?.focus()

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeDestination.current = 'button'
        setMenuOpen(false)
        return
      }
      if (event.key !== 'Tab' || !sidebar) return
      const links = Array.from(sidebar.querySelectorAll<HTMLElement>('a[href]'))
      if (links.length === 0) return
      const target = menuTabTarget<HTMLElement>(links, document.activeElement as HTMLElement | null, event.shiftKey)
      if (target) {
        event.preventDefault()
        target.focus()
      }
    }

    document.addEventListener('keydown', handleKeydown)
    return () => document.removeEventListener('keydown', handleKeydown)
  }, [menuOpen])

  // El botón está dentro de un área inert mientras el menú está abierto;
  // restaurar el foco solo después de cerrar y retirar inert.
  useEffect(() => {
    if (menuOpen || !closeDestination.current) return
    const destination = closeDestination.current
    closeDestination.current = null
    if (destination === 'button') mobileMenuButtonRef.current?.focus()
    else mainRef.current?.focus()
  }, [menuOpen])

  // Al regresar al tamaño de escritorio, el menú deja de ser modal.
  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 701px)')
    const onResize = (event: MediaQueryListEvent) => {
      if (event.matches) setMenuOpen(false)
    }
    desktop.addEventListener('change', onResize)
    return () => desktop.removeEventListener('change', onResize)
  }, [])

  function closeMenuFromBackdrop() {
    closeDestination.current = 'button'
    setMenuOpen(false)
  }

  function renderLinks(items: NavigationItem[]) {
    return items.map(({ path, label, icon }) => (
      <NavLink
        key={path}
        to={path}
        end={path === '/'}
        className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}
        onClick={() => { if (menuOpen) closeDestination.current = 'content'; setMenuOpen(false) }}
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
          tabIndex={-1}
          onClick={closeMenuFromBackdrop}
        />
      )}

      <aside
        ref={sidebarRef}
        className={`sidebar${menuOpen ? ' sidebar--open' : ''}`}
        id="primary-sidebar"
        role={menuOpen ? 'dialog' : undefined}
        aria-modal={menuOpen || undefined}
        aria-label={menuOpen ? 'Menú de navegación' : undefined}
      >
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
            <strong>{roleTitle}</strong>
            <span>{roleDescription}</span>
          </div>
        </div>

        <nav aria-label="Navegación principal" className="sidebar-nav">
          {renderLinks(navigation)}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-disclaimer">
            <Icon name="info" size={17} />
            <span>Integración por módulos<br />Hardware sin verificar</span>
          </div>
        </div>
      </aside>

      <div className="workspace" inert={menuOpen}>
        <header className="topbar">
          <div className="topbar__main">
            <button
              ref={mobileMenuButtonRef}
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
            <span>AgroScan / {roleBadge}</span>
          </div>
          <span className="topbar__context">{roleDescription}</span>
        </header>
        <main id="main-content" className="page-content" ref={mainRef} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
