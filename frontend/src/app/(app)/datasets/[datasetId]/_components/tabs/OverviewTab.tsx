"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { enrichmentApi } from "@/lib/api";
import type { DatasetRecord, EnrichmentJob } from "@/types";
import {
    Activity,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock,
    Database,
    XCircle,
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

    return (
        <div className="space-y-6">
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
