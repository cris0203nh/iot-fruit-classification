import type { ReactNode, SVGProps } from 'react'

export type IconName =
  | 'leaf'
  | 'home'
  | 'scan'
  | 'history'
  | 'network'
  | 'chart'
  | 'boxes'
  | 'settings'
  | 'menu'
  | 'close'
  | 'plus'
  | 'alert'
  | 'camera'
  | 'scale'
  | 'database'
  | 'arrow-right'
  | 'info'
  | 'clipboard'
  | 'clock'

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'children'> {
  name: IconName
  size?: number
}

export function Icon({ name, size = 20, ...props }: IconProps) {
  const paths: Record<IconName, ReactNode> = {
    leaf: <><path d="M20 4c-7 0-13 3-15 9-1.5 4.5 1.5 8 5.5 8 6.5 0 9.5-8.5 9.5-17Z" /><path d="M4 21c2.8-5.2 6.3-8.6 11-11" /></>,
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v12h14V9" /><path d="M9 21v-7h6v7" /></>,
    scan: <><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3" /><circle cx="12" cy="12" r="4" /></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></>,
    network: <><rect x="2" y="2" width="6" height="6" rx="1.5" /><rect x="16" y="2" width="6" height="6" rx="1.5" /><rect x="9" y="16" width="6" height="6" rx="1.5" /><path d="M8 5h8M5 8v5l7 3m7-8v5l-7 3" /></>,
    chart: <><path d="M4 20V12M10 20V4M16 20v-8M22 20v-5" /></>,
    boxes: <><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z" /><path d="m4 6.5 8 5 8-5M12 11.5V22" /></>,
    settings: <><path d="M10 3h4l.7 2.3 2 .9 2.2-1 2.6 3-1.4 2 .2 2.1 1.7 1.6-2 3.5-2.5-.3-1.6 1.3-.5 2.5h-4l-.7-2.3-2-.9-2.2 1-2.6-3 1.4-2-.2-2.1-1.7-1.6 2-3.5 2.5.3 1.6-1.3L10 3Z" /><circle cx="12" cy="12" r="3" /></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="M5 5 19 19M19 5 5 19" />,
    plus: <path d="M12 5v14M5 12h14" />,
    alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
    camera: <><rect x="3" y="6" width="18" height="14" rx="2" /><path d="m7 6 2-3h6l2 3" /><circle cx="12" cy="13" r="3" /></>,
    scale: <><path d="M4 20h16M7 20l1-11h8l1 11M12 9V5" /><path d="M9 5h6M11 13h2" /></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0" /></>,
    'arrow-right': <path d="M4 12h16m-7-7 7 7-7 7" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
    clipboard: <><rect x="5" y="4" width="14" height="18" rx="2" /><path d="M9 4.5h6M9 11h6M9 15h6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l4 2" /></>,
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {paths[name]}
    </svg>
  )
}
