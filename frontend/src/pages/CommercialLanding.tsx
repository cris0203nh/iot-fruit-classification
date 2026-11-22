import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PublicHeader } from '../components/layout/PublicHeader'
import { Icon, type IconName } from '../components/layout/Icon'
import { PlanCard } from '../features/commercial/Commercial'
import { getCatalog, type Plan } from '../features/commercial/commercialApi'
import { PlanRequestLink } from '../features/commercial/PlanRequestLink'
import inspectionImage from '../assets/agroscan-fruit-inspection.webp'
import './CommercialLanding.css'

type Feature = { icon: IconName; eyebrow: string; title: string; description: string }

const benefits: Feature[] = [
  {
    icon: 'scan', eyebrow: '01 / Visión artificial', title: 'Más contexto en cada evaluación.',
    description: 'Reúne imágenes y análisis asistido para que tu equipo revise la fruta con la evidencia disponible.',
  },
  {
    icon: 'network', eyebrow: '02 / Trazabilidad', title: 'De la captura al historial.',
    description: 'Vincula evaluaciones, decisiones y fotografías a su recorrido dentro de cada lote.',
  },
  {
    icon: 'boxes', eyebrow: '03 / Gestión operativa', title: 'Tus lotes, en un mismo lugar.',
    description: 'Ordena la información de la operación y encuentra los registros sin dispersarlos entre herramientas.',
  },
  {
    icon: 'clipboard', eyebrow: '04 / Control humano', title: 'La última palabra es de tu equipo.',
    description: 'Separa las tareas de operación, revisión y administración mediante roles y permisos.',
  },
]

const steps: { icon: IconName; title: string; description: string }[] = [
  { icon: 'boxes', title: 'Registra el lote', description: 'Crea el contexto de trabajo de tu empresa y organiza las piezas que se evaluarán.' },
  { icon: 'camera', title: 'Captura información', description: 'Asocia fotografías y, cuando estén disponibles, mediciones procedentes de dispositivos IoT.' },
  { icon: 'scan', title: 'Consulta la asistencia', description: 'Examina el análisis visual junto con sus imágenes y datos de soporte.' },
  { icon: 'clipboard', title: 'Revisa y da seguimiento', description: 'Conserva la intervención humana y consulta la trazabilidad de cada evaluación.' },
]

const faqs = [
  ['¿AgroScan reemplaza al evaluador?', 'No. La clasificación es asistida y permite revisión humana. Su exactitud debe evaluarse con evidencia experimental; esta demostración no acredita resultados comerciales ni de hardware.'],
  ['¿Solicitar un plan activa mi empresa?', 'No. Primero se registra una solicitud pendiente. El propietario revisa el alta y, si la aprueba, entrega una invitación al primer administrador. No hay registro público con privilegios.'],
  ['¿Debo ingresar una tarjeta o pagar?', 'No. Los precios son ilustrativos DEMO. La solicitud y la invitación no son un pago; cualquier contratación habilitada en este entorno es simulada y no realiza cobros.'],
  ['¿Cómo recibe acceso mi equipo?', 'El primer administrador acepta su invitación y elige una contraseña privada, o utiliza Google cuando está configurado. Después puede gestionar el acceso de su equipo mediante los roles disponibles.'],
  ['¿Puedo ver los datos de otra empresa?', 'El acceso operativo está separado por empresa y por permisos. Los usuarios acceden únicamente a las organizaciones y recursos para los que tienen autorización.'],
] as const

/** Presentación pública: los importes, beneficios y límites proceden exclusivamente del catálogo. */
export function PublicPlanCards({ plans }: { plans: Plan[] }) {
  const active = plans.filter(plan => plan.isActive)
  return active.length ? (
    <div className="landing-plan-grid">
      {active.map(plan => (
        <PlanCard key={plan.id} plan={plan} headingAs="h3">
          <PlanRequestLink plan={plan} className="landing-button landing-button--full" />
        </PlanCard>
      ))}
    </div>
  ) : (
    <div className="landing-catalog-state">
      <Icon name="leaf" size={26} />
      <h3>Estamos preparando el catálogo</h3>
      <p>Vuelve a consultar los planes disponibles. No se registrará una solicitud sin un plan vigente.</p>
    </div>
  )
}

function PublicPlanCatalog() {
  const [plans, setPlans] = useState<Plan[] | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    getCatalog().then(
      data => { if (active) { setPlans(data.plans); setError(false) } },
      () => { if (active) setError(true) },
    )
    return () => { active = false }
  }, [attempt])

  if (error) return (
    <div className="landing-catalog-state">
      <p role="alert">No pudimos consultar el catálogo. No se mostrarán precios sin confirmar.</p>
      <button type="button" className="landing-button" onClick={() => { setError(false); setPlans(null); setAttempt(value => value + 1) }}>Reintentar consulta</button>
    </div>
  )
  if (!plans) return <div className="landing-catalog-state landing-catalog-state--loading" role="status">Consultando planes disponibles…</div>
  return <PublicPlanCards plans={plans} />
}

function HeroVisual() {
  return (
    <figure className="landing-hero-visual">
      <img src={inspectionImage} alt="Imagen ilustrativa de mangos en una línea de inspección con cámara industrial." width="1536" height="1024" fetchPriority="high" />
      <div className="landing-hero-visual__scrim" aria-hidden="true" />
      <div className="landing-hero-visual__top" aria-hidden="true">
        <span className="landing-visual-mark"><Icon name="scan" size={18} /> AGROSCAN / VISIÓN</span>
        <span className="landing-visual-dots"><span /><span /><span /></span>
      </div>
      <div className="landing-hero-visual__bottom">
        <span className="landing-visual-status"><span /> Flujo de trabajo</span>
        <div className="landing-visual-flow" aria-label="Captura, análisis asistido y revisión humana">
          <span>01 <strong>Captura</strong></span>
          <Icon name="arrow-right" size={16} />
          <span>02 <strong>Análisis asistido</strong></span>
          <Icon name="arrow-right" size={16} />
          <span>03 <strong>Revisión</strong></span>
        </div>
      </div>
      <figcaption>Imagen conceptual · No representa una instalación o un resultado validado de AgroScan.</figcaption>
    </figure>
  )
}

export function CommercialLanding() {
  return (
    <div className="landing">
      <a className="skip-link" href="#landing-content">Saltar al contenido</a>
      <PublicHeader />
      <main id="landing-content" tabIndex={-1}>
        <section className="landing-hero landing-container" aria-labelledby="landing-title">
          <div className="landing-hero__copy">
            <p className="landing-eyebrow"><span className="landing-eyebrow__dot" /> INTELIGENCIA PARA LA FRUTA</p>
            <h1 id="landing-title">Cada fruta tiene datos.<br /><em>Haz que cuenten.</em></h1>
            <p className="landing-lead">Visión artificial, información IoT y trazabilidad en una plataforma para equipos que necesitan evaluar, revisar y dar seguimiento a sus lotes.</p>
            <div className="landing-actions">
              <a href="#planes" className="landing-button">Explorar planes DEMO <Icon name="arrow-right" size={19} /></a>
              <a href="#como-funciona" className="landing-text-link">Descubre cómo funciona <Icon name="arrow-right" size={18} /></a>
            </div>
            <p className="landing-hero__note"><Icon name="info" size={17} /> Entorno DEMO · Sin tarjetas ni cobros reales.</p>
          </div>
          <HeroVisual />
        </section>

        <div className="landing-capabilities" aria-label="Tecnologías y capacidades de AgroScan">
          <div className="landing-container landing-capabilities__inner">
            <p>UN ECOSISTEMA CONECTADO</p>
            <ul>
              <li><Icon name="scan" size={21} /> Visión artificial</li>
              <li><Icon name="network" size={21} /> Datos IoT</li>
              <li><Icon name="boxes" size={21} /> Gestión por lotes</li>
              <li><Icon name="clipboard" size={21} /> Revisión humana</li>
            </ul>
          </div>
        </div>

        <section id="beneficios" className="landing-benefits landing-container" aria-labelledby="benefits-title" tabIndex={-1}>
          <div className="landing-section-intro">
            <div>
              <p className="landing-eyebrow">POR QUÉ AGROSCAN</p>
              <h2 id="benefits-title">Menos información suelta.<br /><em>Más decisiones conectadas.</em></h2>
            </div>
            <p>Tu operación necesita algo más que imágenes aisladas. Dale estructura al trabajo del lote, desde la captura hasta su revisión.</p>
          </div>
          <div className="landing-benefit-grid">
            {benefits.map(benefit => (
              <article key={benefit.eyebrow} className="landing-benefit-card">
                <div className="landing-benefit-card__top"><span className="landing-icon"><Icon name={benefit.icon} size={25} /></span><span>{benefit.eyebrow}</span></div>
                <h3>{benefit.title}</h3><p>{benefit.description}</p>
                <span className="landing-benefit-card__rule" aria-hidden="true" />
              </article>
            ))}
          </div>
        </section>

        <section id="como-funciona" className="landing-workflow" aria-labelledby="workflow-title" tabIndex={-1}>
          <div className="landing-container landing-workflow__layout">
            <div className="landing-workflow__intro">
              <p className="landing-eyebrow">ASÍ FUNCIONA</p>
              <h2 id="workflow-title">Del lote a la decisión.<br /><em>Sin perder el hilo.</em></h2>
              <p>AgroScan conecta la información de cada etapa. La tecnología asiste; tu equipo mantiene el criterio de revisión.</p>
              <a href="#planes" className="landing-text-link">Ver opciones para mi empresa <Icon name="arrow-right" size={18} /></a>
            </div>
            <div className="landing-workflow__process">
              <ol className="landing-steps">
                {steps.map((step, index) => (
                  <li key={step.title}>
                    <span className="landing-step-number">0{index + 1}</span>
                    <span className="landing-step-icon"><Icon name={step.icon} size={23} /></span>
                    <div><h3>{step.title}</h3><p>{step.description}</p></div>
                  </li>
                ))}
              </ol>
              <p className="landing-workflow__note"><Icon name="info" size={17} /> La demostración no acredita exactitud experimental del modelo ni validación física de dispositivos. Un piloto operativo requiere comprobaciones propias.</p>
            </div>
          </div>
        </section>

        <section id="planes" className="landing-plans landing-container" aria-labelledby="plans-title" tabIndex={-1}>
          <div className="landing-section-intro landing-section-intro--plans">
            <div><p className="landing-eyebrow">PLANES PARA EMPRESAS</p><h2 id="plans-title">El siguiente paso,<br /><em>a tu ritmo.</em></h2></div>
            <p>Explora los planes publicados en el catálogo dinámico. Elige una opción y envía tu solicitud sin iniciar sesión.</p>
          </div>
          <p className="landing-demo-note"><Icon name="info" size={20} /><span><strong>Catálogo y contratación DEMO.</strong> Precios ilustrativos en PEN, no aprobados comercialmente. Solicitar un plan no realiza un cobro ni activa una suscripción.</span></p>
          <PublicPlanCatalog />
          <p className="landing-plans__after">¿Quieres revisar las condiciones en una página aparte? <Link to="/planes">Ver catálogo completo <Icon name="arrow-right" size={16} /></Link></p>
        </section>

        <section className="landing-onboarding landing-container" aria-labelledby="onboarding-title">
          <div className="landing-onboarding__heading"><p className="landing-eyebrow">INCORPORACIÓN CONTROLADA</p><h2 id="onboarding-title">Primero nos conocemos.<br /><em>Después conectamos a tu equipo.</em></h2><p>Una solicitud no crea cuentas con privilegios ni activa servicios automáticamente.</p></div>
          <ol>
            {[
              ['Solicita un plan', 'Envía la información de contacto de tu empresa.'],
              ['Revisión del alta', 'El propietario evalúa la solicitud antes de aprobarla.'],
              ['Invitación al administrador', 'Si se aprueba, se envía una invitación para crear el primer acceso.'],
            ].map(([title, description], index) => <li key={title}><span>0{index + 1}</span><div><h3>{title}</h3><p>{description}</p></div></li>)}
          </ol>
        </section>

        <section id="preguntas" className="landing-faq landing-container" aria-labelledby="faq-title" tabIndex={-1}>
          <div><p className="landing-eyebrow">RESPUESTAS CLARAS</p><h2 id="faq-title">Lo esencial,<br /><em>sin letra pequeña.</em></h2><p>Todo lo que debes saber antes de explorar este entorno de demostración.</p></div>
          <div className="landing-faq__items">{faqs.map(([question, answer]) => <details key={question}><summary><span>{question}</span><Icon name="plus" size={18} /></summary><p>{answer}</p></details>)}</div>
        </section>

        <section className="landing-final landing-container" aria-labelledby="final-title">
          <div className="landing-final__texture" aria-hidden="true" />
          <div><p className="landing-eyebrow">UNA MEJOR VISIÓN DE TU OPERACIÓN</p><h2 id="final-title">La próxima decisión<br />empieza con <em>más contexto.</em></h2><p>Conoce las condiciones DEMO de AgroScan y solicita la revisión del alta de tu empresa.</p></div>
          <Link to="/planes" className="landing-button landing-button--light">Explorar planes <Icon name="arrow-right" size={19} /></Link>
        </section>
      </main>
      <footer className="landing-footer landing-container">
        <div className="landing-footer__brand"><Link to="/" className="public-brand" aria-label="AgroScan, inicio"><span className="public-brand__symbol"><Icon name="leaf" size={23} /></span><strong>AgroScan</strong></Link><p>Visión que conecta información.<br />Trazabilidad para decidir.</p></div>
        <nav aria-label="Enlaces de pie de página"><Link to="/#beneficios">Beneficios</Link><Link to="/#como-funciona">Cómo funciona</Link><Link to="/planes">Planes DEMO</Link><Link to="/planes">Solicitar un plan</Link><Link to="/acceso">Acceso</Link></nav>
        <p className="landing-footer__disclaimer">Entorno de demostración.<br />Sin cobros ni resultados certificados.</p>
      </footer>
      <div className="landing-bottom-note">AgroScan / SaaS de clasificación asistida y trazabilidad de fruta · DEMO</div>
    </div>
  )
}
