"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ShieldCheck, Workflow, Clock, GitBranch } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { dashboardApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import type { DashboardSummaryResponse } from "@/types";
import { useAuth } from "@/contexts/auth-context";
import { formatDuration } from "@/lib/utils";

export default function DashboardPage() {
  const router = useRouter();
  const { authenticated, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !authenticated) {
      return;
    }

    let isActive = true;

    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        const summaryResult = await dashboardApi.getSummary();

        if (!isActive) {
          return;
        }

        setSummary(summaryResult);
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
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          icon={<Workflow className="h-6 w-6 text-blue-500" />}
          title="Total builds"
          value={metrics.total_builds}
          sublabel="All tracked builds"
        />
        <SummaryCard
          icon={<ShieldCheck className="h-6 w-6 text-emerald-500" />}
          title="Success Rate"
          value={metrics.success_rate}
          format="percentage"
          sublabel="Build success ratio"
        />
        <SummaryCard
          icon={<Clock className="h-6 w-6 text-amber-500" />}
          title="Avg Duration"
          value={metrics.average_duration_minutes}
          format="minutes"
          sublabel="Average build time"
        />
        <SummaryCard
          icon={<GitBranch className="h-6 w-6 text-purple-500" />}
          title="Total repositories"
          value={totalRepositories}
          sublabel="Connected via GitHub"
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Repository Distribution</CardTitle>
          <CardDescription>
            Build count per repository
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 dark:bg-slate-900/40">
                <tr>
                  <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                    Repository
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-600 dark:text-slate-300">
                    Builds
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {summary.repo_distribution.length === 0 ? (
                  <tr>
                    <td
                      className="px-6 py-6 text-center text-sm text-muted-foreground"
                      colSpan={2}
                    >
                      No repositories have been connected yet.
                    </td>
                  </tr>
                ) : (
                  summary.repo_distribution.map((repo) => (
                    <tr
                      key={repo.repository}
                      className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/50"
                      onClick={() => router.push(`/admin/repos`)}
                    >
                      <td className="px-6 py-4 text-sm font-medium text-foreground">
                        {repo.repository}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {repo.builds.toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
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
          ? formatDuration(value)
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
