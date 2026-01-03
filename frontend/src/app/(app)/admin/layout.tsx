'use client'

import { type ReactNode, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'

import { useAuth } from '@/contexts/auth-context'

// /admin routes are now admin-only (monitoring, users, settings)
// /projects and /repositories have their own layouts

export default function AdminLayout({ children }: { children: ReactNode }) {
    const router = useRouter();
    const { authenticated, loading, user } = useAuth();

    const userRole = user?.role;
    const isAdmin = userRole === "admin";

    useEffect(() => {
        if (loading) return;

        if (!authenticated) {
            router.replace("/login");
            return;
        }

        // All /admin/* routes are admin-only now
        if (!isAdmin) {
            router.replace("/overview");
        }
    }, [authenticated, loading, isAdmin, userRole, router]);

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

    // Show loading while redirecting
    if (!authenticated || !isAdmin) {
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
