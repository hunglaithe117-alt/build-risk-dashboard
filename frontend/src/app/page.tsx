"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/contexts/auth-context";

export default function RootRedirect() {
  const router = useRouter();
  const { authenticated, loading } = useAuth();

  useEffect(() => {
    if (loading) {
      return;
    }

    router.replace(authenticated ? "/dashboard" : "/login");
  }, [authenticated, loading, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
      <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
        <span>{loading ? "Checking session..." : "Redirecting..."}</span>
      </div>
    </main>
  );
}
