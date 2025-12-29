"use client";

import {
    ArrowLeft,
    CheckCircle2,
    Clock,
    GitCommit,
    Loader2,
    XCircle,
    RefreshCw,
    AlertCircle,
    RotateCcw,
    Globe,
    Lock,
    GitBranch,
    ExternalLink,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { useParams, useRouter } from "next/navigation";
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
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi, reposApi } from "@/lib/api";
import { formatDurationFromSeconds, formatTimestamp } from "@/lib/utils";
import type { Build, RepoDetail } from "@/types";

import { ExportPanel } from "./_components/ExportPanel";

const PAGE_SIZE = 20;

enum BuildStatus {
    SUCCESS = "success",
    PASSED = "passed",
    FAILURE = "failure",
    CANCELLED = "cancelled",
    SKIPPED = "skipped",
    TIMED_OUT = "timed_out",
    NEUTRAL = "neutral",
    UNKNOWN = "unknown",
}

enum ExtractionStatus {
    PENDING = "pending",
    COMPLETED = "completed",
    PARTIAL = "partial",
    FAILED = "failed",
}


function StatusBadge({ status }: { status: string }) {
    const normalizedStatus = status.toLowerCase();

    if (normalizedStatus === BuildStatus.SUCCESS || normalizedStatus === BuildStatus.PASSED) {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Passed
            </Badge>
        );
    }

    if (normalizedStatus === BuildStatus.FAILURE || normalizedStatus === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }

    if ([BuildStatus.CANCELLED, "canceled"].includes(normalizedStatus as BuildStatus)) {
        return (
            <Badge variant="secondary" className="gap-1">
                <XCircle className="h-3 w-3" /> Cancelled
            </Badge>
        );
    }

    if (normalizedStatus === BuildStatus.SKIPPED) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Skipped
            </Badge>
        );
    }

    if (normalizedStatus === BuildStatus.TIMED_OUT) {
        return (
            <Badge variant="destructive" className="gap-1">
                <Clock className="h-3 w-3" /> Timed Out
            </Badge>
        );
    }

    if (normalizedStatus === BuildStatus.NEUTRAL) {
        return (
            <Badge variant="secondary" className="gap-1">
                <CheckCircle2 className="h-3 w-3" /> Neutral
            </Badge>
        );
    }

    if (normalizedStatus === "action_required") {
        return (
            <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                <AlertCircle className="h-3 w-3" /> Action Required
            </Badge>
        );
    }

    if (normalizedStatus === "startup_failure") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Startup Failed
            </Badge>
        );
    }

    if (normalizedStatus === "stale") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Stale
            </Badge>
        );
    }

    if (normalizedStatus === "queued") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Queued
            </Badge>
        );
    }

    if (normalizedStatus === BuildStatus.UNKNOWN || normalizedStatus === "unknown") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Unknown
            </Badge>
        );
    }

    return <Badge variant="secondary">{status}</Badge>;
}

function ExtractionStatusBadge({ status, hasTrainingData }: { status?: string; hasTrainingData: boolean }) {
    // No training data yet = not started
    if (!hasTrainingData) {
        return (
            <Badge variant="outline" className="border-slate-400 text-slate-500 gap-1">
                <Clock className="h-3 w-3" /> Not Started
            </Badge>
        );
    }

    const normalizedStatus = (status || "").toLowerCase();

    if (normalizedStatus === ExtractionStatus.COMPLETED) {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Done
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.PARTIAL) {
        return (
            <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                <AlertCircle className="h-3 w-3" /> Partial
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.FAILED) {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.PENDING) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> Processing
            </Badge>
        );
    }

    return <Badge variant="secondary" className="text-xs">{status || "Unknown"}</Badge>;
}


export default function RepoBuildsPage() {
    const params = useParams();
    const router = useRouter();
    const repoId = params.repoId as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);


    // Search state
    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearchQuery = useDebounce(searchQuery, 500);

    // Lazy Sync State
    const [syncing, setSyncing] = useState(false);

    const [reprocessingBuilds, setReprocessingBuilds] = useState<Record<string, boolean>>({});

    const { subscribe } = useWebSocket();

    const loadRepo = useCallback(async () => {
        try {
            const data = await reposApi.get(repoId);
            setRepo(data);
        } catch (err) {
            console.error(err);
        }
    }, [repoId]);

    const handleSync = async () => {
        setSyncing(true);
        try {
            await reposApi.triggerLazySync(repoId);
            // Optimistically update UI or show a toast
            // For now, we rely on WebSocket or polling to update the list eventually
        } catch (err) {
            console.error("Failed to trigger sync", err);
        } finally {
            setSyncing(false);
        }
    };

    // Scan functionality removed - scanning is now pipeline-driven

    const loadBuilds = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) {
                setTableLoading(true);
            }
            try {
                const data = await buildApi.getByRepo(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: debouncedSearchQuery || undefined,
                });
                setBuilds(data.items);
                setTotal(data.total);
                setPage(pageNumber);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
                setTableLoading(false);
            }
        },
        [repoId, debouncedSearchQuery]
    );

    useEffect(() => {
        loadRepo();
        loadBuilds(1, true);
    }, [loadRepo, loadBuilds]);

    // WebSocket connection - BUILD_UPDATE for builds list
    useEffect(() => {
        const unsubscribe = subscribe("BUILD_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                // If it's a new build or update, reload the list
                // Optimally we would update the list in place, but reloading is safer for now
                loadBuilds(page);
            }
        });

        return () => {
            unsubscribe();
        };
    }, [subscribe, loadBuilds, page, repoId]);

    // WebSocket connection - REPO_UPDATE for repo stats (builds processed, last sync)
    useEffect(() => {
        const unsubscribe = subscribe("REPO_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                // Reload repo to get updated stats (total builds, last sync time)
                loadRepo();
            }
        });

        return () => {
            unsubscribe();
        };
    }, [subscribe, loadRepo, repoId]);

    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
    const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

    const handlePageChange = (direction: "prev" | "next") => {
        const targetPage =
            direction === "prev"
                ? Math.max(1, page - 1)
                : Math.min(totalPages, page + 1);
        if (targetPage !== page) {
            void loadBuilds(targetPage, true);
        }
    };

    if (loading && !repo) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push("/repositories")}
                        className="gap-2"
                    >
                        <ArrowLeft className="h-4 w-4" />
                        Back to Repos
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">
                            {repo?.full_name || "Repository Builds"}
                        </h1>
                        <p className="text-muted-foreground">
                            View and analyze build history.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-64">
                        <Input
                            placeholder="Search builds..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="h-9"
                        />
                    </div>
                    <ExportPanel repoId={repoId} repoName={repo?.full_name} />
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSync}
                        disabled={syncing}
                        title="Sync builds from GitHub"
                    >
                        {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                        Sync Builds
                    </Button>
                </div>
            </div>



            {/* Repository Info Card */}
            {repo && (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <CardTitle className="text-lg">{repo.full_name}</CardTitle>
                                <Badge variant={repo.is_private ? "secondary" : "outline"} className="gap-1">
                                    {repo.is_private ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                                    {repo.is_private ? "Private" : "Public"}
                                </Badge>
                            </div>
                            {repo.metadata?.html_url && (
                                <a
                                    href={repo.metadata.html_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    <ExternalLink className="h-4 w-4" />
                                    View on GitHub
                                </a>
                            )}
                        </div>
                        {repo.metadata?.description && (
                            <CardDescription className="mt-1">
                                {repo.metadata.description}
                            </CardDescription>
                        )}
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-6 text-sm">
                            <div className="flex items-center gap-2">
                                <GitBranch className="h-4 w-4 text-muted-foreground" />
                                <span className="text-muted-foreground">Default branch:</span>
                                <span className="font-medium">{repo.default_branch || "main"}</span>
                            </div>
                            {repo.main_lang && (
                                <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">Language:</span>
                                    <Badge variant="outline">{repo.main_lang}</Badge>
                                </div>
                            )}
                            {repo.source_languages?.length > 0 && (
                                <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">Configured languages:</span>
                                    <div className="flex gap-1">
                                        {repo.source_languages.map((lang) => (
                                            <Badge key={lang} variant="secondary" className="text-xs">{lang}</Badge>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {repo.test_frameworks?.length > 0 && (
                                <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">Test frameworks:</span>
                                    <div className="flex gap-1">
                                        {repo.test_frameworks.map((fw) => (
                                            <Badge key={fw} variant="secondary" className="text-xs">{fw}</Badge>
                                        ))}
                                    </div>
                                </div>
                            )}
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Total builds:</span>
                                <span className="font-medium">{repo.builds_fetched.toLocaleString()}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Processed:</span>
                                <span className="font-medium">
                                    {(repo.builds_processed || 0).toLocaleString()}
                                    {repo.builds_failed ? (
                                        <span className="text-red-500 ml-1">
                                            ({repo.builds_failed} failed)
                                        </span>
                                    ) : null}
                                </span>
                            </div>
                            {repo.last_synced_at && (
                                <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">Last synced:</span>
                                    <span className="font-medium">{formatTimestamp(repo.last_synced_at)}</span>
                                </div>
                            )}
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">CI Provider:</span>
                                <Badge variant="outline">{repo.ci_provider}</Badge>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}



            <Card>
                <CardHeader>
                    <CardTitle>Build History</CardTitle>
                    <CardDescription>
                        Builds with extracted features for model training.
                    </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Build
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Build ID
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Status
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Commit
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Branch
                                    </th>

                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Date
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Extraction
                                    </th>
                                    <th className="px-6 py-3" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {builds.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={7}
                                            className="px-6 py-6 text-center text-sm text-muted-foreground"
                                        >
                                            No builds recorded yet.
                                        </td>
                                    </tr>
                                ) : (
                                    builds.map((build) => (
                                        <tr
                                            key={build.id}
                                            className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                            onClick={() => router.push(`/repositories/${repoId}/builds/${build.id}`)}
                                        >
                                            <td className="px-6 py-4 font-medium">
                                                #{build.build_number || "—"}
                                            </td>
                                            <td className="px-6 py-4 font-mono text-xs text-muted-foreground">
                                                {build.build_id}
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-2">
                                                    <StatusBadge status={build.conclusion} />
                                                    {build.extraction_error && (
                                                        <div title={build.extraction_error} className="text-yellow-500">
                                                            <AlertCircle className="h-4 w-4" />
                                                        </div>
                                                    )}
                                                    {build.missing_resources && build.missing_resources.length > 0 && (
                                                        <div
                                                            title={`Missing resources: ${build.missing_resources.join(", ")}`}
                                                            className="text-orange-400"
                                                        >
                                                            <AlertCircle className="h-4 w-4" />
                                                        </div>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-1 font-mono text-xs">
                                                    <GitCommit className="h-3 w-3" />
                                                    {build.commit_sha.substring(0, 7)}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground text-xs">
                                                {build.branch}
                                            </td>

                                            <td className="px-6 py-4 text-muted-foreground">
                                                {formatTimestamp(build.created_at)}
                                            </td>
                                            <td className="px-6 py-4">
                                                <ExtractionStatusBadge status={build.extraction_status} hasTrainingData={build.has_training_data} />
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={async (e) => {
                                                            e.stopPropagation();
                                                            if (reprocessingBuilds[build.id]) return;
                                                            setReprocessingBuilds((prev) => ({ ...prev, [build.id]: true }));
                                                            try {
                                                                await buildApi.reprocess(repoId, build.id);
                                                            } catch (err) {
                                                                console.error("Failed to reprocess build", err);
                                                            } finally {
                                                                setReprocessingBuilds((prev) => ({ ...prev, [build.id]: false }));
                                                            }
                                                        }}
                                                        disabled={reprocessingBuilds[build.id]}
                                                        title="Reprocess this build"
                                                    >
                                                        {reprocessingBuilds[build.id] ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <RotateCcw className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            router.push(`/repositories/${repoId}/builds/${build.id}`);
                                                        }}
                                                    >
                                                        View
                                                    </Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
                <div className="flex flex-col gap-3 border-t border-slate-200 px-6 py-4 text-sm text-muted-foreground dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        {total > 0
                            ? `Showing ${pageStart}-${pageEnd} of ${total} builds`
                            : "No builds to display"}
                    </div>
                    <div className="flex items-center gap-3">
                        {tableLoading ? (
                            <div className="flex items-center gap-2">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-xs">Refreshing...</span>
                            </div>
                        ) : null}
                        <div className="flex items-center gap-2">
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handlePageChange("prev")}
                                disabled={page === 1 || tableLoading}
                            >
                                Previous
                            </Button>
                            <span className="text-xs text-muted-foreground">
                                Page {page} of {totalPages}
                            </span>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handlePageChange("next")}
                                disabled={page >= totalPages || tableLoading}
                            >
                                Next
                            </Button>
                        </div>
                    </div>
                </div>
            </Card>



        </div >
    );
}
