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
  const [isPolling, setIsPolling] = useState(false);
  const [showInstallModal, setShowInstallModal] = useState(false);

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

  // Enforce GitHub App Installation
  useEffect(() => {
    if (status?.authenticated && status?.app_installed === false) {
      setShowInstallModal(true);
    } else {
      setShowInstallModal(false);
    }
  }, [status]);

  // Polling logic
  useEffect(() => {
    if (!isPolling) return;
    const startTime = Date.now();
    const maxDuration = 2 * 60 * 1000;

    const interval = setInterval(async () => {
      try {
        if (Date.now() - startTime > maxDuration) {
          clearInterval(interval);
          setIsPolling(false);
          console.log("Polling stopped after 2 minutes.");
          return;
        }

        const authStatus = await integrationApi.verifyAuth();
        if (authStatus.app_installed) {
          setStatus(authStatus);
          setIsPolling(false);
          setShowInstallModal(false);

          window.location.reload();
        }
      } catch (err) {
        console.error("Polling failed", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [isPolling]);

  const handleInstallClick = () => {
    const APP_URL = "https://github.com/apps/builddefection";
    window.open(APP_URL, "_blank");
    setIsPolling(true);
  };

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
      {showInstallModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex flex-col items-center text-center">
              <div className="mb-4 rounded-full bg-blue-100 p-3 dark:bg-blue-900/30">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-8 w-8 text-blue-600 dark:text-blue-400"
                >
                  <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
                  <path d="M9 18c-4.51 2-5-2-7-2" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
                GitHub App Required
              </h2>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                To use BuildGuard, you must install our GitHub App. This allows us
                to sync your repositories and analyze build risks.
              </p>
            </div>
            <div className="space-y-3">
              <button
                onClick={handleInstallClick}
                className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 dark:bg-slate-50 dark:text-slate-900 dark:hover:bg-slate-200"
              >
                {isPolling ? "Checking installation..." : "Install GitHub App"}
              </button>
              {isPolling && (
                <p className="text-center text-xs text-muted-foreground animate-pulse">
                  Waiting for installation to complete...
                </p>
              )}
            </div>
          </div>
        </div>
      )}
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
