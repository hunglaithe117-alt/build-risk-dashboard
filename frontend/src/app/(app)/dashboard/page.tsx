"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  ArrowUpRight,
  Flame,
  ShieldCheck,
  Timer,
  Workflow,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { dashboardApi } from "@/lib/api";
import { integrationApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import type { DashboardSummaryResponse } from "@/types";

const CONCLUSION_LABELS: Record<string, string> = {
  success: "Success",
  failure: "Failure",
  neutral: "Neutral",
  cancelled: "Canceled",
};

export default function DashboardPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSummary = async () => {
      // redirect to login if GitHub is not connected
      try {
        const status = await integrationApi.getGithubStatus();
        if (!status.connected) {
          router.replace("/login");
          return;
        }
      } catch (err) {
        console.error("Failed to check integration status:", err);
      }
      try {
        const data = await dashboardApi.getSummary();
        setSummary(data);
      } catch (err) {
        console.error(err);
        setError(
          "Unable to load dashboard data. Please check the backend API."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
  }, [router]);

  const trendData = useMemo(
    () =>
      summary?.trends.map((trend) => ({
        date: trend.date,
        builds: trend.builds,
        failures: trend.failures,
      })) ?? [],
    [summary]
  );

  const repoDistribution = summary?.repo_distribution ?? [];
  const highRiskBuilds: any[] = [];
  const metrics = summary?.metrics;

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

  if (error || !summary || !metrics) {
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

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          icon={<Workflow className="h-6 w-6 text-blue-500" />}
          title="Total builds (14 days)"
          value={metrics.total_builds}
          sublabel={`${repoDistribution.length} repositories`}
        />
        <SummaryCard
          icon={<Timer className="h-6 w-6 text-purple-500" />}
          title="Average build time"
          value={Math.round(metrics.average_duration_minutes)}
          format="minutes"
          sublabel="Dựa trên builds hoàn thành"
        />
        <SummaryCard
          icon={<Flame className="h-6 w-6 text-red-500" />}
          title="Success rate"
          value={metrics.success_rate}
          format="percentage"
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card className="overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle>Build trends</CardTitle>
              <CardDescription>
                Completed builds and failures per day
              </CardDescription>
            </div>
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
              <ArrowUpRight className="h-3 w-3" />
              Real-time sync
            </span>
          </CardHeader>
          <CardContent className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient
                    id="buildGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" />
                <YAxis
                  yAxisId="left"
                  orientation="left"
                  stroke="#ef4444"
                  domain={[0, 1]}
                  tickFormatter={(value) => value.toFixed(1)}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#3b82f6"
                  allowDecimals={false}
                />
                <Tooltip />
                <Legend />
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="builds"
                  stroke="#3b82f6"
                  fillOpacity={1}
                  fill="url(#buildGradient)"
                  name="Builds"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="failures"
                  stroke="#f59e0b"
                  name="Failures"
                  strokeWidth={2}
                  dot
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Indicator heatmap (disabled)</CardTitle>
            <CardDescription>
              Model inference disabled — no heatmap available
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-2 text-xs">
              <div className="flex flex-col items-start gap-1 text-muted-foreground">
                <span>Day</span>
                <span className="h-12 w-full text-sm font-semibold">
                  Feature extraction active
                </span>
              </div>
              {/* heatmap grid removed */}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Repository performance</CardTitle>
            <CardDescription>
              Number of builds and general activity
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={repoDistribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="repository" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="builds"
                  stroke="#3b82f6"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Recent flagged builds</CardTitle>
            <CardDescription>
              Model-based flags are currently disabled
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {highRiskBuilds.map((build) => (
              <div key={build.id} className="rounded-xl border p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">{build.repository}</p>
                    <p className="text-xs text-muted-foreground">
                      {build.workflow_name} · {build.branch}
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                  <span>Model predictions disabled</span>
                  <span>
                    Conclusion:{" "}
                    {build.conclusion
                      ? CONCLUSION_LABELS[build.conclusion] ?? build.conclusion
                      : "N/A"}
                  </span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Sức khỏe pipeline</CardTitle>
            <CardDescription>
              Đánh giá tổng quan dựa trên chỉ số chất lượng nội bộ và phân tích
              tạm thời (AI disabled).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <PipelineHealthItem
              label="Feature extraction"
              value={`Feature snapshot collection active`}
              status={"healthy"}
              description="Model inference is disabled for now — only feature collection is active."
            />
            <PipelineHealthItem
              label="Code coverage"
              value="64%"
              status="attention"
              description="Target >= 75% · Add tests for ML adapters module"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Các bước tiếp theo</CardTitle>
            <CardDescription>
              Lộ trình tích hợp đầy đủ BuildGuard platform
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <NextStepsItem
              title="1. Complete GitHub sync"
              description="Finish the background job that collects workflow runs, commit diffs, and artifact logs."
            />
            <NextStepsItem
              title="2. Normalize training data"
              description="Build a feature extraction pipeline and prepare a clean dataset for the Bayesian CNN."
            />
            <NextStepsItem
              title="3. Integrate AI model"
              description="Deploy the AI scoring model and connect the `/risk` API to return risk scores (disabled for now)."
            />
            <NextStepsItem
              title="4. Alerting & automation"
              description="Set up Slack/Email notifications and policies to hold deployments for critical alerts."
            />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

interface SummaryCardProps {
  icon: React.ReactNode;
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
      ? `${value} phút`
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

interface PipelineHealthItemProps {
  label: string;
  value: string;
  status: "healthy" | "warning" | "attention";
  description: string;
}

function PipelineHealthItem({
  label,
  value,
  status,
  description,
}: PipelineHealthItemProps) {
  return (
    <div className="rounded-xl border bg-white/60 p-4 dark:bg-slate-900/60">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">{label}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <div
          className={cn(
            "flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold",
            status === "healthy" && "bg-emerald-100 text-emerald-700",
            status === "warning" && "bg-amber-100 text-amber-700",
            status === "attention" && "bg-sky-100 text-sky-700"
          )}
        >
          <AlertCircle className="h-4 w-4" />
          {value}
        </div>
      </div>
    </div>
  );
}

interface NextStepsItemProps {
  title: string;
  description: string;
}

function NextStepsItem({ title, description }: NextStepsItemProps) {
  return (
    <div className="rounded-xl border bg-white/60 p-4 dark:bg-slate-900/60">
      <p className="text-sm font-semibold">{title}</p>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
