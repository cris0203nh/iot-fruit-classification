import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import './PublicHeader.css'

const links = [
  ['beneficios', 'Beneficios'],
  ['como-funciona', 'Cómo funciona'],
  ['planes', 'Planes DEMO'],
  ['preguntas', 'Preguntas frecuentes'],
] as const

export function PublicHeader() {
  const menu = useRef<HTMLDetailsElement>(null)
  const closeMenu = () => { if (menu.current) menu.current.open = false }

  return (
    <header className="public-header">
      <div className="public-header__inner">
        <Link to="/" className="public-brand" aria-label="AgroScan, inicio" onClick={closeMenu}>
          <span className="public-brand__symbol"><Icon name="leaf" size={24} /></span>
          <strong>AgroScan<small>Inteligencia para la fruta</small></strong>
        </Link>
        <nav className="public-header__desktop" aria-label="Navegación comercial">
          {links.map(([id, label]) => <Link key={id} to={`/#${id}`}>{label}</Link>)}
        </nav>
        <div className="public-header__actions">
          <Link to="/acceso" className="public-access">Acceder</Link>
          <Link to="/planes" className="public-header__cta">Explorar planes <Icon name="arrow-right" size={17} /></Link>
        </div>
        <details ref={menu} className="public-header__mobile" onKeyDown={event => {
          if (event.key === 'Escape' && menu.current?.open) {
            closeMenu()
            menu.current?.querySelector('summary')?.focus()
          }
        }}>
          <summary aria-label="Abrir o cerrar menú comercial"><Icon name="menu" size={23} /></summary>
          <nav aria-label="Navegación comercial móvil">
            {links.map(([id, label]) => <Link key={id} to={`/#${id}`} onClick={closeMenu}>{label}</Link>)}
            <Link to="/acceso" onClick={closeMenu}>Acceder a AgroScan</Link>
            <Link to="/planes" onClick={closeMenu} className="public-header__mobile-cta">Explorar catálogo DEMO <Icon name="arrow-right" size={17} /></Link>
          </nav>
        </details>
      </div>
    </header>
  )
}
