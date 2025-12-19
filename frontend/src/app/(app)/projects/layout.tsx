'use client';

import { type ReactNode, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/contexts/auth-context';

/**
 * Layout for /projects route.
 * Accessible by Admin and Guest roles (dataset managers).
 */
export default function ProjectsLayout({ children }: { children: ReactNode }) {
    const router = useRouter();
    const { authenticated, loading, user } = useAuth();

    const userRole = user?.role;
    const isAdmin = userRole === 'admin';
    const isGuest = userRole === 'guest';
    const hasProjectsAccess = isAdmin || isGuest;

    useEffect(() => {
        if (loading) return;

        if (!authenticated) {
            router.replace('/login');
            return;
        }

        if (!hasProjectsAccess) {
            // Regular users don't have access to projects
            router.replace('/overview');
        }
    }, [authenticated, loading, hasProjectsAccess, router]);

    if (loading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                    <span>Checking permissions…</span>
                </div>
            </div>
        );
    }

    if (!authenticated || !hasProjectsAccess) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                    <span>Redirecting…</span>
                </div>
            </div>
        );
    }

    return <>{children}</>;
}
