import { createContext, type ReactNode } from 'react'

export const SidebarSessionContext = createContext<{
  actions: ReactNode; organizationSelector?: ReactNode
} | null>(null)
