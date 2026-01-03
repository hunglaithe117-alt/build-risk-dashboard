'use client';

import { type ReactNode, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/contexts/auth-context';

/**
 * Layout for /my-repos route.
 * User (org member) only - view their assigned repositories.
 */
export default function MyReposLayout({ children }: { children: ReactNode }) {
    const router = useRouter();
    const { authenticated, loading, user } = useAuth();

    const userRole = user?.role;
    const isUser = userRole === 'user';
    const isAdmin = userRole === 'admin';
    // Admin can also view my-repos for testing purposes
    const hasAccess = isUser || isAdmin;

    useEffect(() => {
        if (loading) return;

        if (!authenticated) {
            router.replace('/login');
            return;
        }

        if (!hasAccess) {
            // Non-members redirect to overview
            router.replace('/overview');
        }
    }, [authenticated, loading, hasAccess, userRole, router]);

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

    if (!authenticated || !hasAccess) {
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
