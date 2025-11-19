'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/auth-context'
import { integrationApi } from '@/lib/api'

export interface UseGithubTokenResult {
  isValid: boolean
  isLoading: boolean
  error: string | null
  needsReauth: boolean
  reconnect: () => Promise<void>
}

/**
 * Hook to check and manage GitHub token status
 */
export function useGithubToken(): UseGithubTokenResult {
  const { isGithubConnected, needsGithubReauth, status } = useAuth()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reconnect = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth(
        window.location.pathname
      )
      window.location.href = authorize_url
    } catch (err: any) {
      setError(err?.message || 'Failed to start GitHub authentication')
      setIsLoading(false)
    }
  }

  return {
    isValid: isGithubConnected,
    isLoading,
    error,
    needsReauth: needsGithubReauth,
    reconnect,
  }
}

/**
 * Hook that throws an error if GitHub token is not valid
 * Useful for pages that require GitHub access
 */
export function useRequireGithubToken() {
  const { isGithubConnected, needsGithubReauth, loading } = useAuth()

  useEffect(() => {
    if (!loading && !isGithubConnected && needsGithubReauth) {
      // Optionally redirect to a connection page
      console.warn('GitHub token is required but not available')
    }
  }, [isGithubConnected, needsGithubReauth, loading])

  return {
    isGithubConnected,
    needsGithubReauth,
    loading,
  }
}
