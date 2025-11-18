"use client"

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { integrationApi } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const check = async () => {
      try {
        const data = await integrationApi.getGithubStatus()
        // If integration already connected we consider the user logged-in and route
        if (data.connected) {
          router.replace('/dashboard')
          return
        }
      } catch (err) {
        console.error(err)
        setError('Unable to check login status. Please verify backend.')
      } finally {
        setLoading(false)
      }
    }
    check()
  }, [router])

  const handleLogin = async () => {
    setError(null)
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth('/')
      // Redirect user to GitHub OAuth
      window.location.href = authorize_url
    } catch (err) {
      console.error(err)
      setError('Unable to initiate GitHub OAuth. Check configuration.')
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Checking login status...</CardTitle>
              <CardDescription>Contact backend to verify status.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Please wait...</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <main className="min-h-screen flex items-center justify-center">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Log in</CardTitle>
          <CardDescription>Sign in using GitHub OAuth to start using BuildGuard.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <p className="text-sm text-muted-foreground">BuildGuard uses GitHub OAuth (read-only) for login.</p>
            <div className="flex items-center justify-center pt-4">
              <Button onClick={handleLogin} size="lg">Sign in with GitHub</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}
