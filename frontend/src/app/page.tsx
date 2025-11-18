"use client"

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { integrationApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Github, ShieldCheck, Workflow, Zap } from 'lucide-react'

export default function Home() {
  const router = useRouter()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const check = async () => {
      try {
        const status = await integrationApi.getGithubStatus()
        if (status.connected) {
          router.replace('/dashboard')
        } else {
          router.replace('/login')
        }
      } catch (err) {
        console.error(err)
        // Leave on homepage if check fails
      } finally {
        setChecking(false)
      }
    }

    void check()
  }, [router])
  if (checking) return null

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <span className="inline-flex items-center gap-2 rounded-full bg-blue-100 px-4 py-1 text-sm font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            BuildGuard · DevSecOps Risk Prediction Platform
          </span>
          <h1 className="mt-6 text-5xl font-bold leading-tight text-slate-900 dark:text-white">
            Giám sát CI/CD và dự báo rủi ro builds trong một dashboard
          </h1>
            <p className="mt-4 text-xl text-gray-600 dark:text-gray-300 max-w-3xl mx-auto">
            BuildGuard connects to GitHub using read-only OAuth, collecting workflow runs and commits,
              collecting workflow runs and commit metadata for later feature extraction. The ML prediction
              layer is currently disabled — only data collection and feature extraction remain active.
          </p>
        </div>

        <div className="text-center space-x-4">
          <Link href="/dashboard">
            <Button size="lg" className="text-lg px-8">
              Open Dashboard
            </Button>
          </Link>
          <Link href="/integrations/github">
            <Button size="lg" variant="outline" className="text-lg px-8">
              Connect GitHub OAuth
            </Button>
          </Link>
        </div>

        <div className="mt-16 grid md:grid-cols-3 gap-6">
          <Card className="border border-blue-100 shadow-sm dark:border-blue-900/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-5 w-5 text-blue-600" />
                Thu thập dữ liệu CI/CD
              </CardTitle>
              <CardDescription>
                Đồng bộ commits, workflow runs và artifacts từ GitHub Actions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Read-only OAuth; no GitHub App required · extensible to other CI platforms.
              </p>
            </CardContent>
          </Card>

          <Card className="border border-emerald-100 shadow-sm dark:border-emerald-900/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-emerald-600" />
                Security & quality analysis
              </CardTitle>
              <CardDescription>
                Aggregate internal quality gate metrics and security alerts
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Theo dõi bugs, coverage, technical debt và vulnerabilities cho từng build.
              </p>
            </CardContent>
          </Card>

          <Card className="border border-purple-100 shadow-sm dark:border-purple-900/40">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-purple-600" />
                Feature Extraction
              </CardTitle>
              <CardDescription>
                Build-level features (commits, churn, tests, coverage, logs) collected for analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                BuildGuard currently focuses on building a robust data pipeline — you can connect GitHub and
                extract commit/workflow metadata. Prediction model integration will be re-enabled later.
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-16 border-t pt-12">
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold mb-3">Key Features</h3>
              <ul className="space-y-2 text-gray-600 dark:text-gray-400">
                <li>✓ GitHub OAuth read-only · no write permissions or secrets required.</li>
                <li>✓ Multi-source telemetry: workflow runs, commit diffs, logs, artifacts.</li>
                <li>✓ Security & quality: internal metrics combined with feature extraction.</li>
                <li>✓ Visual dashboard: trend charts, heatmap, build-level detail.</li>
                <li>✓ AI-ready: clean data pipeline for future model integration.</li>
              </ul>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-3">Công nghệ</h3>
              <ul className="space-y-2 text-gray-600 dark:text-gray-400">
                <li>
                  <Github className="mr-2 inline h-4 w-4" />
                  GitHub REST API với scopes: read:user, repo, read:org, workflow.
                </li>
                <li>🎨 Frontend: Next.js 14, Tailwind, shadcn/ui, Recharts.</li>
                <li>⚙️ Backend (prototype): FastAPI, background worker, MongoDB.</li>
                <li>🧠 ML: prediction features are disabled for now; the pipeline focuses on feature extraction.</li>
                <li>🐳 DevOps: Docker Compose, GitHub Actions for CI, and infrastructure security.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
