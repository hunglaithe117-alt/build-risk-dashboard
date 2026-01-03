"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
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
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import {
    CheckCircle2,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Loader2,
    XCircle,
    AlertTriangle,
    Clock,
    RefreshCw,
    RotateCcw,
    Shield,
    Lock,
    Play,
    ExternalLink,
    GitCommit,
    Timer,
    FileText,
} from "lucide-react";
import {
    datasetVersionApi,
    type EnrichedBuildData,
    type ImportBuildItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
    SearchFilterBar,
    DATASET_INGESTION_STATUS_OPTIONS,
    PROCESSING_STATUS_OPTIONS,
    SCAN_STATUS_OPTIONS,
} from "@/components/builds";

interface BuildsSubTabsProps {
    datasetId: string;
    versionId: string;
    versionStatus: string;
    onStartProcessing?: () => void;
    startProcessingLoading?: boolean;
}

const ITEMS_PER_PAGE = 20;

// Statuses that allow viewing processing/scans tabs
const PROCESSING_STATUSES = ["processing", "processed", "failed"];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

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

/** Status config for import builds
 * IMPORTANT: 
 * - FAILED (red) = Retryable errors (timeout, network issues)
 * - MISSING_RESOURCE (amber) = Non-retryable (logs expired, commit not found)
 */
const getImportStatusConfig = (status: string) => {
    const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string; retryable?: boolean }> = {
        pending: { icon: Clock, color: "text-gray-500", label: "Pending" },
        fetched: { icon: CheckCircle2, color: "text-blue-500", label: "Fetched" },
        ingesting: { icon: Loader2, color: "text-blue-500", label: "Ingesting" },
        ingested: { icon: CheckCircle2, color: "text-green-500", label: "Ingested" },
        missing_resource: { icon: AlertTriangle, color: "text-amber-500", label: "Missing Resource", retryable: false },
        failed: { icon: XCircle, color: "text-red-500", label: "Failed", retryable: true },
    };
    return config[status] || { icon: Clock, color: "text-gray-400", label: status };
};

/** Status config for enrichment builds */
const getEnrichmentStatusConfig = (status: string) => {
    const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
        pending: { icon: Clock, color: "text-gray-500", label: "Pending" },
        in_progress: { icon: Loader2, color: "text-blue-500", label: "Processing" },
        completed: { icon: CheckCircle2, color: "text-green-500", label: "Complete" },
        partial: { icon: AlertTriangle, color: "text-amber-500", label: "Partial" },
        failed: { icon: XCircle, color: "text-red-500", label: "Failed" },
    };
    return config[status] || { icon: Clock, color: "text-gray-400", label: status };
};

export function BuildsSubTabs({
    datasetId,
    versionId,
    versionStatus,
    onStartProcessing,
    startProcessingLoading = false,
}: BuildsSubTabsProps) {
    const router = useRouter();
    const searchParams = useSearchParams();

    // Check if processing can be started
    const canStartProcessing = versionStatus.toLowerCase() === "ingested" && !!onStartProcessing;

    // Determine which tabs are accessible based on version status
    const canViewProcessing = PROCESSING_STATUSES.includes(versionStatus.toLowerCase());
    const canViewScans = PROCESSING_STATUSES.includes(versionStatus.toLowerCase());


    // Sub-tab state from URL
    const subTab = searchParams.get("subtab") || "ingestion";
    const isIngestionActive = subTab === "ingestion";
    const isProcessingActive = subTab === "processing" && canViewProcessing;
    const isScansActive = subTab === "scans" && canViewScans;

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);

    // Search and filter state for ingestion
    const [ingestionSearch, setIngestionSearch] = useState("");
    const [ingestionStatusFilter, setIngestionStatusFilter] = useState("all");

    // Search and filter state for processing
    const [processingSearch, setProcessingSearch] = useState("");
    const [processingStatusFilter, setProcessingStatusFilter] = useState("all");

    // Data state for ingestion builds
    const [importBuilds, setImportBuilds] = useState<ImportBuildItem[]>([]);
    const [importTotal, setImportTotal] = useState(0);
    const [importLoading, setImportLoading] = useState(false);

    // Data state for enrichment builds
    const [enrichmentBuilds, setEnrichmentBuilds] = useState<EnrichedBuildData[]>([]);
    const [enrichmentTotal, setEnrichmentTotal] = useState(0);
    const [enrichmentLoading, setEnrichmentLoading] = useState(false);

    // Handle sub-tab change
    const handleSubTabChange = useCallback((tab: string) => {
        // Prevent changing to disabled tabs
        if (tab === "processing" && !canViewProcessing) return;
        if (tab === "scans" && !canViewScans) return;

        const newParams = new URLSearchParams(searchParams.toString());
        newParams.set("subtab", tab);
        router.push(`?${newParams.toString()}`, { scroll: false });
        setCurrentPage(1);
        // Reset search/filter when changing tabs
        setIngestionSearch("");
        setIngestionStatusFilter("all");
        setProcessingSearch("");
        setProcessingStatusFilter("all");
    }, [router, searchParams, canViewProcessing, canViewScans]);

    // Search/filter handlers for ingestion
    const handleIngestionSearch = useCallback((query: string) => {
        setIngestionSearch(query);
        setCurrentPage(1);
    }, []);

    const handleIngestionStatusFilter = useCallback((status: string) => {
        setIngestionStatusFilter(status);
        setCurrentPage(1);
    }, []);

    // Search/filter handlers for processing
    const handleProcessingSearch = useCallback((query: string) => {
        setProcessingSearch(query);
        setCurrentPage(1);
    }, []);

    const handleProcessingStatusFilter = useCallback((status: string) => {
        setProcessingStatusFilter(status);
        setCurrentPage(1);
    }, []);

    // Fetch import builds
    useEffect(() => {
        if (!isIngestionActive) return;

        const fetchImportBuilds = async () => {
            setImportLoading(true);
            try {
                const skip = (currentPage - 1) * ITEMS_PER_PAGE;
                const response = await datasetVersionApi.getImportBuilds(
                    datasetId,
                    versionId,
                    skip,
                    ITEMS_PER_PAGE,
                    ingestionStatusFilter !== "all" ? ingestionStatusFilter : undefined
                );
                // Client-side search filter (API doesn't support search param for this endpoint yet)
                let filteredItems = response.items;
                if (ingestionSearch) {
                    const searchLower = ingestionSearch.toLowerCase();
                    filteredItems = response.items.filter(item =>
                        item.commit_sha.toLowerCase().includes(searchLower) ||
                        item.build_id.toLowerCase().includes(searchLower) ||
                        (item.branch && item.branch.toLowerCase().includes(searchLower))
                    );
                }
                setImportBuilds(filteredItems);
                setImportTotal(ingestionSearch ? filteredItems.length : response.total);
            } catch (err) {
                console.error("Failed to fetch import builds:", err);
            } finally {
                setImportLoading(false);
            }
        };

        fetchImportBuilds();
    }, [datasetId, versionId, currentPage, isIngestionActive, ingestionSearch, ingestionStatusFilter]);

    // Fetch enrichment builds
    useEffect(() => {
        if (!isProcessingActive) return;

        const fetchEnrichmentBuilds = async () => {
            setEnrichmentLoading(true);
            try {
                const skip = (currentPage - 1) * ITEMS_PER_PAGE;
                const response = await datasetVersionApi.getEnrichmentBuilds(
                    datasetId,
                    versionId,
                    skip,
                    ITEMS_PER_PAGE,
                    processingStatusFilter !== "all" ? processingStatusFilter : undefined
                );
                // Client-side search filter
                let filteredItems = response.items;
                if (processingSearch) {
                    const searchLower = processingSearch.toLowerCase();
                    filteredItems = response.items.filter(item =>
                        item.raw_build_run_id.toLowerCase().includes(searchLower) ||
                        item.repo_full_name.toLowerCase().includes(searchLower)
                    );
                }
                setEnrichmentBuilds(filteredItems);
                setEnrichmentTotal(processingSearch ? filteredItems.length : response.total);
            } catch (err) {
                console.error("Failed to fetch enrichment builds:", err);
            } finally {
                setEnrichmentLoading(false);
            }
        };

        fetchEnrichmentBuilds();
    }, [datasetId, versionId, currentPage, isProcessingActive, processingSearch, processingStatusFilter]);

    // Calculate pagination
    const totalItems = isIngestionActive ? importTotal : isProcessingActive ? enrichmentTotal : 0;
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    const isLoading = isIngestionActive ? importLoading : enrichmentLoading;

    // Render tab button with lock icon for disabled tabs
    const TabButton = ({ tab, label, disabled }: { tab: string; label: string; disabled?: boolean }) => {
        const isActive = subTab === tab;
        return (
            <button
                onClick={() => handleSubTabChange(tab)}
                disabled={disabled}
                className={cn(
                    "px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1",
                    isActive && !disabled
                        ? "bg-background text-foreground shadow-sm"
                        : disabled
                            ? "text-muted-foreground/50 cursor-not-allowed"
                            : "text-muted-foreground hover:text-foreground"
                )}
            >
                {disabled && <Lock className="h-3 w-3" />}
                {label}
            </button>
        );
    };

    return (
        <div className="space-y-4">
            {/* Sub-tabs Navigation */}
            <div className="flex items-center justify-between">
                <div className="flex gap-1 rounded-lg bg-muted p-1">
                    <TabButton tab="ingestion" label="Data Collection" />
                    <TabButton tab="processing" label="Feature Extraction" disabled={!canViewProcessing} />
                    <TabButton tab="scans" label="Integration Scans" disabled={!canViewScans} />
                </div>
            </div>

            {/* Content */}
            {isLoading ? (
                <div className="flex min-h-[200px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : isIngestionActive ? (
                <>
                    {/* Search and Filter for Ingestion */}
                    <div className="mb-4">
                        <SearchFilterBar
                            placeholder="Search by commit SHA, build ID, or branch..."
                            statusOptions={DATASET_INGESTION_STATUS_OPTIONS}
                            onSearch={handleIngestionSearch}
                            onStatusFilter={handleIngestionStatusFilter}
                            isLoading={importLoading}
                        />
                    </div>
                    <ImportBuildsTable
                        builds={importBuilds}
                        total={importTotal}
                        datasetId={datasetId}
                        versionId={versionId}
                        canStartProcessing={canStartProcessing}
                        onStartProcessing={onStartProcessing}
                        startProcessingLoading={startProcessingLoading}
                    />
                </>
            ) : isProcessingActive ? (
                <>
                    {/* Search and Filter for Processing */}
                    <div className="mb-4">
                        <SearchFilterBar
                            placeholder="Search by build ID or repository..."
                            statusOptions={PROCESSING_STATUS_OPTIONS}
                            onSearch={handleProcessingSearch}
                            onStatusFilter={handleProcessingStatusFilter}
                            isLoading={enrichmentLoading}
                        />
                    </div>
                    <EnrichmentBuildsTable
                        builds={enrichmentBuilds}
                        total={enrichmentTotal}
                        datasetId={datasetId}
                        versionId={versionId}
                    />
                </>
            ) : isScansActive ? (
                <IntegrationScansSection datasetId={datasetId} versionId={versionId} />
            ) : (
                <Card>
                    <CardContent className="py-8 text-center text-muted-foreground">
                        <Lock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                        <p>This tab requires processing to be started.</p>
                    </CardContent>
                </Card>
            )}

            {/* Pagination (only for ingestion/processing tabs) */}
            {(isIngestionActive || isProcessingActive) && totalPages > 1 && (
                <div className="flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                        Page {currentPage} of {totalPages}
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
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                        >
                            Next
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}

/** Import Builds Table (Ingestion Phase) */
function ImportBuildsTable({
    builds,
    total,
    canStartProcessing = false,
    onStartProcessing,
    startProcessingLoading = false,
}: {
    builds: ImportBuildItem[];
    total: number;
    datasetId: string;
    versionId: string;
    canStartProcessing?: boolean;
    onStartProcessing?: () => void;
    startProcessingLoading?: boolean;
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

/** Enrichment Builds Table (Processing Phase) */
function EnrichmentBuildsTable({
    builds,
    total,
    datasetId,
    versionId,
}: {
    builds: EnrichedBuildData[];
    total: number;
    datasetId: string;
    versionId: string;
}) {
    const router = useRouter();

    if (builds.length === 0) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    No enrichment builds found. Processing may not have started yet.
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-base">Enrichment Builds</CardTitle>
                <CardDescription>
                    {total} builds with feature extraction
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-[100px]">Build ID</TableHead>
                                <TableHead className="w-[180px]">Repository</TableHead>
                                <TableHead className="w-[100px]">Status</TableHead>
                                <TableHead className="w-[100px]">Features</TableHead>
                                <TableHead className="w-[80px]">Skipped</TableHead>
                                <TableHead className="w-[100px]">Enriched At</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {builds.map((build) => {
                                const statusConfig = getEnrichmentStatusConfig(build.extraction_status);
                                const StatusIcon = statusConfig.icon;

                                return (
                                    <TableRow
                                        key={build.id}
                                        className="cursor-pointer hover:bg-muted/50"
                                        onClick={() => router.push(`/projects/${datasetId}/versions/${versionId}/builds/${build.id}`)}
                                    >
                                        <TableCell className="font-mono text-sm">
                                            #{build.raw_build_run_id.slice(-8)}
                                        </TableCell>
                                        <TableCell className="max-w-[180px] truncate">
                                            {build.repo_full_name}
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={statusConfig.color}>
                                                <StatusIcon className={cn("mr-1 h-3 w-3", build.extraction_status === "in_progress" && "animate-spin")} />
                                                {statusConfig.label}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-sm">
                                                {build.feature_count}/{build.expected_feature_count}
                                            </span>
                                        </TableCell>
                                        <TableCell className="text-muted-foreground text-sm">
                                            {formatRelativeTime(build.enriched_at)}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}

// =============================================================================
// Integration Scans Section (Third sub-tab)
// =============================================================================

interface CommitScan {
    id: string;
    commit_sha: string;
    repo_full_name: string;
    status: string;
    error_message: string | null;
    builds_affected: number;
    retry_count: number;
    started_at: string | null;
    completed_at: string | null;
}

interface CommitScansResponse {
    trivy: CommitScan[];
    sonarqube: CommitScan[];
}

function formatDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt || !completedAt) return "-";
    const diff = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (diff < 1000) return `${diff}ms`;
    return `${(diff / 1000).toFixed(1)}s`;
}

const SCANS_PER_PAGE = 10;

function IntegrationScansSection({ datasetId, versionId }: { datasetId: string; versionId: string }) {
    const [scans, setScans] = useState<CommitScansResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [retrying, setRetrying] = useState<string | null>(null);
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

    // Search and filter state
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");

    // Pagination state for each tab
    const [sonarPage, setSonarPage] = useState(1);
    const [trivyPage, setTrivyPage] = useState(1);

    // Active tab for Retry Failed button
    const [activeTab, setActiveTab] = useState<"sonarqube" | "trivy">("sonarqube");

    const fetchScans = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const res = await fetch(
                `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans`,
                { credentials: "include" }
            );
            if (res.ok) {
                const data = await res.json();
                setScans(data);

                // Continue polling if any scans are running
                const hasRunning = [...(data.trivy || []), ...(data.sonarqube || [])]
                    .some((s: CommitScan) => s.status === "scanning" || s.status === "pending");
                if (hasRunning && !pollingRef.current) {
                    pollingRef.current = setInterval(() => fetchScans(true), 5000);
                } else if (!hasRunning && pollingRef.current) {
                    clearInterval(pollingRef.current);
                    pollingRef.current = null;
                }
            }
        } catch (err) {
            console.error("Failed to fetch scans:", err);
        } finally {
            if (!silent) setLoading(false);
        }
    }, [datasetId, versionId]);

    useEffect(() => {
        if (versionId) fetchScans();
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
    }, [versionId, fetchScans]);

    const handleRetry = async (commitSha: string, toolType: string) => {
        setRetrying(`${toolType}-${commitSha}`);
        try {
            await fetch(
                `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans/${commitSha}/retry?tool_type=${toolType}`,
                { method: "POST", credentials: "include" }
            );
            await fetchScans();
        } catch (err) {
            console.error("Retry failed:", err);
        } finally {
            setRetrying(null);
        }
    };

    const handleRetryAllFailed = async (toolType: string) => {
        const scanList = toolType === "sonarqube" ? scans?.sonarqube : scans?.trivy;
        const failedScans = scanList?.filter(s => s.status === "failed") || [];
        for (const scan of failedScans) {
            await handleRetry(scan.commit_sha, toolType);
        }
    };

    // Filter scans based on search and status
    const filterScans = useCallback((scanList: CommitScan[]) => {
        return scanList.filter(scan => {
            const matchesSearch = searchQuery === "" ||
                scan.commit_sha.toLowerCase().includes(searchQuery.toLowerCase()) ||
                scan.repo_full_name.toLowerCase().includes(searchQuery.toLowerCase());
            const matchesStatus = statusFilter === "all" || scan.status === statusFilter;
            return matchesSearch && matchesStatus;
        });
    }, [searchQuery, statusFilter]);

    // Reset pagination when filter changes
    useEffect(() => {
        setSonarPage(1);
        setTrivyPage(1);
    }, [searchQuery, statusFilter]);

    const renderStatus = (status: string) => {
        const config: Record<string, { icon: React.ReactNode; className: string }> = {
            completed: { icon: <CheckCircle2 className="h-3 w-3" />, className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" },
            failed: { icon: <XCircle className="h-3 w-3" />, className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" },
            scanning: { icon: <Loader2 className="h-3 w-3 animate-spin" />, className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400" },
            pending: { icon: <Clock className="h-3 w-3" />, className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400" },
        };
        const c = config[status] || config.pending;
        return (
            <Badge variant="outline" className={c.className}>
                <span className="flex items-center gap-1">{c.icon} {status}</span>
            </Badge>
        );
    };

    const renderScanTable = (scanList: CommitScan[], toolType: string, currentPage: number, setPage: (p: number) => void) => {
        const filteredList = filterScans(scanList);

        if (!filteredList || filteredList.length === 0) {
            return <p className="text-sm text-muted-foreground py-4">No scans match your criteria</p>;
        }

        const stats = {
            total: filteredList.length,
            completed: filteredList.filter(s => s.status === "completed").length,
            failed: filteredList.filter(s => s.status === "failed").length,
            pending: filteredList.filter(s => s.status === "pending" || s.status === "scanning").length,
        };

        const totalPages = Math.ceil(filteredList.length / SCANS_PER_PAGE);
        const startIdx = (currentPage - 1) * SCANS_PER_PAGE;
        const paginatedList = filteredList.slice(startIdx, startIdx + SCANS_PER_PAGE);

        return (
            <div className="space-y-3">
                <div className="flex gap-2 text-xs text-muted-foreground">
                    <span>{stats.total} total</span>
                    <span>•</span>
                    <span className="text-green-600">{stats.completed} completed (page)</span>
                    {stats.failed > 0 && <><span>•</span><span className="text-red-600">{stats.failed} failed</span></>}
                    {stats.pending > 0 && <><span>•</span><span>{stats.pending} pending</span></>}
                </div>
                <div className="border rounded-lg overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Commit</TableHead>
                                <TableHead>Repo</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Builds</TableHead>
                                <TableHead>Duration</TableHead>
                                <TableHead className="w-16"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {paginatedList.map((scan) => (
                                <TableRow key={scan.id}>
                                    <TableCell className="font-mono text-xs">
                                        {scan.commit_sha.substring(0, 7)}
                                    </TableCell>
                                    <TableCell className="text-sm truncate max-w-[150px]" title={scan.repo_full_name}>
                                        {scan.repo_full_name.split('/').pop() || scan.repo_full_name}
                                    </TableCell>
                                    <TableCell>{renderStatus(scan.status)}</TableCell>
                                    <TableCell>{scan.builds_affected}</TableCell>
                                    <TableCell className="text-xs">
                                        {formatDuration(scan.started_at, scan.completed_at)}
                                    </TableCell>
                                    <TableCell>
                                        {scan.status === "failed" && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                disabled={retrying === `${toolType}-${scan.commit_sha}`}
                                                onClick={() => handleRetry(scan.commit_sha, toolType)}
                                            >
                                                {retrying === `${toolType}-${scan.commit_sha}` ? (
                                                    <Loader2 className="h-3 w-3 animate-spin" />
                                                ) : (
                                                    <RotateCcw className="h-3 w-3" />
                                                )}
                                            </Button>
                                        )}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">
                            Showing {startIdx + 1}-{Math.min(startIdx + SCANS_PER_PAGE, filteredList.length)} of {filteredList.length} scans
                        </span>
                        <div className="flex items-center gap-1">
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2"
                                onClick={() => setPage(Math.max(1, currentPage - 1))}
                                disabled={currentPage === 1}
                            >
                                <ChevronLeft className="h-3 w-3" />
                            </Button>
                            <span className="px-2">Page {currentPage} of {totalPages}</span>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2"
                                onClick={() => setPage(Math.min(totalPages, currentPage + 1))}
                                disabled={currentPage === totalPages}
                            >
                                <ChevronRight className="h-3 w-3" />
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin mr-2" />
                <span className="text-muted-foreground">Loading scans...</span>
            </div>
        );
    }

    if (!scans || (scans.sonarqube.length === 0 && scans.trivy.length === 0)) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    No integration scans for this version
                </CardContent>
            </Card>
        );
    }

    const failedCount = [
        ...(scans.sonarqube || []),
        ...(scans.trivy || [])
    ].filter(s => s.status === "failed").length;

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Integration Scans</CardTitle>
                        <CardDescription>
                            SonarQube and Trivy security scans
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        {failedCount > 0 && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleRetryAllFailed(activeTab)}
                                className="text-red-600 border-red-200 hover:bg-red-50"
                            >
                                <RotateCcw className="h-4 w-4 mr-1" />
                                Retry Failed ({failedCount})
                            </Button>
                        )}
                        <Button variant="outline" size="sm" onClick={() => fetchScans()}>
                            <RefreshCw className="h-4 w-4 mr-1" />
                            Refresh
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Search and Filter */}
                <SearchFilterBar
                    placeholder="Search by commit SHA or repository..."
                    statusOptions={SCAN_STATUS_OPTIONS}
                    onSearch={setSearchQuery}
                    onStatusFilter={setStatusFilter}
                    isLoading={loading}
                />

                {/* Tab Navigation for SonarQube/Trivy */}
                <div className="flex gap-1 rounded-lg bg-muted p-1 w-fit">
                    {scans.sonarqube.length > 0 && (
                        <button
                            onClick={() => setActiveTab("sonarqube")}
                            className={cn(
                                "px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5",
                                activeTab === "sonarqube"
                                    ? "bg-background text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Shield className="h-4 w-4 text-blue-600" />
                            SonarQube ({filterScans(scans.sonarqube).length})
                        </button>
                    )}
                    {scans.trivy.length > 0 && (
                        <button
                            onClick={() => setActiveTab("trivy")}
                            className={cn(
                                "px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5",
                                activeTab === "trivy"
                                    ? "bg-background text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <AlertTriangle className="h-4 w-4 text-amber-600" />
                            Trivy ({filterScans(scans.trivy).length})
                        </button>
                    )}
                </div>

                {/* Scan Tables */}
                {activeTab === "sonarqube" && scans.sonarqube.length > 0 && (
                    renderScanTable(scans.sonarqube, "sonarqube", sonarPage, setSonarPage)
                )}
                {activeTab === "trivy" && scans.trivy.length > 0 && (
                    renderScanTable(scans.trivy, "trivy", trivyPage, setTrivyPage)
                )}
            </CardContent>
        </Card>
    );
}
