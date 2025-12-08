"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { pipelineApi } from "@/lib/api";
import type { PipelineRun, PipelineStats, DAGInfo } from "@/types";
import {
    Activity,
    CheckCircle,
    XCircle,
    Clock,
    GitBranch,
    AlertTriangle,
    RefreshCw,
    Trash2,
    Zap
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

// Stats Card Component
function StatsCard({
    title,
    value,
    subtitle,
    icon: Icon,
    color = "blue"
}: {
    title: string;
    value: string | number;
    subtitle?: string;
    icon: React.ComponentType<{ className?: string }>;
    color?: "blue" | "green" | "red" | "yellow" | "purple";
}) {
    const colorClasses = {
        blue: "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
        green: "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400",
        red: "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400",
        yellow: "bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400",
        purple: "bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400",
    };

    return (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
                    <p className="text-2xl font-bold mt-1">{value}</p>
                    {subtitle && (
                        <p className="text-xs text-slate-400 mt-1">{subtitle}</p>
                    )}
                </div>
                <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
                    <Icon className="w-5 h-5" />
                </div>
            </div>
        </div>
    );
}

// Status Badge Component
function StatusBadge({ status }: { status: string }) {
    const statusConfig: Record<string, { color: string; icon: React.ComponentType<{ className?: string }> }> = {
        completed: { color: "bg-green-100 text-green-700", icon: CheckCircle },
        failed: { color: "bg-red-100 text-red-700", icon: XCircle },
        running: { color: "bg-blue-100 text-blue-700", icon: RefreshCw },
        pending: { color: "bg-yellow-100 text-yellow-700", icon: Clock },
        cancelled: { color: "bg-gray-100 text-gray-700", icon: XCircle },
    };

    const config = statusConfig[status] || statusConfig.pending;
    const Icon = config.icon;

    return (
        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
            <Icon className="w-3 h-3" />
            {status}
        </span>
    );
}

export default function PipelineDashboardPage() {
    const router = useRouter();
    const [stats, setStats] = useState<PipelineStats | null>(null);
    const [dagInfo, setDAGInfo] = useState<DAGInfo | null>(null);
    const [runs, setRuns] = useState<PipelineRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = async () => {
        try {
            setLoading(true);
            setError(null);

            const [statsData, dagData, runsData] = await Promise.all([
                pipelineApi.getStats({ days: 7 }),
                pipelineApi.getDAGInfo(),
                pipelineApi.listRuns({ limit: 20 }),
            ]);

            setStats(statsData);
            setDAGInfo(dagData);
            setRuns(runsData.items);
        } catch (err) {
            console.error("Failed to fetch pipeline data:", err);
            setError("Failed to load pipeline data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const formatDuration = (ms: number | null | undefined) => {
        if (!ms) return "-";
        if (ms < 1000) return `${ms.toFixed(0)}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
        return `${(ms / 60000).toFixed(1)}m`;
    };

    if (loading) {
        return (
            <div className="p-8">
                <div className="animate-pulse space-y-6">
                    <div className="h-8 w-48 bg-slate-200 rounded" />
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="h-32 bg-slate-200 rounded-xl" />
                        ))}
                    </div>
                    <div className="h-96 bg-slate-200 rounded-xl" />
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-8">
                <div className="bg-red-50 text-red-700 p-4 rounded-lg flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    {error}
                </div>
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Pipeline Monitoring</h1>
                    <p className="text-slate-500 mt-1">
                        Monitor feature extraction pipeline executions
                    </p>
                </div>
                {dagInfo && (
                    <div className="text-sm text-slate-500 flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-lg">
                        <GitBranch className="w-4 h-4" />
                        DAG v{dagInfo.version}
                    </div>
                )}
            </div>

            {/* Stats Cards */}
            {stats && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatsCard
                        title="Total Runs (7 days)"
                        value={stats.total_runs}
                        subtitle={`${stats.completed} completed`}
                        icon={Activity}
                        color="blue"
                    />
                    <StatsCard
                        title="Success Rate"
                        value={`${stats.success_rate.toFixed(1)}%`}
                        subtitle={`${stats.failed} failed`}
                        icon={CheckCircle}
                        color={stats.success_rate >= 90 ? "green" : stats.success_rate >= 70 ? "yellow" : "red"}
                    />
                    <StatsCard
                        title="Avg Duration"
                        value={formatDuration(stats.avg_duration_ms)}
                        subtitle={`${stats.avg_nodes_executed.toFixed(1)} nodes avg`}
                        icon={Clock}
                        color="purple"
                    />
                    <StatsCard
                        title="Total Retries"
                        value={stats.total_retries}
                        subtitle={`${stats.total_features} features extracted`}
                        icon={RefreshCw}
                        color={stats.total_retries > 10 ? "yellow" : "blue"}
                    />
                </div>
            )}

            {/* DAG Info */}
            {dagInfo && (
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-950/30 dark:to-purple-950/30 rounded-xl p-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
                            <Zap className="w-6 h-6 text-blue-600" />
                        </div>
                        <div>
                            <p className="font-medium">Feature Extraction DAG</p>
                            <p className="text-sm text-slate-500">
                                {dagInfo.node_count} nodes • {dagInfo.feature_count} features •
                                Groups: {dagInfo.groups.join(", ")}
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Recent Runs Table */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
                <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
                    <h2 className="font-semibold">Recent Pipeline Runs</h2>
                    <button
                        onClick={fetchData}
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-slate-50 dark:bg-slate-900/50">
                            <tr>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">ID</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Status</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Duration</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Nodes</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Features</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Retries</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">DAG</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase">Started</th>
                                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase"></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                            {runs.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                                        No pipeline runs yet. Import a repository to start extracting features.
                                    </td>
                                </tr>
                            ) : (
                                runs.map((run) => (
                                    <tr
                                        key={run.id}
                                        className="hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer transition-colors"
                                        onClick={() => router.push(`/admin/pipeline/${run.id}`)}
                                    >
                                        <td className="px-4 py-3 font-mono text-xs text-slate-500" title={run.id}>
                                            {run.id.slice(-8)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <StatusBadge status={run.status} />
                                        </td>
                                        <td className="px-4 py-3 text-sm">
                                            {formatDuration(run.duration_ms)}
                                        </td>
                                        <td className="px-4 py-3 text-sm">
                                            <span className="text-green-600">{run.nodes_executed - run.nodes_failed}</span>
                                            {run.nodes_failed > 0 && (
                                                <span className="text-red-600"> / {run.nodes_failed} failed</span>
                                            )}
                                            {run.nodes_skipped > 0 && (
                                                <span className="text-slate-400"> ({run.nodes_skipped} skipped)</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-sm font-medium">
                                            {run.feature_count}
                                        </td>
                                        <td className="px-4 py-3 text-sm">
                                            {run.total_retries > 0 ? (
                                                <span className="text-yellow-600">{run.total_retries}</span>
                                            ) : (
                                                <span className="text-slate-400">0</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-sm font-mono text-slate-500">
                                            {run.dag_version || "-"}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-slate-500">
                                            {run.started_at
                                                ? formatDistanceToNow(new Date(run.started_at), { addSuffix: true })
                                                : "-"
                                            }
                                        </td>
                                        <td className="px-4 py-3 text-sm">
                                            {run.errors.length > 0 && (
                                                <span title={run.errors[0]}>
                                                    <AlertTriangle className="w-4 h-4 text-red-500" />
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
