'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { BadgeCheck, Building2, BarChart, Github, Home, PlugZap, ShieldAlert, SlidersHorizontal, Workflow } from 'lucide-react'

const navigation = [
  {
    label: 'Tổng quan',
    href: '/dashboard',
    icon: Home,
  },
  {
    label: 'Builds',
    href: '/builds',
    icon: BarChart,
    hint: 'In development',
  },
  {
    label: 'Pipeline',
    href: '/pipeline',
    icon: Workflow,
  },
  {
    label: 'Admin Center',
    href: '/admin',
    icon: SlidersHorizontal,
  },
  {
    label: 'Cảnh báo',
    href: '/alerts',
    icon: ShieldAlert,
    disabled: true,
    hint: 'Đang phát triển',
  },
  {
    label: 'Tích hợp GitHub',
    href: '/integrations/github',
    icon: Github,
  },
  {
    label: 'Tổ chức',
    href: '/organization',
    icon: Building2,
    disabled: true,
    hint: 'Đang phát triển',
  },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <div className="flex h-full flex-col border-r bg-white/70 backdrop-blur dark:bg-slate-950/90">
      <div className="flex items-center gap-2 border-b px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white">
          <BadgeCheck className="h-6 w-6" />
        </div>
        <div>
          <p className="text-lg font-semibold">BuildGuard</p>
          <p className="text-xs text-muted-foreground">DevSecOps Insights</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive = pathname.startsWith(item.href)
          const Icon = item.icon

          return (
            <Link
              key={item.href}
              href={item.disabled ? '#' : item.href}
              className={cn(
                'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                item.disabled
                  ? 'cursor-not-allowed text-muted-foreground/60'
                  : 'hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-slate-800',
                isActive && !item.disabled ? 'bg-blue-600 text-white hover:text-white' : '',
              )}
              aria-disabled={item.disabled}
              onClick={(event) => {
                if (item.disabled) {
                  event.preventDefault()
                }
              }}
            >
              <Icon className={cn('h-4 w-4', isActive && !item.disabled ? 'text-white' : 'text-muted-foreground')} />
              <span className="flex-1">{item.label}</span>
              {item.disabled ? (
                <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold uppercase text-slate-600 group-hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400">
                  Soon
                </span>
              ) : null}
              {item.hint ? (
                <span className="sr-only">{item.hint}</span>
              ) : null}
            </Link>
          )
        })}
      </nav>

      <div className="border-t px-4 py-4 text-xs text-muted-foreground">
        <p className="font-semibold text-foreground">BuildGuard Thesis 2025</p>
        <p className="mt-1 leading-relaxed">
          This prototype focuses on observing builds and extracting features for later analysis.
        </p>
        <p className="mt-2 flex items-center gap-2 text-muted-foreground/80">
          <PlugZap className="h-4 w-4" />
          GitHub OAuth provides read-only access to collect analytics data.
        </p>
      </div>
    </div>
  )
}
