'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, PlugZap, RefreshCw, ShieldCheck } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { pipelineApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { PipelineStage, PipelineStatus } from '@/types'

const STATUS_BADGE: Record<PipelineStage['status'], string> = {
  completed: 'bg-emerald-100 text-emerald-700',
  running: 'bg-blue-100 text-blue-700',
  pending: 'bg-slate-100 text-slate-600',
  blocked: 'bg-red-100 text-red-700',
}

const STATUS_LABEL: Record<PipelineStage['status'], string> = {
  completed: 'Completed',
  running: 'Running',
  pending: 'Pending',
  blocked: 'Blocked',
}

export default function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await pipelineApi.getStatus()
        setStatus(response)
      } catch (err) {
        console.error(err)
        setError('Unable to load pipeline status. Check backend `/api/pipeline/status`.')
      } finally {
        setLoading(false)
      }
    }

    fetchStatus()
  }, [])

  const normalizationStage = useMemo(
    () => status?.stages.find((stage) => stage.key === 'normalization'),
    [status],
  )

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading pipeline...</CardTitle>
            <CardDescription>Retrieving preprocessing/normalization status.</CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Please wait a moment.
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error || !status) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
          <CardHeader>
            <CardTitle className="text-red-700 dark:text-red-300">Pipeline not ready</CardTitle>
            <CardDescription>{error ?? 'No data received from API.'}</CardDescription>
          </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
            Check the FastAPI service and ensure MongoDB has sample data.
          </CardContent>
        </Card>
      </div>
    )
  }

  const lastRun = new Date(status.last_run).toLocaleString('en-US')
  const nextRun = new Date(status.next_run).toLocaleString('en-US')

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <PipelineMetric
          icon={<RefreshCw className="h-5 w-5 text-blue-500" />}
          label="Normalized feature vectors"
          value={status.normalized_features.toLocaleString('en-US')}
          sublabel="128 features / build · used for analysis (model disabled)"
        />
        <PipelineMetric
          icon={<AlertTriangle className="h-5 w-5 text-amber-500" />}
          label="Pending repositories"
          value={status.pending_repositories}
          sublabel="Prioritize repos that are not fully imported"
        />
        <PipelineMetric
          icon={<ShieldCheck className="h-5 w-5 text-emerald-500" />}
          label="Anomalies detected"
          value={status.anomalies_detected}
          sublabel="Used for manual review"
        />
        <PipelineMetric
          icon={<PlugZap className="h-5 w-5 text-purple-500" />}
          label="Last run"
          value={lastRun}
          sublabel={`Next: ${nextRun}`}
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Data pipeline</CardTitle>
              <CardDescription>Stage-by-stage pipeline status</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status.stages.map((stage) => (
              <StageRow key={stage.key} stage={stage} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Normalization readiness</CardTitle>
            <CardDescription>Bottlenecks & recommended actions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {normalizationStage ? (
              <>
                <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                  <p className="text-xs uppercase font-semibold text-amber-600 dark:text-amber-300">Progress</p>
                  <p className="text-lg font-semibold">{normalizationStage.percent_complete}% complete</p>
                  <p className="text-xs text-muted-foreground">
                    {normalizationStage.items_processed?.toLocaleString('en-US')} /{' '}
                    {Math.round(status.normalized_features / 128).toLocaleString('en-US')} processed builds
                  </p>
                </div>
                <ul className="space-y-3">
                  <li className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                    <p className="font-semibold">1. Data cleaning</p>
                    <p className="text-xs text-muted-foreground">
                      Normalize branch names, timezones, and parse timestamps from GitHub Actions logs.
                    </p>
                  </li>
                  <li className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                    <p className="font-semibold">2. Feature normalization</p>
                    <p className="text-xs text-muted-foreground">
                      StandardScaler + min-max scaling for metrics (duration, code smells, coverage...).
                    </p>
                  </li>
                  <li className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                    <p className="font-semibold">3. Quality checks</p>
                    <p className="text-xs text-muted-foreground">
                      Compare with sample schema · detect drift or missing values before scoring.
                    </p>
                  </li>
                </ul>
              </>
            ) : (
              <p className="text-muted-foreground">Normalization information not found.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Issues to review</CardTitle>
            <CardDescription>Derived from the stages <code>issues</code> field</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {status.stages.some((stage) => stage.issues.length > 0) ? (
              status.stages
                .filter((stage) => stage.issues.length > 0)
                .map((stage) => (
                  <div key={stage.key} className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-900 dark:bg-amber-950/40">
                    <p className="text-xs font-semibold uppercase text-amber-600 dark:text-amber-400">
                      {stage.label}
                    </p>
                    <ul className="mt-2 space-y-2 text-amber-900 dark:text-amber-100">
                      {stage.issues.map((issue) => (
                        <li key={issue} className="flex items-start gap-2 text-xs">
                          <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
                          {issue}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
            ) : (
              <p className="text-muted-foreground">No pipeline issues recorded.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}

interface PipelineMetricProps {
  icon: React.ReactNode
  label: string
  value: string | number
  sublabel: string
}

function PipelineMetric({ icon, label, value, sublabel }: PipelineMetricProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground">{sublabel}</p>
      </CardContent>
    </Card>
  )
}

interface StageRowProps {
  stage: PipelineStage
}

function StageRow({ stage }: StageRowProps) {
  const statusClass = STATUS_BADGE[stage.status]
  const statusLabel = STATUS_LABEL[stage.status]
  const progressPercent = `${stage.percent_complete}%`

  return (
    <div className="rounded-xl border border-slate-200 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/70">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold">{stage.label}</p>
          <p className="text-xs text-muted-foreground">{stage.notes ?? 'No notes.'}</p>
        </div>
        <span className={cn('inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold', statusClass)}>
          {statusLabel}
        </span>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Progress</span>
          <span>{progressPercent}</span>
        </div>
        <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className={cn(
              'h-2 rounded-full',
              stage.status === 'completed' && 'bg-emerald-500',
              stage.status === 'running' && 'bg-blue-500',
              stage.status === 'pending' && 'bg-slate-300',
              stage.status === 'blocked' && 'bg-red-500',
            )}
            style={{ width: progressPercent }}
          />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {stage.items_processed ? <span>Items: {stage.items_processed.toLocaleString('en-US')}</span> : null}
        {stage.duration_seconds ? <span>Duration: {Math.round(stage.duration_seconds / 60)} minutes</span> : null}
        {stage.started_at ? <span>Started: {new Date(stage.started_at).toLocaleTimeString('en-US')}</span> : null}
      </div>
      {stage.issues.length > 0 ? (
        <ul className="mt-3 space-y-2 rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          {stage.issues.map((issue) => (
            <li key={issue} className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
              {issue}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

interface RoleMatrixProps {
  title: string
  description: string
  capabilities: string[]
}

function RoleMatrix({ title, description, capabilities }: RoleMatrixProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/70">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      </div>
      <ul className="mt-3 space-y-1.5 text-xs text-muted-foreground">
        {capabilities.map((capability) => (
          <li key={capability} className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-3 w-3 text-emerald-500" />
            {capability}
          </li>
        ))}
      </ul>
    </div>
  )
}
