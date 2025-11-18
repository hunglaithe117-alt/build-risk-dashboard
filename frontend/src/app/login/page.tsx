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

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await integrationApi.getGithubStatus();
        if (data.connected) {
          router.replace("/dashboard");
          return;
        }
      } catch (err) {
        console.error(err);
        setError("Unable to check login status. Please verify backend.");
      } finally {
        setLoading(false);
      }
    };
    check();
  }, [router]);

  const handleLogin = async () => {
    setError(null);
    setActionLoading(true);
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth("/");
      // Redirect user to GitHub OAuth
      window.location.href = authorize_url;
    } catch (err) {
      console.error(err);
      setError("Unable to initiate GitHub OAuth. Check configuration.");
    } finally {
      setActionLoading(false);
    }
  };

  // NOTE: Do not early-return while `loading` is true; we show the login
  // UI immediately and only indicate the loading state on the sign-in
  // button (as requested).

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
            {error ? (
              <p className="text-sm text-red-600 text-center">{error}</p>
            ) : null}
            <div className="flex items-center justify-center pt-4 w-full">
              <Button
                onClick={handleLogin}
                size="lg"
                // disable while initial check is running or while the OAuth
                // redirect is being prepared.
                disabled={loading || actionLoading}
              >
                {actionLoading || loading ? (
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
