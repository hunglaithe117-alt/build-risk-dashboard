"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { enrichmentApi } from "@/lib/api";
import type { DatasetRecord, EnrichmentJob } from "@/types";
import {
    Activity,
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock,
    Database,
    FileSpreadsheet,
    HardDrive,
    Layers,
    TrendingUp,
    XCircle,
    Zap,
} from "lucide-react";

interface OverviewTabProps {
    dataset: DatasetRecord;
    onRefresh: () => void;
}

function formatDate(value?: string | null) {
    if (!value) return "—";
    try {
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(value));
    } catch {
        return value;
    }
}

function formatFileSize(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatRelativeTime(dateStr: string | undefined | null): string {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(dateStr);
}

export function OverviewTab({ dataset, onRefresh }: OverviewTabProps) {
    const [enrichmentJobs, setEnrichmentJobs] = useState<EnrichmentJob[]>([]);
    const [loading, setLoading] = useState(true);
    const [previewExpanded, setPreviewExpanded] = useState(true);

    const hasMapping = Boolean(dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name);
    const totalFeatures = dataset.selected_features?.length || 0;
    const sonarFeatures = dataset.selected_features?.filter(f => f.startsWith("sonar_")).length || 0;
    const regularFeatures = totalFeatures - sonarFeatures;

    // Calculate health score
    const calculateHealthScore = (): number => {
        let score = 0;
        // Mapping (30 points)
        if (hasMapping) score += 30;
        // Features selected (30 points)
        if (totalFeatures > 0) score += Math.min(30, totalFeatures);
        // Recent enrichment (40 points)
        const latestJob = enrichmentJobs[0];
        if (latestJob?.status === "completed") score += 40;
        else if (latestJob?.status === "running") score += 20;
        return Math.min(100, score);
    };

    // Load enrichment history
    const loadEnrichmentHistory = useCallback(async () => {
        try {
            const response = await enrichmentApi.listJobs(dataset.id);
            setEnrichmentJobs(response || []);
        } catch (err) {
            console.error("Failed to load enrichment history:", err);
        } finally {
            setLoading(false);
        }
    }, [dataset.id]);

    useEffect(() => {
        loadEnrichmentHistory();
    }, [loadEnrichmentHistory]);

    const healthScore = calculateHealthScore();
    const latestJob = enrichmentJobs[0];

    // Health check items
    const healthItems = [
        {
            label: "Column mapping complete",
            passed: hasMapping,
            icon: hasMapping ? CheckCircle2 : XCircle,
        },
        {
            label: `${totalFeatures} features selected`,
            passed: totalFeatures > 0,
            icon: totalFeatures > 0 ? CheckCircle2 : AlertCircle,
        },
        {
            label: latestJob
                ? `Last enrichment: ${formatRelativeTime(latestJob.completed_at || latestJob.started_at)}`
                : "No enrichment run yet",
            passed: latestJob?.status === "completed",
            icon: latestJob?.status === "completed" ? CheckCircle2 : Clock,
        },
    ];

    return (
        <div className="space-y-6">
            {/* Health Score Card */}
            <Card className="overflow-hidden">
                <CardHeader className="bg-gradient-to-r from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <TrendingUp className="h-5 w-5 text-emerald-500" />
                                Dataset Health Score
                            </CardTitle>
                            <CardDescription>
                                Overall readiness for feature extraction
                            </CardDescription>
                        </div>
                        <div className="text-right">
                            <p className="text-4xl font-bold">{healthScore}</p>
                            <p className="text-sm text-muted-foreground">/100</p>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    <Progress
                        value={healthScore}
                        className={`h-3 ${healthScore >= 80 ? "[&>div]:bg-emerald-500" : healthScore >= 50 ? "[&>div]:bg-amber-500" : "[&>div]:bg-red-500"}`}
                    />
                    <div className="mt-4 space-y-2">
                        {healthItems.map((item, idx) => {
                            const Icon = item.icon;
                            return (
                                <div key={idx} className="flex items-center gap-2 text-sm">
                                    <Icon
                                        className={`h-4 w-4 ${item.passed ? "text-green-500" : "text-amber-500"}`}
                                    />
                                    <span className={item.passed ? "" : "text-muted-foreground"}>
                                        {item.label}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </CardContent>
            </Card>

            {/* Statistics Grid */}
            <div className="grid gap-4 md:grid-cols-5">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Rows</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <FileSpreadsheet className="h-5 w-5 text-muted-foreground" />
                            <span className="text-2xl font-bold">{dataset.rows.toLocaleString()}</span>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Columns</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <Layers className="h-5 w-5 text-muted-foreground" />
                            <span className="text-2xl font-bold">{dataset.columns?.length || 0}</span>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Selected Features</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <Zap className="h-5 w-5 text-amber-500" />
                            <span className="text-2xl font-bold">{totalFeatures}</span>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                            {regularFeatures} regular, {sonarFeatures} sonar
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>File Size</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <HardDrive className="h-5 w-5 text-muted-foreground" />
                            <span className="text-2xl font-bold">
                                {formatFileSize(dataset.size_bytes || 0)}
                            </span>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Success Rate</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-500" />
                            <span className="text-2xl font-bold">
                                {latestJob && latestJob.total_rows > 0
                                    ? `${((latestJob.enriched_rows / latestJob.total_rows) * 100).toFixed(1)}%`
                                    : "—"}
                            </span>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Recent Activity */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5" />
                        Recent Activity
                    </CardTitle>
                    <CardDescription>
                        Latest enrichment jobs and changes
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="py-8 text-center text-muted-foreground">
                            Loading activity...
                        </div>
                    ) : enrichmentJobs.length > 0 ? (
                        <div className="space-y-3">
                            {enrichmentJobs.slice(0, 5).map((job, idx) => (
                                <div
                                    key={idx}
                                    className="flex items-center justify-between rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
                                >
                                    <div className="flex items-center gap-3">
                                        {job.status === "completed" && (
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        )}
                                        {job.status === "running" && (
                                            <Clock className="h-4 w-4 animate-pulse text-blue-500" />
                                        )}
                                        {job.status === "failed" && (
                                            <XCircle className="h-4 w-4 text-red-500" />
                                        )}
                                        {job.status === "pending" && (
                                            <Clock className="h-4 w-4 text-slate-400" />
                                        )}
                                        <div>
                                            <p className="text-sm font-medium">
                                                Enrichment {job.status}
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                {job.enriched_rows?.toLocaleString() || 0} / {job.total_rows?.toLocaleString() || 0} rows
                                            </p>
                                        </div>
                                    </div>
                                    <span className="text-xs text-muted-foreground">
                                        {formatRelativeTime(job.started_at)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="py-8 text-center text-muted-foreground">
                            No enrichment jobs yet. Start your first enrichment from the Enrichment tab.
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Data Preview (Collapsible) */}
            <Card>
                <CardHeader
                    className="cursor-pointer"
                    onClick={() => setPreviewExpanded(!previewExpanded)}
                >
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Database className="h-5 w-5" />
                                Data Preview
                            </CardTitle>
                            <CardDescription>First 5 rows of the dataset</CardDescription>
                        </div>
                        {previewExpanded ? (
                            <ChevronDown className="h-5 w-5 text-muted-foreground" />
                        ) : (
                            <ChevronRight className="h-5 w-5 text-muted-foreground" />
                        )}
                    </div>
                </CardHeader>
                {previewExpanded && (
                    <CardContent className="p-0">
                        <div className="max-h-80 overflow-auto">
                            <table className="min-w-full text-sm">
                                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        {dataset.columns?.map((col) => (
                                            <th key={col} className="px-4 py-2 text-left font-medium whitespace-nowrap">
                                                {col}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {dataset.preview?.slice(0, 5).map((row, idx) => (
                                        <tr key={idx}>
                                            {dataset.columns?.map((col) => (
                                                <td key={col} className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                                                    {String(row[col] ?? "—").slice(0, 50)}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                )}
            </Card>
        </div>
    );
}
