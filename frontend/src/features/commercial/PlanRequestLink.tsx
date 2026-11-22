import { Link } from 'react-router-dom'
import { Icon } from '../../components/layout/Icon'
import type { Plan } from './commercialApi'

export function PlanRequestLink({ plan, className = 'action-button action-button--primary' }: { plan: Plan; className?: string }) {
  return <Link className={className} aria-label={`Solicitar plan ${plan.name}`} to={`/solicitar?plan=${plan.id}`}>Solicitar plan <Icon name="arrow-right" size={18} /></Link>
}
