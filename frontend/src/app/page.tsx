"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { integrationApi } from "@/lib/api";

export default function RootRedirect() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const check = async () => {
      try {
        const status = await integrationApi.getGithubStatus();
        if (status.connected) {
          router.replace("/dashboard");
        } else {
          router.replace("/login");
        }
      } catch (err) {
        console.error("Failed to verify integration status:", err);
        router.replace("/login");
      } finally {
        setChecking(false);
      }
    };

    void check();
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
      {checking ? (
        <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          <span>Đang chuyển hướng...</span>
        </div>
      ) : null}
    </main>
  );
}
