"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Github,
  Link2,
  Loader2,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Sparkles,
  Timer,
  UploadCloud,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { integrationApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { GithubImportJob, GithubIntegrationStatus } from "@/types";

export default function GithubIntegrationPage() {
  const [integration, setIntegration] =
    useState<GithubIntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [jobs, setJobs] = useState<GithubImportJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [newRepo, setNewRepo] = useState("buildguard/core-platform");
  const [newBranch, setNewBranch] = useState("main");

  const fetchIntegration = useCallback(async () => {
    try {
      const data = await integrationApi.getGithubStatus();
      setIntegration(data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Unable to load GitHub OAuth status from backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchImports = useCallback(async () => {
    try {
      const data = await integrationApi.getGithubImports();
      setJobs(data);
      setJobsError(null);
    } catch (err) {
      console.error(err);
      setJobsError("Unable to load list of import history.");
    } finally {
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIntegration();
    fetchImports();
  }, [fetchImports, fetchIntegration]);

  const hasIssues =
    integration?.lastSyncStatus !== "success" || !integration?.connected;

  const totalBuilds = useMemo(
    () =>
      integration?.repositories.reduce(
        (count, repo) => count + repo.buildCount,
        0
      ) ?? 0,
    [integration]
  );
  const runningJobs = useMemo(
    () => jobs.filter((job) => job.status === "running").length,
    [jobs]
  );
  const lastCompletedJob = useMemo(
    () => jobs.find((job) => job.status === "completed"),
    [jobs]
  );

  const handleAuthorize = async () => {
    setActionError(null);
    setActionLoading(true);
    try {
      const { authorize_url } = await integrationApi.startGithubOAuth(
        "/integrations/github"
      );
      window.location.href = authorize_url;
    } catch (err) {
      console.error(err);
      setActionError(
        "Unable to initiate OAuth. Check GITHUB_CLIENT_ID/SECRET configuration."
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevoke = async () => {
    setActionError(null);
    setActionLoading(true);
    try {
      await integrationApi.revokeGithubToken();
      await fetchIntegration();
    } catch (err) {
      console.error(err);
      setActionError("Unable to revoke GitHub token.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setImportError(null);
    setImportLoading(true);
    try {
      const job = await integrationApi.startGithubImport({
        repository: newRepo,
        branch: newBranch,
      });
      setJobs((prev) => [job, ...prev]);
    } catch (err) {
      console.error(err);
      setImportError("Unable to start a new repository import.");
    } finally {
      setImportLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading GitHub OAuth status...</CardTitle>
            <CardDescription>
              Syncing integration state from FastAPI backend.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Please wait a moment.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !integration) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20">
          <CardHeader>
            <CardTitle className="text-red-600 dark:text-red-300">
              Unable to load data
            </CardTitle>
            <CardDescription>
              {error ?? "Integration payload empty."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Check the backend endpoint <code>/api/integrations/github</code>.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const scopes = integration?.scopes ?? [
    "read:user",
    "repo",
    "read:org",
    "workflow",
  ];

  return (
    <div className="space-y-6">
      <Card
        className={cn(
          "border-2",
          hasIssues
            ? "border-amber-300 bg-amber-50/60 dark:bg-amber-900/20"
            : "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-900/20"
        )}
      >
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="flex items-center gap-3 text-xl">
              <Github className="h-6 w-6 text-slate-800" />
              GitHub OAuth Integration
            </CardTitle>
            <CardDescription>
              Read-only access: {scopes.join(", ")}
            </CardDescription>
            {integration.accountLogin ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Authorized as{" "}
                <span className="font-medium text-slate-700 dark:text-slate-200">
                  @{integration.accountLogin}
                </span>
                {integration.accountName ? ` (${integration.accountName})` : ""}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {integration.connected ? (
              <>
                <button
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-400 transition"
                  title="Collector not yet ready"
                  disabled
                  type="button"
                >
                  Trigger manual sync
                </button>
                <button
                  onClick={handleRevoke}
                  disabled={actionLoading}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-blue-500 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-60"
                  type="button"
                >
                  Revoke access
                </button>
              </>
            ) : (
              <button
                onClick={handleAuthorize}
                disabled={actionLoading}
                className="inline-flex items-center gap-2 rounded-lg bg-black px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
              >
                <Github className="h-4 w-4" />
                Authorize GitHub
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <IntegrationMetric
            icon={<ShieldCheck className="h-5 w-5 text-emerald-500" />}
            label="Connection status"
          >
            {integration.connected ? "Authorized" : "Not connected"}
          </IntegrationMetric>
          <IntegrationMetric
            icon={<Timer className="h-5 w-5 text-blue-500" />}
            label="Last sync"
          >
            {integration.connectedAt
              ? new Date(integration.connectedAt).toLocaleString("en-US")
              : "Not synced"}
          </IntegrationMetric>
          <IntegrationMetric
            icon={<Sparkles className="h-5 w-5 text-purple-500" />}
            label="Last sync message"
          >
            {integration.lastSyncMessage ?? "Collector has not run yet"}
          </IntegrationMetric>
          <IntegrationMetric
            icon={<UploadCloud className="h-5 w-5 text-slate-700" />}
            label="Import jobs running"
          >
            {runningJobs} running ·{" "}
            {lastCompletedJob
              ? `Completed: ${new Date(
                  lastCompletedJob.completed_at ?? lastCompletedJob.created_at
                ).toLocaleString("en-US")}`
              : "No jobs completed yet"}
          </IntegrationMetric>
          {actionError ? (
            <p className="md:col-span-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
              {actionError}
            </p>
          ) : null}
          {jobsError ? (
            <p className="md:col-span-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {jobsError}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Connected repositories</CardTitle>
            <CardDescription>
              Total {integration.repositories.length} repositories ·{" "}
              {totalBuilds} builds collected
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {integration.repositories.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 bg-white p-4 text-sm text-muted-foreground dark:border-slate-800 dark:bg-slate-900">
                No builds have been synced yet. Complete GitHub authorization to
                start collecting workflow runs.
              </p>
            ) : (
              integration.repositories.map((repo) => (
                <div
                  key={repo.name}
                  className="rounded-xl border bg-white/60 p-4 dark:bg-slate-900/60"
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="font-semibold text-slate-800">
                        {repo.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Last sync:{" "}
                        {repo.lastSync
                          ? new Date(repo.lastSync).toLocaleString("en-US")
                          : "Not synced"}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase",
                        repo.status === "healthy" &&
                          "bg-emerald-100 text-emerald-700",
                        repo.status === "degraded" &&
                          "bg-amber-100 text-amber-700",
                        repo.status === "attention" && "bg-red-100 text-red-700"
                      )}
                    >
                      {repo.status}
                    </span>
                  </div>

                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <IntegrationStat label="Builds" value={repo.buildCount} />
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Authorization guide</CardTitle>
            <CardDescription>
              GitHub OAuth with read-only scopes
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <ol className="space-y-3 text-sm text-muted-foreground">
              <li>
                1. Click the &ldquo;Authorize GitHub&rdquo; button to open the
                authentication screen.
              </li>
              <li>
                2. GitHub will display requested scopes: read:user, repo,
                read:org, workflow.
              </li>
              <li>
                3. After consenting, the app receives an authorization code and exchanges
                it for an access token.
              </li>
              <li>
                4. Token is securely stored (encrypted at rest) · no write or
                delete permissions are requested.
              </li>
              <li>
                5. BuildGuard runs a background job to collect commit metadata and
                workflow runs.
              </li>
            </ol>

            <div className="rounded-lg border border-dashed border-blue-300 bg-blue-50/50 p-4 text-sm dark:border-blue-800 dark:bg-blue-900/20">
              <p className="font-semibold text-blue-700 dark:text-blue-300">
                Authorize with GitHub
              </p>
              <p className="text-xs text-muted-foreground">
                BuildGuard will open the OAuth page in a new tab. After
                confirming, you will be returned to the dashboard.
              </p>
              <button
                onClick={handleAuthorize}
                disabled={actionLoading}
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-black px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
              >
                <Github className="h-4 w-4" />
                Authorize GitHub
              </button>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs leading-relaxed text-muted-foreground dark:border-slate-800 dark:bg-slate-900">
              <p className="font-semibold text-slate-700 dark:text-slate-200">
                Data safety commitment
              </p>
              <ul className="mt-2 space-y-2">
                <li className="flex items-start gap-2">
                  <ShieldOff className="mt-0.5 h-4 w-4 text-blue-500" />
                  BuildGuard uses read-only tokens to access workflow and commit
                  metadata.
                </li>
                <li className="flex items-start gap-2">
                  <ShieldOff className="mt-0.5 h-4 w-4 text-blue-500" />
                  No GitHub App or webhook needed; OAuth alone is sufficient.
                </li>
                <li className="flex items-start gap-2">
                  <ShieldOff className="mt-0.5 h-4 w-4 text-blue-500" />
                  You can revoke access at any time in GitHub Settings →
                  Applications.
                </li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
          <CardHeader>
          <CardTitle>Import repository history</CardTitle>
          <CardDescription>
            Automatically ingest all workflow runs and commit metadata
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={handleImport}
            className="grid gap-3 md:grid-cols-[2fr_1fr_auto]"
          >
            <input
              type="text"
              value={newRepo}
              onChange={(event) => setNewRepo(event.target.value)}
              placeholder="e.g., buildguard/core-platform"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900"
            />
            <input
              type="text"
              value={newBranch}
              onChange={(event) => setNewBranch(event.target.value)}
              placeholder="branch (e.g., main)"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none dark:border-slate-800 dark:bg-slate-900"
            />
            <button
              type="submit"
              disabled={importLoading}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
            >
              <UploadCloud className="h-4 w-4" />
              {importLoading ? "Importing..." : "Start import"}
            </button>
          </form>
          {importError ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
              {importError}
            </p>
          ) : null}
          <div className="space-y-3">
            {jobsLoading ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading import jobs list...
              </p>
            ) : jobs.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-2 text-sm text-muted-foreground dark:border-slate-800 dark:bg-slate-900">
                No import jobs found. Create one using the form above to collect
                build history.
              </p>
            ) : (
              jobs.map((job) => <ImportJobCard key={job.id} job={job} />)
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sync details</CardTitle>
          <CardDescription>
            Data flow after GitHub OAuth authorization
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <SyncStep
            title="1. OAuth Authorization"
            description="User signs in and consents to share read access to repository & workflow."
            icon={<Link2 className="h-5 w-5 text-blue-500" />}
          />
          <SyncStep
            title="2. Background collector"
            description="Background worker periodically calls GitHub REST API to collect commits, workflow runs, and artifacts."
            icon={<RefreshCw className="h-5 w-5 text-purple-500" />}
          />
          <SyncStep
            title="3. Scoring engine (disabled)"
            description="Data gets preprocessed & saved to the DB · model inference is currently disabled."
            icon={<ShieldCheck className="h-5 w-5 text-emerald-500" />}
          />
        </CardContent>
      </Card>
    </div>
  );
}

interface IntegrationMetricProps {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}

function IntegrationMetric({ icon, label, children }: IntegrationMetricProps) {
  return (
    <div className="rounded-xl border bg-white/60 p-4 text-sm font-semibold text-slate-700 dark:bg-slate-900/60">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        {icon} {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

interface IntegrationStatProps {
  label: string;
  value: number;
  status?: "warning";
}

function IntegrationStat({ label, value, status }: IntegrationStatProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900",
        status === "warning" &&
          "border-amber-300 bg-amber-50/80 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20"
      )}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

interface ImportJobCardProps {
  job: GithubImportJob;
}

function ImportJobCard({ job }: ImportJobCardProps) {
  const statusClass =
    job.status === "completed"
      ? "bg-emerald-100 text-emerald-700"
      : job.status === "failed"
      ? "bg-red-100 text-red-700"
      : job.status === "running"
      ? "bg-blue-100 text-blue-700"
      : "bg-slate-100 text-slate-600";

  return (
    <div className="rounded-xl border border-slate-200 bg-white/70 p-4 text-sm shadow-sm dark:border-slate-800 dark:bg-slate-900/70">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-semibold text-slate-800">{job.repository}</p>
          <p className="text-xs text-muted-foreground">Branch: {job.branch}</p>
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase",
            statusClass
          )}
        >
          {job.status}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>Progress {job.progress}%</span>
        <span>
          {job.builds_imported} builds · {job.commits_analyzed} commits
        </span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className={cn(
            "h-2 rounded-full",
            job.status === "completed" && "bg-emerald-500",
            job.status === "failed" && "bg-red-500",
            job.status === "running" && "bg-blue-500",
            job.status === "pending" && "bg-slate-400"
          )}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <div className="mt-3 grid gap-3 text-xs md:grid-cols-3">
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-[11px] uppercase text-muted-foreground">Tests</p>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {job.tests_collected}
          </p>
        </div>
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-[11px] uppercase text-muted-foreground">Creator</p>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {job.initiated_by}
          </p>
        </div>
        <div className="rounded-lg border border-slate-100 bg-slate-50 p-2 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-[11px] uppercase text-muted-foreground">Started</p>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {job.started_at
              ? new Date(job.started_at).toLocaleTimeString("en-US")
              : "N/A"}
          </p>
        </div>
      </div>
      {job.last_error ? (
        <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {job.last_error}
        </p>
      ) : null}
    </div>
  );
}

interface SyncStepProps {
  title: string;
  description: string;
  icon: React.ReactNode;
}

function SyncStep({ title, description, icon }: SyncStepProps) {
  return (
    <div className="rounded-xl border bg-white/60 p-4 text-sm shadow-sm dark:bg-slate-900/60">
      <div className="flex items-center gap-3 text-slate-700">
        {icon}
        <span className="font-semibold">{title}</span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
