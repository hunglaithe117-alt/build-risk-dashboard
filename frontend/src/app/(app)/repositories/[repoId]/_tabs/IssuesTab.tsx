"use client";

import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { reposApi } from "@/lib/api";
import { formatTimestamp } from "@/lib/utils";

interface FailedImportBuild {
    id: string;
    ci_run_id: string;
    commit_sha: string;
    ingestion_error?: string;
    resource_errors: Record<string, string>;
    fetched_at?: string;
}

interface IssuesTabProps {
    repoId: string;
    failedIngestionCount: number;
    failedExtractionCount: number;
    failedPredictionCount: number;
    onRetryIngestion: () => void;
    onRetryFailed: () => void; // Unified: handles both extraction + prediction
    retryIngestionLoading: boolean;
    retryFailedLoading: boolean;
}

export function IssuesTab({
    repoId,
    failedIngestionCount,
    failedExtractionCount,
    failedPredictionCount,
    onRetryIngestion,
    onRetryFailed,
    retryIngestionLoading,
    retryFailedLoading,
}: IssuesTabProps) {
    const [failedImports, setFailedImports] = useState<FailedImportBuild[]>([]);
    const [loading, setLoading] = useState(true);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            // Only fetch failed import builds - extraction failures come from parent progress
            const importRes = await reposApi.getFailedImportBuilds(repoId, 20);
            setFailedImports(importRes.failed_builds);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [repoId]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const totalFailed = failedIngestionCount + failedExtractionCount + failedPredictionCount;

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (totalFailed === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <div className="text-green-600 text-lg font-medium">✓ No Issues</div>
                    <p className="text-muted-foreground mt-1">All builds processed successfully</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary */}
            <div className="flex items-center gap-4 p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <div className="flex-1">
                    <span className="font-medium text-amber-700 dark:text-amber-400">
                        {totalFailed} build(s) need attention
                    </span>
                </div>
            </div>

            {/* Failed Ingestion */}
            {failedIngestionCount > 0 && (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base">Failed Ingestion</CardTitle>
                                <CardDescription>{failedIngestionCount} build(s) failed during data collection</CardDescription>
                            </div>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={onRetryIngestion}
                                disabled={retryIngestionLoading}
                            >
                                {retryIngestionLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry All
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-4 py-2 text-left font-medium text-slate-500">CI Run ID</th>
                                    <th className="px-4 py-2 text-left font-medium text-slate-500">Commit</th>
                                    <th className="px-4 py-2 text-left font-medium text-slate-500">Error</th>
                                    <th className="px-4 py-2 text-left font-medium text-slate-500">Date</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {failedImports.map((build) => (
                                    <tr key={build.id}>
                                        <td className="px-4 py-3 font-mono text-xs">{build.ci_run_id}</td>
                                        <td className="px-4 py-3 font-mono text-xs">{build.commit_sha?.substring(0, 7)}</td>
                                        <td className="px-4 py-3">
                                            <span className="text-red-600 text-xs">
                                                {build.ingestion_error || Object.values(build.resource_errors).join(", ") || "Unknown error"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground text-xs">
                                            {build.fetched_at ? formatTimestamp(build.fetched_at) : "—"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </CardContent>
                </Card>
            )}

            {/* Processing Failures (Extraction + Prediction) */}
            {(failedExtractionCount > 0 || failedPredictionCount > 0) && (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base">Processing Failures</CardTitle>
                                <CardDescription>
                                    {failedExtractionCount > 0 && failedPredictionCount > 0
                                        ? `${failedExtractionCount} extraction + ${failedPredictionCount} prediction failures`
                                        : failedExtractionCount > 0
                                            ? `${failedExtractionCount} build(s) failed during feature extraction`
                                            : `${failedPredictionCount} build(s) failed during risk prediction`
                                    }
                                </CardDescription>
                            </div>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={onRetryFailed}
                                disabled={retryFailedLoading}
                            >
                                {retryFailedLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry All ({failedExtractionCount + failedPredictionCount})
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground">
                            {failedExtractionCount > 0 && (
                                <span>{failedExtractionCount} builds failed extraction. </span>
                            )}
                            {failedPredictionCount > 0 && (
                                <span>{failedPredictionCount} builds failed prediction. </span>
                            )}
                            Click &quot;Retry All&quot; to retry all failed builds.
                        </p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
