import { Icon, type IconName } from './layout/Icon'
import './MetricCard.css'

export function MetricCard({ label, value, icon, detail, tone = 'green' }: {
  label: string; value: string | number; icon: IconName; detail: string; tone?: 'green' | 'blue' | 'amber'
}) {
  return <article className={`executive-metric executive-metric--${tone}`}>
    <div className="executive-metric__head"><span>{label}</span><span className="executive-metric__icon"><Icon name={icon} size={21} /></span></div>
    <strong>{value}</strong><p>{detail}</p>
  </article>
}
