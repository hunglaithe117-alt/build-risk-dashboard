'use client'

import { useEffect, useMemo, useState } from 'react'
import { Bell, LogOut, Menu, Settings } from 'lucide-react'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'

import { integrationApi, usersApi } from '@/lib/api'
import type { UserAccount } from '@/types'
import { useAuth } from '@/contexts/auth-context'

interface TopbarProps {
  onToggleSidebar?: () => void
}

export function Topbar({ onToggleSidebar }: TopbarProps) {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState<UserAccount | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  const { authenticated, loading: authLoading, githubProfile, refresh } = useAuth()

  useEffect(() => {
    if (authLoading || !authenticated) {
      return
    }

    const fetchProfile = async () => {
      try {
        const userData = await usersApi.getCurrentUser()
        setUser(userData)
      } catch (err) {
        console.error('Unable to load current user profile', err)
      }
    }

    void fetchProfile()
  }, [authenticated, authLoading])

  const initials = useMemo(() => {
    if (user?.name) {
      return user.name
        .split(' ')
        .filter(Boolean)
        .map((part) => part[0]?.toUpperCase())
        .slice(0, 2)
        .join('')
    }
    return user?.email?.[0]?.toUpperCase() ?? '?'
  }, [user])

  const displayName = user?.name ?? user?.email ?? 'Not signed in'
  const displayRole = user?.role === 'admin' ? 'admin' : 'user'

  const pageTitle = useMemo(() => {
    if (pathname?.startsWith('/datasets')) return 'Projects / Datasets'
    if (pathname?.startsWith('/admin/repos')) return 'Repositories'
    if (pathname?.startsWith('/dashboard')) return 'Overview'
    if (pathname?.startsWith('/admin/pipeline')) return 'Pipeline'
    return 'Workspace'
  }, [pathname])

  const handleLogout = async () => {
    if (signingOut) return
    setSigningOut(true)
    try {
      await integrationApi.logout()
    } catch (err) {
      console.error('Failed to logout', err)
    } finally {
      await refresh()
      router.replace('/login')
      setSigningOut(false)
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b bg-white/70 px-4 md:px-6 backdrop-blur dark:bg-slate-950/90">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800 lg:hidden"
          aria-label="Toggle navigation"
          onClick={onToggleSidebar}
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-foreground">{pageTitle}</h1>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3">
          <button
            className="rounded-full p-2 text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
            aria-label="Notifications"
            type="button"
          >
            <Bell className="h-5 w-5" />
          </button>
          <button
            className="rounded-full p-2 text-muted-foreground transition hover:bg-slate-100 hover:text-blue-600 dark:hover:bg-slate-800"
            aria-label="Settings"
            type="button"
          >
            <Settings className="h-5 w-5" />
          </button>
        </div>

        <div className="flex items-center gap-3 rounded-xl border px-3 py-2">
          <div className="relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-slate-200 text-xs font-semibold uppercase text-slate-600">
            {githubProfile?.avatar_url ? (
              <Image
                src={githubProfile.avatar_url}
                alt={displayName}
                fill
                className="object-cover"
                sizes="32px"
              />
            ) : (
              initials
            )}
          </div>
          <div>
            <p className="text-sm font-semibold">{displayName}</p>
            <p className="text-xs text-muted-foreground uppercase">{displayRole}</p>
          </div>
          <button
            className="rounded-full border border-slate-200 p-2 text-muted-foreground transition hover:bg-red-50 hover:text-red-600 dark:border-slate-700 dark:hover:bg-red-900/30 dark:hover:text-red-400"
            aria-label="Sign out"
            type="button"
            disabled={signingOut}
            onClick={handleLogout}
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
