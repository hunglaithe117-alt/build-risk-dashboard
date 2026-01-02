"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWebSocket } from "@/contexts/websocket-context";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    CheckCircle2,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Loader2,
    XCircle,
    AlertTriangle,
    Clock,
    Lock,
    Play,
    ExternalLink,
    GitCommit,
    Timer,
    FileText,
    RotateCcw,
} from "lucide-react";
import { datasetVersionApi, type ImportBuildItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
    SearchFilterBar,
    DATASET_INGESTION_STATUS_OPTIONS,
} from "@/components/builds";

const ITEMS_PER_PAGE = 20;

/** Format relative time */
const formatRelativeTime = (dateStr: string | null): string => {
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
    return date.toLocaleDateString();
};

/** Status config for import builds */
const getImportStatusConfig = (status: string) => {
    const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
        pending: { icon: Clock, color: "text-gray-500", label: "Pending" },
        fetched: { icon: CheckCircle2, color: "text-blue-500", label: "Fetched" },
        ingesting: { icon: Loader2, color: "text-blue-500", label: "Ingesting" },
        ingested: { icon: CheckCircle2, color: "text-green-500", label: "Ingested" },
        missing_resource: { icon: AlertTriangle, color: "text-amber-500", label: "Missing Resource" },
        failed: { icon: XCircle, color: "text-red-500", label: "Failed" },
    };
    return config[status] || { icon: Clock, color: "text-gray-400", label: status };
};

export default function IngestionPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const router = useRouter();
    const { subscribe } = useWebSocket();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    const [currentPage, setCurrentPage] = useState(1);
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [builds, setBuilds] = useState<ImportBuildItem[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [versionStatus, setVersionStatus] = useState<string>("queued");
    const [startProcessingLoading, setStartProcessingLoading] = useState(false);
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [failedCount, setFailedCount] = useState(0);

    // Processing progress state
    const [processingProgress, setProcessingProgress] = useState<{
        builds_processed: number;
        builds_total: number;
        progress: number;
    } | null>(null);

    // Subscribe to WebSocket updates for real-time ingestion status
    useEffect(() => {
        const unsubscribe = subscribe("INGESTION_BUILD_UPDATE", (data: any) => {
            // Check if this update is for our version (dataset pipeline)
            if (data.repo_id === versionId && data.pipeline_type === "dataset") {
                const { resource, status, commit_shas, build_ids } = data;

                // Granular update based on resource type
                setBuilds((prevBuilds) =>
                    prevBuilds.map((build) => {
                        let shouldUpdate = false;

                        if (resource === "git_history") {
                            // git_history: Update ALL builds (clone is repo-level)
                            shouldUpdate = true;
                        } else if (resource === "git_worktree" && commit_shas?.length) {
                            // git_worktree: Update builds with matching commit_sha
                            shouldUpdate = commit_shas.includes(build.commit_sha);
                        } else if (resource === "build_logs" && build_ids?.length) {
                            // build_logs: Update builds with matching build_id
                            shouldUpdate = build_ids.includes(build.build_id);
                        }

                        if (shouldUpdate) {
                            return {
                                ...build,
                                resource_status: {
                                    ...build.resource_status,
                                    [resource]: {
                                        ...build.resource_status?.[resource],
                                        status: status,
                                    },
                                },
                            };
                        }
                        return build;
                    })
                );
            }
        });
        return () => unsubscribe();
    }, [subscribe, versionId]);

    // Subscribe to ENRICHMENT_UPDATE for processing progress
    useEffect(() => {
        const unsubscribe = subscribe("ENRICHMENT_UPDATE", (data: any) => {
            if (data.version_id === versionId) {
                // Update version status
                if (data.status) {
                    setVersionStatus(data.status);
                }
                // Update processing progress
                if (data.status === "processing" || data.status === "processed") {
                    setProcessingProgress({
                        builds_processed: data.builds_processed || 0,
                        builds_total: data.builds_total || 0,
                        progress: data.progress || 0,
                    });
                }
                // Clear progress when completed
                if (data.status === "processed") {
                    setProcessingProgress(null);
                }
            }
        });
        return () => unsubscribe();
    }, [subscribe, versionId]);

    // Fetch version status
    useEffect(() => {
        async function fetchVersion() {
            try {
                const response = await datasetVersionApi.getVersionData(
                    datasetId,
                    versionId,
                    1,
                    1,
                    false
                );
                setVersionStatus(response.version.status);
            } catch (err) {
                console.error("Failed to fetch version:", err);
            }
        }
        fetchVersion();
    }, [datasetId, versionId]);

    // Fetch import builds
    useEffect(() => {
        async function fetchBuilds() {
            setLoading(true);
            try {
                const skip = (currentPage - 1) * ITEMS_PER_PAGE;
                const response = await datasetVersionApi.getImportBuilds(
                    datasetId,
                    versionId,
                    skip,
                    ITEMS_PER_PAGE,
                    statusFilter !== "all" ? statusFilter : undefined
                );
                // Client-side search filter
                let filteredItems = response.items;
                if (searchQuery) {
                    const searchLower = searchQuery.toLowerCase();
                    filteredItems = response.items.filter(item =>
                        item.commit_sha.toLowerCase().includes(searchLower) ||
                        item.build_id.toLowerCase().includes(searchLower) ||
                        (item.branch && item.branch.toLowerCase().includes(searchLower))
                    );
                }
                setBuilds(filteredItems);
                setTotal(searchQuery ? filteredItems.length : response.total);
            } catch (err) {
                console.error("Failed to fetch import builds:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchBuilds();
    }, [datasetId, versionId, currentPage, searchQuery, statusFilter]);

    // Fetch failed count for retry button
    useEffect(() => {
        async function fetchFailedCount() {
            try {
                const response = await datasetVersionApi.getImportBuilds(
                    datasetId, versionId, 0, 1, "failed"
                );
                setFailedCount(response.total);
            } catch (err) {
                console.error("Failed to fetch failed count:", err);
            }
        }
        fetchFailedCount();
    }, [datasetId, versionId, builds]);

    const handleSearch = useCallback((query: string) => {
        setSearchQuery(query);
        setCurrentPage(1);
    }, []);

    const handleStatusFilter = useCallback((status: string) => {
        setStatusFilter(status);
        setCurrentPage(1);
    }, []);

    const handleStartProcessing = async () => {
        setStartProcessingLoading(true);
        try {
            await datasetVersionApi.startProcessing(datasetId, versionId);
            // Refresh to update status
            const response = await datasetVersionApi.getVersionData(datasetId, versionId, 1, 1, false);
            setVersionStatus(response.version.status);
        } catch (err) {
            console.error("Failed to start processing:", err);
        } finally {
            setStartProcessingLoading(false);
        }
    };

    const handleRetryIngestion = async () => {
        setRetryIngestionLoading(true);
        try {
            await datasetVersionApi.retryIngestion(datasetId, versionId);
            // Refresh version and builds
            const response = await datasetVersionApi.getVersionData(datasetId, versionId, 1, 1, false);
            setVersionStatus(response.version.status);
            setCurrentPage(1);
        } catch (err) {
            console.error("Failed to retry ingestion:", err);
        } finally {
            setRetryIngestionLoading(false);
        }
    };

    const totalPages = Math.ceil(total / ITEMS_PER_PAGE);
    const canStartProcessing = versionStatus.toLowerCase() === "ingested";
    const canRetryIngestion = failedCount > 0;

    return (
        <div className="space-y-4">
            {/* Search and Filter */}
            <SearchFilterBar
                placeholder="Search by commit SHA, build ID, or branch..."
                statusOptions={DATASET_INGESTION_STATUS_OPTIONS}
                onSearch={handleSearch}
                onStatusFilter={handleStatusFilter}
                isLoading={loading}
            />

            {/* Processing Progress Card */}
            {versionStatus === "processing" && (
                <Card className="border-purple-200 bg-purple-50 dark:border-purple-800 dark:bg-purple-950/30">
                    <CardContent className="py-4">
                        <div className="flex items-center gap-4">
                            <Loader2 className="h-5 w-5 animate-spin text-purple-600" />
                            <div className="flex-1">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
                                        Feature Extraction in Progress
                                    </span>
                                    <span className="text-sm text-purple-600 dark:text-purple-400">
                                        {processingProgress?.builds_processed || 0} / {processingProgress?.builds_total || total} builds
                                    </span>
                                </div>
                                <div className="h-2 w-full rounded-full bg-purple-200 dark:bg-purple-900 overflow-hidden">
                                    <div
                                        className="h-full bg-purple-600 transition-all duration-500"
                                        style={{ width: `${processingProgress?.progress || 0}%` }}
                                    />
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Builds Table */}
            {loading ? (
                <div className="flex min-h-[200px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <ImportBuildsTable
                    builds={builds}
                    total={total}
                    canStartProcessing={canStartProcessing}
                    onStartProcessing={handleStartProcessing}
                    startProcessingLoading={startProcessingLoading}
                    canRetryIngestion={canRetryIngestion}
                    onRetryIngestion={handleRetryIngestion}
                    retryIngestionLoading={retryIngestionLoading}
                    failedCount={failedCount}
                />
            )}

            {/* Pagination */}
            <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                    Showing {Math.min(builds.length, ITEMS_PER_PAGE)} of {total} builds
                </p>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                    >
                        <ChevronLeft className="h-4 w-4" />
                        Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">
                        Page {currentPage} of {Math.max(1, totalPages)}
                    </span>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage >= totalPages || totalPages <= 1}
                    >
                        Next
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}

/** Import Builds Table */
function ImportBuildsTable({
    builds,
    total,
    canStartProcessing = false,
    onStartProcessing,
    startProcessingLoading = false,
    canRetryIngestion = false,
    onRetryIngestion,
    retryIngestionLoading = false,
    failedCount = 0,
}: {
    builds: ImportBuildItem[];
    total: number;
    canStartProcessing?: boolean;
    onStartProcessing?: () => void;
    startProcessingLoading?: boolean;
    canRetryIngestion?: boolean;
    onRetryIngestion?: () => void;
    retryIngestionLoading?: boolean;
    failedCount?: number;
}) {
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const toggleExpand = (id: string) => {
        setExpandedId((prev) => (prev === id ? null : id));
    };

    const formatDuration = (seconds?: number) => {
        if (!seconds) return "—";
        if (seconds < 60) return `${seconds.toFixed(0)}s`;
        if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
        return `${(seconds / 3600).toFixed(1)}h`;
    };

    if (builds.length === 0) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    No import builds found
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Import Builds</CardTitle>
                        <CardDescription>
                            {total} builds in data collection phase
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        {onRetryIngestion && (
                            <Button
                                variant="outline"
                                onClick={onRetryIngestion}
                                disabled={retryIngestionLoading || failedCount === 0}
                                className={cn("gap-2", failedCount === 0 && "opacity-50")}
                            >
                                {retryIngestionLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="h-4 w-4" />
                                )}
                                Retry Failed ({failedCount})
                            </Button>
                        )}
                        {canStartProcessing && onStartProcessing && (
                            <Button onClick={onStartProcessing} disabled={startProcessingLoading} className="gap-2">
                                {startProcessingLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Play className="h-4 w-4" />
                                )}
                                Start Processing
                            </Button>
                        )}
                    </div>
                </div>
            </CardHeader>
            <CardContent className="space-y-2">
                {builds.map((build) => {
                    const statusConfig = getImportStatusConfig(build.status);
                    const StatusIcon = statusConfig.icon;
                    const isExpanded = expandedId === build.id;

                    return (
                        <div key={build.id} className="border rounded-lg overflow-hidden">
                            {/* Main Row - Clickable */}
                            <div
                                className="flex items-center gap-4 p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                                onClick={() => toggleExpand(build.id)}
                            >
                                <ChevronDown className={cn("h-4 w-4 transition-transform", isExpanded && "rotate-180")} />

                                <span className="font-mono text-sm w-[80px]">
                                    {build.build_number ? `#${build.build_number}` : `...${build.build_id.slice(-6)}`}
                                </span>

                                <span className="font-mono text-sm w-[80px]">
                                    {build.commit_sha.slice(0, 7)}
                                </span>

                                <span className="text-sm truncate max-w-[120px]">
                                    {build.branch}
                                </span>

                                <Badge variant="outline" className={cn("ml-auto", statusConfig.color)}>
                                    <StatusIcon className={cn("mr-1 h-3 w-3", build.status === "ingesting" && "animate-spin")} />
                                    {statusConfig.label}
                                </Badge>

                                <ResourceStatusBadges resourceStatus={build.resource_status} />

                                <span className="text-xs text-muted-foreground w-[80px] text-right">
                                    {formatRelativeTime(build.ingested_at)}
                                </span>
                            </div>

                            {/* Expanded Details */}
                            {isExpanded && (
                                <div className="border-t bg-muted/30 p-4 space-y-4">
                                    {/* Commit Info */}
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <h4 className="text-sm font-medium flex items-center gap-2">
                                                <GitCommit className="h-4 w-4" />
                                                Commit Info
                                            </h4>
                                            <div className="text-sm space-y-1 text-muted-foreground">
                                                <p><span className="font-medium">SHA:</span> <code className="text-xs">{build.commit_sha}</code></p>
                                                {build.commit_message && (
                                                    <p className="truncate"><span className="font-medium">Message:</span> {build.commit_message}</p>
                                                )}
                                                {build.commit_author && (
                                                    <p><span className="font-medium">Author:</span> {build.commit_author}</p>
                                                )}
                                            </div>
                                        </div>

                                        {/* CI Build Info */}
                                        <div className="space-y-2">
                                            <h4 className="text-sm font-medium flex items-center gap-2">
                                                <Timer className="h-4 w-4" />
                                                CI Build Info
                                            </h4>
                                            <div className="text-sm space-y-1 text-muted-foreground">
                                                <p><span className="font-medium">Provider:</span> {build.provider || "—"}</p>
                                                <p><span className="font-medium">Conclusion:</span> {build.conclusion || "—"}</p>
                                                <p><span className="font-medium">Duration:</span> {formatDuration(build.duration_seconds)}</p>
                                                {build.web_url && (
                                                    <a
                                                        href={build.web_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-600 hover:underline flex items-center gap-1"
                                                        onClick={(e) => e.stopPropagation()}
                                                    >
                                                        View on CI <ExternalLink className="h-3 w-3" />
                                                    </a>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Resources Collected */}
                                    <div className="space-y-2">
                                        <h4 className="text-sm font-medium flex items-center gap-2">
                                            <FileText className="h-4 w-4" />
                                            Resources Collected
                                        </h4>
                                        <div className="grid grid-cols-3 gap-2">
                                            {Object.entries(build.resource_status || {}).map(([resource, info]) => (
                                                <div
                                                    key={resource}
                                                    className={cn(
                                                        "p-2 rounded text-xs border",
                                                        info.status === "completed" && "bg-green-50 border-green-200 dark:bg-green-950/30",
                                                        info.status === "failed" && "bg-red-50 border-red-200 dark:bg-red-950/30",
                                                        info.status === "pending" && "bg-gray-50 border-gray-200 dark:bg-gray-950/30",
                                                    )}
                                                >
                                                    <div className="font-medium capitalize">{resource.replace(/_/g, " ")}</div>
                                                    <div className={cn(
                                                        info.status === "completed" && "text-green-600",
                                                        info.status === "failed" && "text-red-600",
                                                    )}>
                                                        {info.status}
                                                    </div>
                                                    {info.error && (
                                                        <div className="text-red-500 truncate" title={info.error}>
                                                            {info.error}
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>

                                        {/* Logs status */}
                                        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
                                            <span>Logs: {build.logs_available ? "✓ Available" : build.logs_expired ? "⚠ Expired" : "Pending"}</span>
                                        </div>
                                    </div>

                                    {/* Error Message */}
                                    {build.ingestion_error && (
                                        <div className="p-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded text-sm text-red-700 dark:text-red-300">
                                            <span className="font-medium">Error:</span> {build.ingestion_error}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </CardContent>
        </Card>
    );
}

/** Resource Status Badges */
function ResourceStatusBadges({
    resourceStatus,
}: {
    resourceStatus: Record<string, { status: string; error?: string }>;
}) {
    const entries = Object.entries(resourceStatus || {});
    if (entries.length === 0) return <span className="text-muted-foreground">—</span>;

    const completed = entries.filter(([, v]) => v.status === "completed").length;
    const failed = entries.filter(([, v]) => v.status === "failed").length;

    return (
        <div className="flex items-center gap-1">
            {completed > 0 && (
                <Badge variant="secondary" className="text-green-600 text-xs">
                    {completed} ✓
                </Badge>
            )}
            {failed > 0 && (
                <Badge variant="secondary" className="text-red-600 text-xs">
                    {failed} ✗
                </Badge>
            )}
        </div>
    );
}
