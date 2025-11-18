'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { integrationApi } from '@/lib/api'

type AuthStatus = Awaited<ReturnType<typeof integrationApi.verifyAuth>>

interface AuthContextValue {
  status: AuthStatus | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const authStatus = await integrationApi.verifyAuth()
      setStatus(authStatus)
      setError(null)
    } catch (err) {
      console.error('Failed to verify auth status', err)
      setStatus({ authenticated: false } as AuthStatus)
      setError('Unable to verify authentication status.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      loading,
      error,
      refresh,
    }),
    [error, loading, refresh, status]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  const authenticated = Boolean(context.status?.authenticated)
  const user = context.status?.user ?? null
  const githubProfile = context.status?.github ?? null

  return {
    ...context,
    authenticated,
    user,
    githubProfile,
  }
}
