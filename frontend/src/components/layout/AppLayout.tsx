import { useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { operatorNavigation, reviewerNavigation, administratorNavigation, ownerNavigation } from '../../app/navigation'
import type { NavigationItem } from '../../app/navigation'
import { getSessionRole } from '../../services/agroscanApi'
import { Icon } from './Icon'
import { menuTabTarget } from './menuFocus'
import { AccountIdentity, SidebarAccount } from './SidebarAccount'
import { SidebarSessionContext } from './sidebarSession'
import './AppLayout.css'

export function AppLayout({ owner = false, account, actions, children }: {
  owner?: boolean; account?: ReactNode; actions?: ReactNode; children?: ReactNode
} = {}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const role = getSessionRole()
  const reviewer = role === 'revisor'
  const administrator = role === 'administrador'
  const sidebarSession = useContext(SidebarSessionContext)
  const roleTitle = owner ? 'Panel de plataforma' : reviewer ? 'Panel de revisión' : administrator ? 'Panel administrativo' : 'Panel de operaciones'
  const roleDescription = owner ? 'Gestión global de AgroScan' : reviewer ? 'Control de evaluaciones' : administrator ? 'Supervisión de AgroScan' : 'Gestión de productos agrícolas'
  const navigation: NavigationItem[] = owner ? ownerNavigation : reviewer
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
      if (document.querySelector('dialog.google-link-dialog[open]')) return
      if (event.key === 'Escape') {
        event.preventDefault()
        closeDestination.current = 'button'
        setMenuOpen(false)
        return
      }
      if (event.key !== 'Tab' || !sidebar) return
      const links = Array.from(sidebar.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),select:not([disabled]),summary'))
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
    const desktop = window.matchMedia('(min-width: 1001px)')
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
        end={path === '/app'}
        className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}
        onClick={() => { if (menuOpen) closeDestination.current = 'content'; setMenuOpen(false) }}
      >
        <Icon name={icon} size={19} />
        <span>{label}</span>
      </NavLink>
    ))
  }

  return (
    <div className={`app-shell${owner ? ' app-shell--owner' : administrator ? ' app-shell--administrator' : ''}`}>
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
            <span>{owner ? 'Plataforma multiempresa' : 'Evaluación externa'}</span>
          </div>
          <button type="button" className="sidebar-close" aria-label="Cerrar menú" onClick={closeMenuFromBackdrop}>
            <Icon name="close" size={20} />
          </button>
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
          <SidebarAccount role={owner ? 'Propietario global' : administrator ? 'Administrador empresarial' : reviewer ? 'Revisor (consulta)' : 'Operador'}
            identity={owner ? account : <AccountIdentity />} actions={owner ? actions : sidebarSession?.actions}
            organizationSelector={owner ? undefined : sidebarSession?.organizationSelector} />
          <div className="sidebar-disclaimer">
            <Icon name="info" size={17} />
            <span>{owner ? <>Administración global<br />Contratación solo DEMO</> : <>Verifica la estación<br />antes de evaluar</>}</span>
          </div>
        </div>
      </aside>

      <div className="workspace" inert={menuOpen}>
        <div className="layout-mobile-controls">
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
        </div>
        <main id="main-content" className="page-content" ref={mainRef} tabIndex={-1}>
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  )
}
