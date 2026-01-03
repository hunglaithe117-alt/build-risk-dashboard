'use client'

import { useEffect, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/contexts/auth-context'

interface RequireViewerProps {
    children: ReactNode
    fallbackPath?: string
}

/**
 * Component that requires viewer role (admin or user) to view its children.
 * Redirects non-viewer users to the fallback path (default: /overview).
 *
 * Use this for read-only pages that both admin and user should access.
 */
export function RequireViewer({ children, fallbackPath = '/overview' }: RequireViewerProps) {
    const router = useRouter()
    const { authenticated, loading, user } = useAuth()

    const isViewer = user?.role === 'admin' || user?.role === 'user'

    useEffect(() => {
        if (loading) return

        if (!authenticated) {
            router.replace('/login')
            return
        }

        if (!isViewer) {
            router.replace(fallbackPath)
        }
    }, [authenticated, loading, isViewer, router, fallbackPath])

    // Show loading while checking auth
    if (loading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                    <span>Checking permissions…</span>
                </div>
            </div>
        )
    }

    // Show loading while redirecting non-viewer
    if (!authenticated || !isViewer) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                    <span>Redirecting…</span>
                </div>
            </div>
        )
    }

    return <>{children}</>
}
