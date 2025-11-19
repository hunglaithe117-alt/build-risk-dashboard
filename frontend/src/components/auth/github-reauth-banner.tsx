'use client'

import { AlertCircle } from 'lucide-react'
import { useAuth } from '@/contexts/auth-context'
import { integrationApi } from '@/lib/api'
import { useState } from 'react'

export function GithubReauthBanner() {
  const { needsGithubReauth, status } = useAuth()
  const [isReconnecting, setIsReconnecting] = useState(false)

  if (!needsGithubReauth) {
    return null
  }

  const handleReconnect = async () => {
    setIsReconnecting(true)
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth(
        window.location.pathname
      )
      window.location.href = authorize_url
    } catch (error) {
      console.error('Failed to start GitHub OAuth:', error)
      setIsReconnecting(false)
    }
  }

  const getMessage = () => {
    const reason = status?.reason
    switch (reason) {
      case 'github_token_expired':
        return 'Your GitHub access token has expired. Please reconnect your GitHub account to continue.'
      case 'github_token_revoked':
        return 'Your GitHub access token has been revoked. Please reconnect your GitHub account to continue.'
      case 'no_github_identity':
        return 'GitHub account not connected. Please connect your GitHub account to access repository features.'
      default:
        return 'GitHub authentication required. Please connect your GitHub account.'
    }
  }

  return (
    <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-4">
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <AlertCircle className="h-5 w-5 text-yellow-400" />
        </div>
        <div className="ml-3 flex-1">
          <p className="text-sm text-yellow-700">{getMessage()}</p>
          <div className="mt-2">
            <button
              onClick={handleReconnect}
              disabled={isReconnecting}
              className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-100 hover:bg-yellow-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isReconnecting ? 'Redirecting...' : 'Reconnect GitHub'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
