"use client";

import {
  AlertTriangle,
  ArrowLeft,
  BookCopy,
  Calendar,
  Clock,
  Code,
  Github,
  GitPullRequest,
  Hexagon,
  Loader2,
  Shield,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { BuildDetail } from "@/types";

interface BuildDetailClientProps {
  build: BuildDetail;
}

export function BuildDetailClient({ build }: BuildDetailClientProps) {
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const features = build.features ?? {};

  return (
    <div className="space-y-6">
      <Link
        href="/builds"
        className="inline-flex items-center gap-2 text-sm font-semibold text-blue-600 transition hover:text-blue-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to builds list
      </Link>

      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="flex items-center gap-3 text-xl">
              <Hexagon className="h-6 w-6 text-blue-500" />
              {build.repository}
            </CardTitle>
            <CardDescription>
              Workflow: {build.workflow_name} · Branch: {build.branch} · Build{" "}
              {build.build_number}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
              <Sparkles className="h-4 w-4 text-blue-600" />
              Feature extraction: {Object.keys(features).length} features
            </span>
            <a
              href={build.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 transition hover:border-blue-500 hover:text-blue-600"
            >
              <Github className="h-4 w-4" />
              View on GitHub
            </a>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-[2fr_1fr]">
          <div className="grid gap-4">
            <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-4 text-sm dark:border-blue-900/70 dark:bg-blue-950/40">
              {explanationError ? (
                <p className="text-red-600 dark:text-red-300">{explanationError}</p>
              ) : (
                <>
                  <p className="flex items-center gap-2 text-slate-800 dark:text-slate-100">
                    <Sparkles className="h-4 w-4 text-blue-600" />
                    Feature extraction complete — metadata available
                  </p>
                  <p className="text-xs text-muted-foreground">Commit and workflow metadata saved for analysis</p>
                </>
              )}
            </div>
            <div className="grid gap-3 rounded-xl border bg-white/60 p-4 dark:bg-slate-900/60 md:grid-cols-3">
              <InfoItem
                icon={<Calendar className="h-5 w-5 text-blue-500" />}
                label="Started"
              >
                {build.started_at
                  ? new Date(build.started_at).toLocaleString("en-US")
                  : "N/A"}
              </InfoItem>
              <InfoItem
                icon={<Clock className="h-5 w-5 text-purple-500" />}
                label="Duration"
              >
                {build.duration_seconds
                  ? `${Math.round(build.duration_seconds / 60)} minutes`
                  : "Running"}
              </InfoItem>
              <InfoItem
                icon={<GitPullRequest className="h-5 w-5 text-emerald-500" />}
                label="Commit author"
              >
                {build.author_name}
              </InfoItem>
            </div>

            <div className="rounded-xl border bg-white/60 p-4 dark:bg-slate-900/60">
              <h3 className="text-sm font-semibold text-slate-700">
                Commit summary
              </h3>
              <p className="text-xs text-muted-foreground">
                Commit SHA: {build.commit_sha} · Email: {build.author_email}
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-slate-100 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900">
                  <p className="font-semibold text-slate-700">Key changes</p>
                  <ul className="mt-2 space-y-1 text-muted-foreground">
                    <li>- Update pipeline security hooks</li>
                    <li>- Fix the collector & sync frequency</li>
                    <li>- Refactor GitHub sync worker</li>
                  </ul>
                </div>
                <div className="rounded-lg border border-slate-100 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900">
                    <p className="font-semibold text-slate-700">Technical indicators</p>
                  <ul className="mt-2 space-y-1 text-muted-foreground">
                    <li>- {features.gh_diff_files_added ?? 0} files changed</li>
                    <li>- {features.gh_diff_tests_added ?? 0} tests added</li>
                    <li>- Pending review from security team</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <Card className="border border-slate-200 shadow-none dark:border-slate-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">
                    Security review notes
                  </CardTitle>
                  <CardDescription>
                    Track via risk score and internal security alerts.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-xs">
                  <MetricRow
                    label="Security indicators"
                    value={"N/A (predictions disabled)"}
                    intent={"positive"}
                  />
                    <p className="text-muted-foreground">
                      Use internal reports to view detailed security issues and
                      code quality. Prediction engine temporarily disabled.
                    </p>
                </CardContent>
              </Card>
            </div>
          </div>

          <div className="space-y-4">
            <Card className="border border-slate-200 shadow-none dark:border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">Extracted features</CardTitle>
                <CardDescription>Features derived from commit & workflow</CardDescription>
              </CardHeader>
              <CardContent className="h-56">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-slate-100 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900">
                    <p className="text-[11px] uppercase text-muted-foreground">Files changed</p>
                    <p className="text-lg font-semibold">{features.gh_diff_files_added ?? 0}</p>
                  </div>
                  <div className="rounded-lg border border-slate-100 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900">
                    <p className="text-[11px] uppercase text-muted-foreground">Tests added</p>
                    <p className="text-lg font-semibold">{features.gh_diff_tests_added ?? 0}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border border-slate-200 shadow-none dark:border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  Deployment readiness
                </CardTitle>
                <CardDescription>
                  Recommendations based on rule-based checks + risk score
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <p className="text-xs text-muted-foreground">Policy checks and manual reviews are shown here when enabled. Risk-based recommendations are disabled.</p>
              </CardContent>
            </Card>

            <Card className="border border-slate-200 shadow-none dark:border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                GitHub sync timeline
                </CardTitle>
                <CardDescription>
                  Build ingestion timeline (demo)
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(features).slice(0, 6).map(([name, value]) => (
                    <div
                      key={name}
                      className="rounded-lg border border-slate-100 bg-slate-50 p-2 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                    >
                      <p className="text-[11px] uppercase text-muted-foreground">{name}</p>
                      <p className="text-lg font-semibold">{typeof value === 'number' ? value : String(value)}</p>
                    </div>
                  ))}
                </div>
                <TimelineItem
                  time="T-12m"
                  label="Workflow run completed"
                  detail="GitHub Actions run completed · status: success"
                />
                <TimelineItem
                  time="T-9m"
                  label="Collector synced logs"
                  detail="Collected logs & artifacts · 3 warnings recorded"
                />
                <TimelineItem
                  time="T-6m"
                  label="Feature extraction"
                  detail="Extracted 128 features from commits & workflow runs"
                />
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface InfoItemProps {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}

function InfoItem({ icon, label, children }: InfoItemProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900">
      <div className="mt-1">{icon}</div>
      <div>
        <p className="text-xs font-semibold uppercase text-muted-foreground">
          {label}
        </p>
        <p className="text-sm text-slate-700 dark:text-slate-200">{children}</p>
      </div>
    </div>
  );
}

interface MetricRowProps {
  label: string;
  value: string | number;
  intent?: "positive" | "negative" | "attention";
}

function MetricRow({ label, value, intent }: MetricRowProps) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-semibold",
          intent === "positive" && "text-emerald-600",
          intent === "negative" && "text-red-600",
          intent === "attention" && "text-amber-600"
        )}
      >
        {value}
      </span>
    </div>
  );
}

interface RecommendationItemProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

function RecommendationItem({
  icon,
  title,
  description,
}: RecommendationItemProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-slate-100 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="mt-1">{icon}</div>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

interface TimelineItemProps {
  time: string;
  label: string;
  detail: string;
}

function TimelineItem({ time, label, detail }: TimelineItemProps) {
  return (
    <div className="flex gap-3 rounded-lg border border-slate-100 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="font-mono text-xs text-blue-600">{time}</div>
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}
