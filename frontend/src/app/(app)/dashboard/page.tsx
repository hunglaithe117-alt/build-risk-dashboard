"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ShieldCheck, Workflow } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buildApi, dashboardApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import type { BuildDetail, DashboardSummaryResponse } from "@/types";
import { useAuth } from "@/contexts/auth-context";

export default function DashboardPage() {
  const router = useRouter();
  const { authenticated, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [recentBuilds, setRecentBuilds] = useState<BuildDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [buildsError, setBuildsError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !authenticated) {
      return;
    }

    let isActive = true;

    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        const [summaryResult, buildsResult] = await Promise.allSettled([
          dashboardApi.getSummary(),
          buildApi.getAll({ limit: 10 }),
        ]);

        if (!isActive) {
          return;
        }

        if (summaryResult.status === "fulfilled") {
          setSummary(summaryResult.value);
        } else {
          throw summaryResult.reason;
        }

        if (buildsResult.status === "fulfilled") {
          setRecentBuilds(buildsResult.value.builds ?? []);
          setBuildsError(null);
        } else {
          console.error("Failed to load recent builds", buildsResult.reason);
          setBuildsError("Unable to load recent builds.");
        }
      } catch (err) {
        console.error("Failed to load dashboard data", err);
        if (isActive) {
          setError(
            "Unable to load dashboard data. Please check the backend API."
          );
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    };

    loadData();

    return () => {
      isActive = false;
    };
  }, [authenticated, authLoading]);

  const handleRowClick = (buildId: string) => {
    router.push(`/builds/${buildId}`);
  };

  const totalRepositories = summary?.repo_distribution?.length ?? 0;

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading dashboard...</CardTitle>
            <CardDescription>
              Connecting to the backend API to retrieve aggregated data.
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

  if (error || !summary || !summary.metrics) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20">
          <CardHeader>
            <CardTitle className="text-red-600 dark:text-red-300">
              Unable to load data
            </CardTitle>
            <CardDescription>
              {error ?? "Dashboard data is not yet available."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Check the backend FastAPI and ensure the endpoint{" "}
              <code>/api/dashboard/summary</code> is operational.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { metrics } = summary;

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2">
        <SummaryCard
          icon={<Workflow className="h-6 w-6 text-blue-500" />}
          title="Total builds (14 days)"
          value={metrics.total_builds}
          sublabel="Rolling 14-day period"
        />
        <SummaryCard
          icon={<ShieldCheck className="h-6 w-6 text-emerald-500" />}
          title="Total repositories"
          value={totalRepositories}
          sublabel="Connected via GitHub"
        />
      </section>

      <Card className="overflow-hidden">
        <CardHeader>
          <div>
            <CardTitle>Recent builds</CardTitle>
            <CardDescription>
              Latest workflow runs across your tracked repositories
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {buildsError ? (
            <div className="p-6 text-sm text-red-600 dark:text-red-400">
              {buildsError}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="bg-slate-50 dark:bg-slate-900/40">
                  <tr>
                    <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                      Repo name
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                      Branch
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                      Build ID
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                      Status (Success/Failed)
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                      Build finished time
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {recentBuilds.length === 0 ? (
                    <tr>
                      <td
                        className="px-6 py-6 text-center text-sm text-muted-foreground"
                        colSpan={5}
                      >
                        No builds have been recorded yet.
                      </td>
                    </tr>
                  ) : (
                    recentBuilds.map((build) => {
                      const statusInfo = getBuildStatus(
                        build.conclusion,
                        build.status
                      );
                      const finishedAt =
                        build.completed_at ??
                        build.updated_at ??
                        build.created_at;

                      return (
                        <tr
                          key={build.id}
                          role="button"
                          tabIndex={0}
                          className="cursor-pointer transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:hover:bg-slate-900/50"
                          onClick={() => handleRowClick(build.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              handleRowClick(build.id);
                            }
                          }}
                        >
                          <td className="px-6 py-4 text-sm font-medium text-foreground">
                            {build.repository}
                          </td>
                          <td className="px-6 py-4 text-sm text-muted-foreground">
                            {build.branch ?? "—"}
                          </td>
                          <td className="px-6 py-4 text-sm text-muted-foreground">
                            {build.build_number ?? build.id}
                          </td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${statusInfo.className}`}
                            >
                              {statusInfo.label}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm text-muted-foreground">
                            {formatFinishedTime(finishedAt)}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function formatFinishedTime(dateString?: string | null) {
  if (!dateString) {
    return "—";
  }

  const parsed = new Date(dateString);

  if (Number.isNaN(parsed.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function getBuildStatus(conclusion?: string | null, status?: string | null) {
  const normalized = (conclusion ?? status ?? "").toLowerCase();

  if (normalized === "success" || normalized === "successful") {
    return {
      label: "Success",
      className:
        "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    };
  }

  if (normalized === "failure" || normalized === "failed") {
    return {
      label: "Failed",
      className: "bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300",
    };
  }

  return {
    label: conclusion ?? status ?? "Unknown",
    className:
      "bg-slate-100 text-slate-600 dark:bg-slate-900/40 dark:text-slate-200",
  };
}

interface SummaryCardProps {
  icon: ReactNode;
  title: string;
  value: number;
  format?: "score" | "percentage" | "minutes";
  sublabel?: string;
}

function SummaryCard({
  icon,
  title,
  value,
  format,
  sublabel,
}: SummaryCardProps) {
  const formattedValue =
    format === "score"
      ? value.toFixed(2)
      : format === "percentage"
      ? `${value.toFixed(1)}%`
      : format === "minutes"
      ? `${value} minutes`
      : value;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{formattedValue}</div>
        {sublabel ? (
          <p className="text-xs text-muted-foreground">{sublabel}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
