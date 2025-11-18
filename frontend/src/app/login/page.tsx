"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { integrationApi } from "@/lib/api";
import { useAuth } from "@/contexts/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { authenticated, loading: authLoading, error: authError } = useAuth();
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (authenticated) {
      router.replace("/dashboard");
    }
  }, [authenticated, authLoading, router]);

  const handleLogin = async () => {
    setError(null);
    setActionLoading(true);
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth("/");
      window.location.href = authorize_url;
    } catch (err) {
      console.error(err);
      setError("Unable to initiate GitHub OAuth. Check configuration.");
    } finally {
      setActionLoading(false);
    }
  };

  const combinedError = error ?? authError;

  return (
    <main className="min-h-screen flex items-center justify-center">
      <Card className="w-full max-w-lg">
        <CardHeader className="flex flex-col items-center text-center">
          <CardTitle>Log in</CardTitle>
          <CardDescription>
            Sign in using GitHub OAuth to start using BuildGuard.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center">
          <div className="flex flex-col items-center justify-center space-y-4 w-full">
            {combinedError ? (
              <p className="text-sm text-red-600 text-center">{combinedError}</p>
            ) : null}
            <div className="flex items-center justify-center pt-4 w-full">
              <Button
                onClick={handleLogin}
                size="lg"
                disabled={authLoading || actionLoading}
              >
                {actionLoading || authLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {actionLoading ? "Signing in..." : "Checking..."}
                  </>
                ) : (
                  "Sign in with GitHub"
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
