'use client'

import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'
import { Sidebar } from './sidebar'
import { Topbar } from './topbar'

interface AppShellProps {
  children: React.ReactNode
}

const SIDEBAR_COLLAPSED_KEY = 'sidebar-collapsed'

export function AppShell({ children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mounted, setMounted] = useState(false)

  // Load collapsed state from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    if (stored !== null) {
      setSidebarCollapsed(stored === 'true')
    }
    setMounted(true)
  }, [])

  const handleToggleSidebar = () => {
    const newValue = !sidebarCollapsed
    setSidebarCollapsed(newValue)
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(newValue))
  }

  const closeMobileNav = () => setMobileNavOpen(false)

  // Determine grid columns based on collapsed state
  // lg (Laptop 1024-1279px): Collapsible sidebar (64px or 280px)
  // xl (Desktop 1280px+): Persistent full sidebar (280px)
  const gridCols = sidebarCollapsed
    ? 'lg:grid-cols-[64px_1fr]'
    : 'lg:grid-cols-[64px_1fr] xl:grid-cols-[280px_1fr]'

  return (
    <div className={cn(
      "grid h-screen w-full overflow-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50 transition-all duration-200",
      mounted ? gridCols : 'lg:grid-cols-[64px_1fr] xl:grid-cols-[280px_1fr]'
    )}>
      {/* Laptop Sidebar - Icon only (lg breakpoint: 1024px+) */}
      <aside className={cn(
        "hidden lg:block h-screen overflow-hidden border-r dark:border-slate-800",
        sidebarCollapsed ? "" : "xl:hidden"
      )}>
        <Sidebar collapsed onToggleCollapse={handleToggleSidebar} />
      </aside>

      {/* Desktop Sidebar - Full (xl breakpoint: 1280px+) */}
      <aside className={cn(
        "hidden h-screen overflow-hidden border-r dark:border-slate-800",
        sidebarCollapsed ? "" : "xl:block"
      )}>
        <Sidebar onToggleCollapse={handleToggleSidebar} />
      </aside>

      {/* Mobile Sidebar - Overlay (below lg breakpoint) */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-72 transform border-r bg-white shadow-xl transition-transform duration-200 ease-in-out dark:border-slate-800 dark:bg-slate-950 lg:hidden',
          mobileNavOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <Sidebar />
      </div>
      {mobileNavOpen ? (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={closeMobileNav}
          aria-hidden="true"
        />
      ) : null}

      {/* Main Content Area */}
      <div className="flex flex-col h-screen overflow-hidden">
        <Topbar onToggleSidebar={() => setMobileNavOpen((prev) => !prev)} />
        <main className="flex-1 overflow-y-auto bg-slate-50 p-3 lg:p-4 xl:p-6 dark:bg-slate-950">
          <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-3 lg:gap-4 xl:gap-6">{children}</div>
        </main>
      </div>
    </div>
  )
}

