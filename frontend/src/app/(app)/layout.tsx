 'use client'

import { AppShell } from '@/components/layout/app-shell'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { integrationApi } from '@/lib/api'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()

  useEffect(() => {
    const check = async () => {
      try {
        const status = await integrationApi.getGithubStatus()
        if (!status.connected) {
          router.replace('/login')
        }
      } catch (err) {
        console.error('Failed to verify auth status:', err)
      }
    }

    void check()
  }, [router])
  return <AppShell>{children}</AppShell>
}
