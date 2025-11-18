'use client'

import { useEffect, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { useRouter } from 'next/navigation'

import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/contexts/auth-context'

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter()
  const { authenticated, loading } = useAuth()

  useEffect(() => {
    if (loading) {
      return
    }

    if (!authenticated) {
      router.replace('/login')
    }
  }, [authenticated, loading, router])

  if (loading || !authenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          <span>{loading ? 'Checking session…' : 'Redirecting to login…'}</span>
        </div>
      </div>
    )
  }

  return <AppShell>{children}</AppShell>
}
