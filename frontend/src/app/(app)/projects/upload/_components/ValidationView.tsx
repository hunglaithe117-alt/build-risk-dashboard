"use client";

import {
    AlertCircle,
    AlertTriangle,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Loader2,
    Pause,
    Play,
    RotateCcw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { datasetsApi } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";
import type { UploadDatasetModalProps } from "../_components/types";
import { useUploadDatasetWizard } from "../_components/hooks/useUploadDatasetWizard";

// Logic repurposed from UploadDatasetModal/index.tsx

interface RepoStatItem {
    id: string;
    full_name: string;
    builds_total: number;
    builds_found: number;
    builds_not_found: number;
    builds_filtered: number;
}

const REPOS_PER_PAGE = 20;

interface ValidationViewProps {
    wizard: ReturnType<typeof useUploadDatasetWizard>;
}

export function ValidationView({ wizard }: ValidationViewProps) {
    const {
        datasetId,
        validationStatus,
        validationProgress,
        validationStats,
        validationError,
    } = wizard;

    // Repo stats state
    const [repoStats, setRepoStats] = useState<RepoStatItem[]>([]);
    const [repoStatsTotal, setRepoStatsTotal] = useState(0);
    const [repoStatsPage, setRepoStatsPage] = useState(0);
    const [repoStatsLoading, setRepoStatsLoading] = useState(false);

    // Fetch repo stats when validation completes
    const fetchRepoStats = useCallback(async (dId: string, page: number = 0) => {
        setRepoStatsLoading(true);
        try {
            const result = await datasetsApi.getRepoStats(dId, {
                skip: page * REPOS_PER_PAGE,
                limit: REPOS_PER_PAGE,
            });
            setRepoStats(result.items);
            setRepoStatsTotal(result.total);
        } catch (err) {
            console.error("Failed to fetch repo stats:", err);
        } finally {
            setRepoStatsLoading(false);
        }
    }, []);

    // Effect to fetch stats
    useEffect(() => {
        if (validationStatus === "completed" && datasetId) {
            fetchRepoStats(datasetId, repoStatsPage);
        }
    }, [validationStatus, datasetId, repoStatsPage, fetchRepoStats]);

    // Reset stats on unmount or status change?
    // Actually, we want to keep them if completed.

    const totalPages = Math.ceil(repoStatsTotal / REPOS_PER_PAGE);

    return (
        <div className="space-y-6">
            {/* Status Header */}
            <div className="flex items-center gap-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-900 border">
                {validationStatus === "validating" && (
                    <div className="flex items-center gap-3 text-blue-600">
                        <div className="relative">
                            <Loader2 className="h-6 w-6 animate-spin" />
                            <span className="absolute inset-0 flex items-center justify-center text-[8px] font-bold">
                                {validationProgress}%
                            </span>
                        </div>
                        <div>
                            <p className="font-semibold">Validating builds...</p>
                            <p className="text-sm text-muted-foreground">Please wait while we verify build data.</p>
                        </div>
                    </div>
                )}
                {validationStatus === "completed" && (
                    <div className="flex items-center gap-3 text-emerald-600">
                        <div className="rounded-full bg-emerald-100 p-2 dark:bg-emerald-900/30">
                            <CheckCircle2 className="h-6 w-6" />
                        </div>
                        <div>
                            <p className="font-semibold">Validation complete</p>
                            <p className="text-sm text-muted-foreground text-emerald-600/80">All builds processed successfully.</p>
                        </div>
                    </div>
                )}
                {validationStatus === "failed" && (
                    <div className="flex items-center gap-3 text-red-600">
                        <div className="rounded-full bg-red-100 p-2 dark:bg-red-900/30">
                            <AlertTriangle className="h-6 w-6" />
                        </div>
                        <div>
                            <p className="font-semibold">Validation failed</p>
                            <p className="text-sm text-red-600/80">Something went wrong during validation.</p>
                        </div>
                    </div>
                )}
            </div>

            {/* Progress Bar for Validating */}
            {validationStatus === "validating" && (
                <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Progress</span>
                        <span>{validationProgress}%</span>
                    </div>
                    <Progress value={validationProgress} className="h-2" />
                </div>
            )}

            {/* Error Message */}
            {validationError && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                    <p className="text-sm text-red-700 dark:text-red-300">
                        {validationError}
                    </p>
                </div>
            )}

            {/* Stats Summary Cards */}
            {validationStats && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-lg border bg-card p-4 shadow-sm">
                        <p className="text-xs uppercase text-muted-foreground font-semibold">Total Repos</p>
                        <p className="mt-2 text-3xl font-bold">{validationStats.repos_total}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            {validationStats.repos_valid} valid
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4 shadow-sm">
                        <p className="text-xs uppercase text-muted-foreground font-semibold">Builds Found</p>
                        <p className="mt-2 text-3xl font-bold text-emerald-600 dark:text-emerald-500">{validationStats.builds_found}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Valid builds mapped
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4 shadow-sm">
                        <p className="text-xs uppercase text-muted-foreground font-semibold">Builds Filtered</p>
                        <p className="mt-2 text-3xl font-bold text-blue-600 dark:text-blue-500">{validationStats.builds_filtered ?? 0}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Excluded by filters
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4 shadow-sm">
                        <p className="text-xs uppercase text-muted-foreground font-semibold">Builds Missing</p>
                        <p className="mt-2 text-3xl font-bold text-amber-600 dark:text-amber-500">{validationStats.builds_not_found}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Not found in CI
                        </p>
                    </div>
                </div>
            )}

            {/* Build Coverage Bar */}
            {validationStats && validationStats.builds_total > 0 && (
                <div className="rounded-lg border p-4 bg-card">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium">Build Coverage</span>
                        <span className="text-lg font-bold">
                            {Math.round((validationStats.builds_found / validationStats.builds_total) * 100)}%
                        </span>
                    </div>
                    <Progress
                        value={(validationStats.builds_found / validationStats.builds_total) * 100}
                        className="h-3"
                    />
                    <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                        <span>{validationStats.builds_found} found</span>
                        <span>{validationStats.builds_total} total rows</span>
                    </div>
                </div>
            )}

            {/* Per-Repo Stats Table (Paginated) */}
            {validationStatus === "completed" && (
                <div className="rounded-lg border overflow-hidden bg-card">
                    <div className="bg-muted/50 px-4 py-3 border-b flex items-center justify-between">
                        <span className="font-medium">Repository Details</span>
                        {totalPages > 1 && (
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="icon"
                                    className="h-8 w-8"
                                    onClick={() => setRepoStatsPage(Math.max(0, repoStatsPage - 1))}
                                    disabled={repoStatsPage === 0 || repoStatsLoading}
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                </Button>
                                <span className="text-xs text-muted-foreground w-12 text-center">
                                    {repoStatsPage + 1} / {totalPages}
                                </span>
                                <Button
                                    variant="outline"
                                    size="icon"
                                    className="h-8 w-8"
                                    onClick={() => setRepoStatsPage(Math.min(totalPages - 1, repoStatsPage + 1))}
                                    disabled={repoStatsPage >= totalPages - 1 || repoStatsLoading}
                                >
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                    </div>
                    <div className="max-h-[400px] overflow-y-auto">
                        {repoStatsLoading ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : repoStats.length > 0 ? (
                            <table className="w-full text-sm">
                                <thead className="bg-muted/30 sticky top-0 z-10 backdrop-blur-md">
                                    <tr>
                                        <th className="text-left px-4 py-3 font-medium">Repository</th>
                                        <th className="text-center px-2 py-3 font-medium">Found</th>
                                        <th className="text-center px-2 py-3 font-medium">Filtered</th>
                                        <th className="text-center px-2 py-3 font-medium">Missing</th>
                                        <th className="text-center px-2 py-3 font-medium">Total</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {repoStats.map((repo) => (
                                        <tr key={repo.id} className="hover:bg-muted/20 transition-colors">
                                            <td className="px-4 py-3 font-mono text-xs truncate max-w-[200px]" title={repo.full_name}>
                                                {repo.full_name}
                                            </td>
                                            <td className="text-center px-2 py-3 text-emerald-600 font-medium bg-emerald-50/30 dark:bg-emerald-900/10">
                                                {repo.builds_found}
                                            </td>
                                            <td className="text-center px-2 py-3 text-blue-600 font-medium bg-blue-50/30 dark:bg-blue-900/10">
                                                {repo.builds_filtered}
                                            </td>
                                            <td className="text-center px-2 py-3 text-amber-600 font-medium bg-amber-50/30 dark:bg-amber-900/10">
                                                {repo.builds_not_found}
                                            </td>
                                            <td className="text-center px-2 py-3 text-muted-foreground">
                                                {repo.builds_total}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div className="py-12 text-center text-muted-foreground">
                                No repository data available
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
