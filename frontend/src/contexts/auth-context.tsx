"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { integrationApi } from "@/lib/api";
import type { AuthVerifyResponse } from "@/types";

interface AuthContextValue {
  status: AuthVerifyResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  isGithubConnected: boolean;
  needsGithubReauth: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthVerifyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const authStatus = await integrationApi.verifyAuth();
      setStatus(authStatus);
      setError(null);
    } catch (err: any) {
      console.error("Failed to verify auth status", err);

      // Check if it's a GitHub token error
      const authError = err?.response?.headers?.["x-auth-error"];
      if (
        authError === "github_token_expired" ||
        authError === "github_token_revoked" ||
        authError === "github_not_connected"
      ) {
        // User is authenticated but GitHub token is invalid
        setStatus({
          authenticated: true,
          github_connected: false,
          reason: authError,
        });
        setError(`GitHub authentication required: ${authError}`);
      } else if (err.response?.status === 401) {
        // Standard unauthenticated state - not an error
        setStatus({ authenticated: false, github_connected: false });
        setError(null);
      } else {
        // Complete authentication failure (network error, 500, etc.)
        setStatus({ authenticated: false, github_connected: false });
        setError("Unable to verify authentication status.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Determine if GitHub needs re-authentication
  const needsGithubReauth = useMemo(() => {
    if (!status?.authenticated) return false;
    if (status.github_connected === false) return true;
    const reason = status.reason;
    return (
      reason === "github_token_expired" ||
      reason === "github_token_revoked" ||
      reason === "no_github_identity"
    );
  }, [status]);

  const isGithubConnected = useMemo(() => {
    return status?.authenticated === true && status?.github_connected === true;
  }, [status]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      loading,
      error,
      refresh,
      isGithubConnected,
      needsGithubReauth,
    }),
    [error, loading, refresh, status, isGithubConnected, needsGithubReauth]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  const authenticated = Boolean(context.status?.authenticated);
  const user = context.status?.user ?? null;
  const githubProfile = context.status?.github ?? null;

  return {
    ...context,
    authenticated,
    user,
    githubProfile,
  };
}
