"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Filter,
  ExternalLink,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buildApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BuildDetail } from "@/types";

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  in_progress: "In progress",
  completed: "Completed",
};

const CONCLUSION_LABELS: Record<string, string> = {
  success: "Success",
  failure: "Failure",
  neutral: "Neutral",
  cancelled: "Canceled",
};

export default function BuildsPage() {
  const [builds, setBuilds] = useState<BuildDetail[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [repoFilter, setRepoFilter] = useState<"all" | string>("all");
  const [branchFilter, setBranchFilter] = useState<"all" | string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBuild, setSelectedBuild] = useState<BuildDetail | null>(null);
  // fetch builds
  useEffect(() => {
    const fetchBuilds = async () => {
      try {
        const response = await buildApi.getAll({ limit: 200 });
        setBuilds(response.builds);
      } catch (err) {
        console.error(err);
        setError("Unable to fetch builds list. Check backend API.");
      } finally {
        setLoading(false);
      }
    };

    fetchBuilds();
  }, []);

  const handleSelectBuild = (build: BuildDetail) => {
    setSelectedBuild(build);
  };

  const handleCloseInsight = () => {
    setSelectedBuild(null);
  };

  const repositories = useMemo(
    () => Array.from(new Set(builds.map((b) => b.repository))).sort(),
    [builds]
  );
  const branches = useMemo(
    () => Array.from(new Set(builds.map((b) => b.branch))).sort(),
    [builds]
  );

  const filteredBuilds = useMemo(() => {
    return builds.filter((build) => {
      const matchesSearch =
        build.repository.toLowerCase().includes(searchTerm.toLowerCase()) ||
        build.branch.toLowerCase().includes(searchTerm.toLowerCase()) ||
        build.commit_sha.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesRepo =
        repoFilter === "all" || build.repository === repoFilter;
      const matchesBranch =
        branchFilter === "all" || build.branch === branchFilter;
      return matchesSearch && matchesRepo && matchesBranch;
    });
  }, [branchFilter, builds, repoFilter, searchTerm]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading builds...</CardTitle>
            <CardDescription>Fetching builds from backend</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Please wait…</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent>
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-3 text-left font-medium">
                  Build
                </th>
                <th scope="col" className="px-4 py-3 text-left font-medium">
                  Repository · Workflow
                </th>
                <th scope="col" className="px-4 py-3 text-left font-medium">
                  Features
                </th>
                <th scope="col" className="px-4 py-3 text-left font-medium">
                  Status
                </th>
                <th scope="col" className="px-4 py-3 text-left font-medium">
                  Thời gian
                </th>
                <th scope="col" className="px-4 py-3 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filteredBuilds.map((build) => (
                <tr key={build.id} className="hover:bg-blue-50/40">
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="font-semibold text-slate-800">
                        #{build.build_number}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {build.commit_sha}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="font-medium">{build.repository}</span>
                      <span className="text-xs text-muted-foreground">
                        {build.workflow_name} · {build.branch}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => handleSelectBuild(build)}
                      className="flex w-full flex-col items-start gap-1 rounded-lg border border-transparent px-1 py-1 text-left transition hover:border-blue-200 hover:bg-blue-50/40"
                    >
                      <span className="text-sm font-semibold">
                        View features
                      </span>
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600">
                        <Sparkles className="h-3 w-3" />
                        Explore
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={build.status}
                      conclusion={build.conclusion}
                      showConclusion={build.status === "completed"}
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {build.started_at
                      ? new Date(build.started_at).toLocaleString("en-US")
                      : "N/A"}
                    <br />
                    {build.duration_seconds
                      ? `${Math.round(build.duration_seconds / 60)} minutes`
                      : "Running"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        href={`/builds/${build.id}`}
                        className="rounded-lg border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-600 transition hover:bg-blue-600 hover:text-white"
                      >
                        Details
                      </Link>
                      <a
                        href={build.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1 text-xs text-muted-foreground transition hover:border-blue-500 hover:text-blue-600"
                      >
                        Logs
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredBuilds.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-6 text-center text-sm text-muted-foreground"
                  >
                    No builds match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
      {selectedBuild ? (
        <BuildInsightPanel
          build={selectedBuild}
          onClose={() => setSelectedBuild(null)}
        />
      ) : null}
    </div>
  );
}

interface BuildInsightPanelProps {
  build: BuildDetail;
  onClose: () => void;
}

function BuildInsightPanel({ build, onClose }: BuildInsightPanelProps) {
  return (
    <Card className="border border-slate-200 bg-white">
      <CardHeader className="flex items-center justify-between">
        <div>
          <CardTitle>Build details · {build.repository}</CardTitle>
          <CardDescription>
            Commit {build.commit_sha} · #{build.build_number}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 p-2 text-muted-foreground transition hover:bg-red-50 hover:text-red-600"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="rounded-xl border border-blue-200 bg-white/50 p-4 text-sm">
          <p className="font-semibold flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-600" />
            Extracted features
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Feature extraction is active. ML prediction is disabled.
          </p>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border bg-slate-50 p-3 text-xs">
            <p className="text-[11px] uppercase text-muted-foreground">
              Feature snapshot
            </p>
            {Object.entries(build.features ?? {})
              .slice(0, 12)
              .map(([k, v]) => (
                <div key={k} className="mt-2 flex items-center justify-between">
                  <span className="font-semibold text-slate-700">{k}</span>
                  <span className="text-muted-foreground">{String(v)}</span>
                </div>
              ))}
          </div>

          <div className="rounded-lg border bg-slate-50 p-3 text-xs">
            <p className="text-[11px] uppercase text-muted-foreground">
              Feature groups
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {Object.entries(build.features ?? {})
                .slice(0, 6)
                .map(([name, value]) => (
                  <div
                    key={name}
                    className="rounded-lg border border-slate-100 bg-white p-2 text-xs text-slate-700"
                  >
                    <p className="font-semibold">{name}</p>
                    <p className="text-lg font-bold">{String(value)}</p>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface FilterButtonProps {
  label: string;
  active: boolean;
  onClick: () => void;
  intent?: string;
}

function FilterButton({ label, active, onClick, intent }: FilterButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-semibold capitalize transition",
        active
          ? "border-transparent text-white shadow-sm"
          : "border-slate-200 text-slate-600 hover:border-blue-500 hover:text-blue-600 dark:border-slate-700",
        intent === "low" && active && "bg-emerald-500",

        intent === "high" && active && "bg-orange-500",
        intent === "critical" && active && "bg-red-500",
        !intent && active && "bg-blue-600"
      )}
    >
      {label}
    </button>
  );
}

interface StatusBadgeProps {
  status: string;
  conclusion?: string;
  showConclusion?: boolean;
}

function StatusBadge({ status, conclusion, showConclusion }: StatusBadgeProps) {
  const statusLabel = STATUS_LABELS[status] ?? status;
  const conclusionLabel =
    conclusion && showConclusion
      ? CONCLUSION_LABELS[conclusion] ?? conclusion
      : undefined;

  return (
    <div className="flex flex-col gap-1">
      <span className="inline-flex items-center rounded-full border border-blue-200 px-2 py-0.5 text-xs font-semibold text-blue-600">
        {statusLabel}
      </span>
      {conclusionLabel ? (
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold",
            conclusion === "success" && "border-emerald-200 text-emerald-600",
            conclusion === "failure" && "border-red-200 text-red-600",
            conclusion === "neutral" && "border-slate-200 text-slate-600",
            conclusion === "cancelled" && "border-amber-200 text-amber-600"
          )}
        >
          {conclusionLabel}
        </span>
      ) : null}
    </div>
  );
}
