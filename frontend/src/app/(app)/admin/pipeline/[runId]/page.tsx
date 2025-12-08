"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { pipelineApi } from "@/lib/api";
import type { PipelineRunDetail, NodeExecutionResult } from "@/types";
import {
    ArrowLeft,
    CheckCircle,
    XCircle,
    Clock,
    AlertTriangle,
    RefreshCw,
    GitBranch,
    ChevronDown,
    ChevronRight,
    Zap,
    SkipForward
} from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";

// Status Badge Component
function StatusBadge({ status, size = "sm" }: { status: string; size?: "sm" | "lg" }) {
    const statusConfig: Record<string, {
        bg: string;
        text: string;
        icon: React.ComponentType<{ className?: string }>
    }> = {
        completed: { bg: "bg-green-100", text: "text-green-700", icon: CheckCircle },
        success: { bg: "bg-green-100", text: "text-green-700", icon: CheckCircle },
        failed: { bg: "bg-red-100", text: "text-red-700", icon: XCircle },
        running: { bg: "bg-blue-100", text: "text-blue-700", icon: RefreshCw },
        pending: { bg: "bg-yellow-100", text: "text-yellow-700", icon: Clock },
        skipped: { bg: "bg-gray-100", text: "text-gray-700", icon: SkipForward },
        cancelled: { bg: "bg-gray-100", text: "text-gray-700", icon: XCircle },
    };

    const config = statusConfig[status] || statusConfig.pending;
    const Icon = config.icon;
    const sizeClasses = size === "lg" ? "px-3 py-1.5 text-sm" : "px-2 py-1 text-xs";

    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full font-medium ${config.bg} ${config.text} ${sizeClasses}`}>
            <Icon className={size === "lg" ? "w-4 h-4" : "w-3 h-3"} />
            {status}
        </span>
    );
}

// Node Result Row Component
function NodeResultRow({ result, index }: { result: NodeExecutionResult; index: number }) {
    const [expanded, setExpanded] = useState(result.status === "failed");

    const formatDuration = (ms: number) => {
        if (ms < 1000) return `${ms.toFixed(0)}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
        return `${(ms / 60000).toFixed(2)}m`;
    };

    return (
        <div className="border-b border-slate-200 dark:border-slate-700 last:border-b-0">
            <div
                className={`flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors ${result.status === "failed" ? "bg-red-50/50 dark:bg-red-950/20" : ""
                    }`}
                onClick={() => setExpanded(!expanded)}
            >
                <div className="w-8 text-center text-sm text-slate-400">
                    {index + 1}
                </div>
                <div className="flex-1">
                    <div className="flex items-center gap-2">
                        <span className="font-medium">{result.node_name}</span>
                        {result.retry_count > 0 && (
                            <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">
                                {result.retry_count} retries
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-sm text-slate-500 w-20 text-right">
                        {formatDuration(result.duration_ms)}
                    </span>
                    <span className="text-sm text-slate-500 w-16 text-right">
                        {result.features_extracted.length} features
                    </span>
                    <StatusBadge status={result.status} />
                    {(result.features_extracted.length > 0 || result.error || result.warning) ? (
                        expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />
                    ) : (
                        <div className="w-4" />
                    )}
                </div>
            </div>

            {expanded && (
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-200 dark:border-slate-700">
                    {result.error && (
                        <div className="mb-3 p-3 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
                            <div className="flex items-start gap-2">
                                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                <span className="font-mono text-xs break-all">{result.error}</span>
                            </div>
                        </div>
                    )}

                    {result.warning && (
                        <div className="mb-3 p-3 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded-lg text-sm">
                            <div className="flex items-start gap-2">
                                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                <span>{result.warning}</span>
                            </div>
                        </div>
                    )}

                    {result.features_extracted.length > 0 && (
                        <div>
                            <p className="text-xs font-medium text-slate-500 mb-2">Features Extracted:</p>
                            <div className="flex flex-wrap gap-1">
                                {result.features_extracted.map((feature) => (
                                    <span
                                        key={feature}
                                        className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-0.5 rounded"
                                    >
                                        {feature}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function PipelineRunDetailPage() {
    const params = useParams();
    const router = useRouter();
    const runId = params.runId as string;

    const [run, setRun] = useState<PipelineRunDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchRun = async () => {
            try {
                setLoading(true);
                const data = await pipelineApi.getRun(runId);
                setRun(data);
            } catch (err) {
                console.error("Failed to fetch pipeline run:", err);
                setError("Failed to load pipeline run details");
            } finally {
                setLoading(false);
            }
        };

        if (runId) {
            fetchRun();
        }
    }, [runId]);

    const formatDuration = (ms: number | null | undefined) => {
        if (!ms) return "-";
        if (ms < 1000) return `${ms.toFixed(0)}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
        return `${(ms / 60000).toFixed(2)}m`;
    };

    if (loading) {
        return (
            <div className="p-8">
                <div className="animate-pulse space-y-6">
                    <div className="h-8 w-64 bg-slate-200 rounded" />
                    <div className="h-32 bg-slate-200 rounded-xl" />
                    <div className="h-96 bg-slate-200 rounded-xl" />
                </div>
            </div>
        );
    }

    if (error || !run) {
        return (
            <div className="p-8">
                <Link
                    href="/admin/pipeline"
                    className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-4"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Pipeline Runs
                </Link>
                <div className="bg-red-50 text-red-700 p-4 rounded-lg flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    {error || "Pipeline run not found"}
                </div>
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6">
            {/* Header */}
            <div>
                <Link
                    href="/admin/pipeline"
                    className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-700 mb-4 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Pipeline Runs
                </Link>

                <div className="flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-2xl font-bold">Pipeline Run</h1>
                            <StatusBadge status={run.status} size="lg" />
                        </div>
                        <p className="text-slate-500 mt-1 font-mono text-sm">
                            ID: {run.id}
                        </p>
                    </div>

                    {run.dag_version && (
                        <div className="text-sm text-slate-500 flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-lg">
                            <GitBranch className="w-4 h-4" />
                            DAG v{run.dag_version}
                        </div>
                    )}
                </div>
            </div>

            {/* Overview Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                    <p className="text-xs font-medium text-slate-500 uppercase">Duration</p>
                    <p className="text-xl font-bold mt-1">{formatDuration(run.duration_ms)}</p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                    <p className="text-xs font-medium text-slate-500 uppercase">Nodes Executed</p>
                    <p className="text-xl font-bold mt-1">
                        <span className="text-green-600">{run.nodes_executed - run.nodes_failed}</span>
                        {run.nodes_failed > 0 && <span className="text-red-600"> / {run.nodes_failed}</span>}
                    </p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                    <p className="text-xs font-medium text-slate-500 uppercase">Features Extracted</p>
                    <p className="text-xl font-bold mt-1">{run.feature_count}</p>
                </div>
                <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                    <p className="text-xs font-medium text-slate-500 uppercase">Total Retries</p>
                    <p className={`text-xl font-bold mt-1 ${run.total_retries > 0 ? "text-yellow-600" : ""}`}>
                        {run.total_retries}
                    </p>
                </div>
            </div>

            {/* Timing Info */}
            <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                <div className="flex flex-wrap gap-6 text-sm">
                    <div>
                        <span className="text-slate-500">Started:</span>{" "}
                        <span className="font-medium">
                            {run.started_at
                                ? `${format(new Date(run.started_at), "PPpp")} (${formatDistanceToNow(new Date(run.started_at), { addSuffix: true })})`
                                : "-"
                            }
                        </span>
                    </div>
                    <div>
                        <span className="text-slate-500">Completed:</span>{" "}
                        <span className="font-medium">
                            {run.completed_at
                                ? format(new Date(run.completed_at), "PPpp")
                                : "-"
                            }
                        </span>
                    </div>
                    <div>
                        <span className="text-slate-500">Workflow Run ID:</span>{" "}
                        <span className="font-mono">{run.workflow_run_id}</span>
                    </div>
                </div>
            </div>

            {/* Errors */}
            {run.errors.length > 0 && (
                <div className="bg-red-50 dark:bg-red-950/30 rounded-xl p-4 border border-red-200 dark:border-red-800">
                    <h3 className="font-semibold text-red-700 dark:text-red-300 flex items-center gap-2 mb-3">
                        <XCircle className="w-5 h-5" />
                        Errors ({run.errors.length})
                    </h3>
                    <ul className="space-y-2">
                        {run.errors.map((error, i) => (
                            <li key={i} className="text-sm text-red-600 dark:text-red-300 font-mono bg-red-100 dark:bg-red-900/30 p-2 rounded">
                                {error}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Warnings */}
            {run.warnings.length > 0 && (
                <div className="bg-yellow-50 dark:bg-yellow-950/30 rounded-xl p-4 border border-yellow-200 dark:border-yellow-800">
                    <h3 className="font-semibold text-yellow-700 dark:text-yellow-300 flex items-center gap-2 mb-3">
                        <AlertTriangle className="w-5 h-5" />
                        Warnings ({run.warnings.length})
                    </h3>
                    <ul className="space-y-2">
                        {run.warnings.map((warning, i) => (
                            <li key={i} className="text-sm text-yellow-600 dark:text-yellow-300 bg-yellow-100 dark:bg-yellow-900/30 p-2 rounded">
                                {warning}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Node Results */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
                <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
                    <h2 className="font-semibold flex items-center gap-2">
                        <Zap className="w-5 h-5 text-blue-500" />
                        Node Execution Timeline ({run.node_results.length} nodes)
                    </h2>
                </div>

                <div>
                    {run.node_results.length === 0 ? (
                        <div className="px-4 py-8 text-center text-slate-500">
                            No node execution results available
                        </div>
                    ) : (
                        run.node_results.map((result, index) => (
                            <NodeResultRow key={result.node_name} result={result} index={index} />
                        ))
                    )}
                </div>
            </div>

            {/* Features Extracted */}
            {run.features_extracted.length > 0 && (
                <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-700">
                    <h3 className="font-semibold mb-3">
                        All Features Extracted ({run.features_extracted.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                        {run.features_extracted.map((feature) => (
                            <span
                                key={feature}
                                className="text-sm bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-1 rounded"
                            >
                                {feature}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
