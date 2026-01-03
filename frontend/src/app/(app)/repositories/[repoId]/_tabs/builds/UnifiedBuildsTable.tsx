"use client";

import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock,
    GitCommit,
    Loader2,
    RotateCcw,
    XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    SearchFilterBar,
    ResourceStatusIndicator,
    TablePagination,
} from "@/components/builds";
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi } from "@/lib/api";
import { formatTimestamp, cn } from "@/lib/utils";
import type { UnifiedBuild } from "@/types";

const PAGE_SIZE = 20;

// Phase status options for filter dropdown
const UNIFIED_STATUS_OPTIONS = [
    { value: "all", label: "All Phases" },
    { value: "ingestion", label: "Ingestion" },
    { value: "processing", label: "Processing" },
    { value: "prediction", label: "Prediction" },
];

// Status icon component for phase columns
function PhaseStatusIcon({ status }: { status: string | undefined }) {
    if (!status) {
        return <Clock className="h-4 w-4 text-slate-400" />;
    }

    const statusLower = status.toLowerCase();
    if (statusLower === "completed" || statusLower === "ingested") {
        return <CheckCircle2 className="h-4 w-4 text-green-600" />;
    }
    if (statusLower === "partial") {
        return <AlertCircle className="h-4 w-4 text-amber-500" />;
    }
    if (statusLower === "failed" || statusLower === "missing_resource") {
        return <XCircle className="h-4 w-4 text-red-500" />;
    }
    if (statusLower === "in_progress" || statusLower === "ingesting" || statusLower === "processing") {
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    }
    return <Clock className="h-4 w-4 text-slate-400" />;
}

// Risk badge for prediction column - includes uncertainty
function RiskBadge({ level, confidence, uncertainty }: { level?: string; confidence?: number; uncertainty?: number }) {
    if (!level) return <span className="text-muted-foreground">—</span>;

    const riskLevel = level.toUpperCase();
    const confLabel = confidence ? ` ${(confidence * 100).toFixed(0)}%` : "";
    const uncertaintyLabel = uncertainty !== undefined ? `±${(uncertainty * 100).toFixed(0)}%` : "";

    if (riskLevel === "LOW") {
        return (
            <div className="flex flex-col gap-0.5">
                <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    Low{confLabel}
                </Badge>
                {uncertaintyLabel && (
                    <span className="text-[10px] text-muted-foreground">{uncertaintyLabel}</span>
                )}
            </div>
        );
    }
    if (riskLevel === "MEDIUM") {
        return (
            <div className="flex flex-col gap-0.5">
                <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                    <AlertCircle className="h-3 w-3" />
                    Med{confLabel}
                </Badge>
                {uncertaintyLabel && (
                    <span className="text-[10px] text-muted-foreground">{uncertaintyLabel}</span>
                )}
            </div>
        );
    }
    if (riskLevel === "HIGH") {
        return (
            <div className="flex flex-col gap-0.5">
                <Badge variant="destructive" className="gap-1">
                    <XCircle className="h-3 w-3" />
                    High{confLabel}
                </Badge>
                {uncertaintyLabel && (
                    <span className="text-[10px] text-muted-foreground">{uncertaintyLabel}</span>
                )}
            </div>
        );
    }
    return <Badge variant="secondary">{level}</Badge>;
}

interface UnifiedBuildsTableProps {
    repoId: string;
    onRetryIngestion?: () => void;
    onRetryProcessing?: () => void;
    retryIngestionLoading?: boolean;
    retryProcessingLoading?: boolean;
}

export function UnifiedBuildsTable({
    repoId,
    onRetryIngestion,
    onRetryProcessing,
    retryIngestionLoading,
    retryProcessingLoading,
}: UnifiedBuildsTableProps) {
    const router = useRouter();
    const [builds, setBuilds] = useState<UnifiedBuild[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

    // Search and filter state
    const [searchQuery, setSearchQuery] = useState("");
    const [phaseFilter, setPhaseFilter] = useState("all");

    const { subscribe } = useWebSocket();

    const loadBuilds = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) setTableLoading(true);
            try {
                const response = await buildApi.getUnifiedBuilds(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: searchQuery || undefined,
                    phase: phaseFilter !== "all" ? phaseFilter : undefined,
                });
                setBuilds(response.items);
                setTotal(response.total);
                setPage(pageNumber);
            } catch (err) {
                console.error("Failed to load unified builds:", err);
            } finally {
                setLoading(false);
                setTableLoading(false);
            }
        },
        [repoId, searchQuery, phaseFilter]
    );

    useEffect(() => {
        loadBuilds(1, true);
    }, [loadBuilds]);

    // Search handler
    const handleSearch = useCallback((query: string) => {
        setSearchQuery(query);
        setPage(1);
    }, []);

    // Phase filter handler
    const handlePhaseFilter = useCallback((phase: string) => {
        setPhaseFilter(phase);
        setPage(1);
    }, []);

    // WebSocket subscription for real-time updates
    useEffect(() => {
        const unsubscribeBuild = subscribe("BUILD_UPDATE", (payload: { repo_id: string }) => {
            if (payload.repo_id === repoId) {
                loadBuilds(page);
            }
        });

        const unsubscribeRepo = subscribe("REPO_UPDATE", (payload: { repo_id: string }) => {
            if (payload.repo_id === repoId) {
                loadBuilds(page);
            }
        });

        return () => {
            unsubscribeBuild();
            unsubscribeRepo();
        };
    }, [subscribe, loadBuilds, page, repoId]);

    const toggleRow = (buildId: string) => {
        setExpandedRows((prev) => {
            const next = new Set(prev);
            if (next.has(buildId)) {
                next.delete(buildId);
            } else {
                next.add(buildId);
            }
            return next;
        });
    };

    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;

    // Count failed builds for retry buttons
    const ingestionFailedCount = builds.filter(
        (b) => b.ingestion_status === "failed" || b.ingestion_status === "missing_resource"
    ).length;
    const processingFailedCount = builds.filter(
        (b) => b.extraction_status === "failed" || b.prediction_status === "failed"
    ).length;

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <Card>
            <CardHeader className="space-y-4">
                <div className="flex flex-row items-center justify-between">
                    <div>
                        <CardTitle>Pipeline Builds</CardTitle>
                        <CardDescription>
                            All builds with ingestion, extraction, and prediction status
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        {onRetryIngestion && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onRetryIngestion}
                                disabled={retryIngestionLoading || ingestionFailedCount === 0}
                                className={cn(
                                    "text-amber-600 border-amber-300 hover:bg-amber-50",
                                    ingestionFailedCount === 0 && "opacity-50"
                                )}
                            >
                                {retryIngestionLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry Ingestion
                            </Button>
                        )}
                        {onRetryProcessing && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onRetryProcessing}
                                disabled={retryProcessingLoading || processingFailedCount === 0}
                                className={cn(
                                    "text-amber-600 border-amber-300 hover:bg-amber-50",
                                    processingFailedCount === 0 && "opacity-50"
                                )}
                            >
                                {retryProcessingLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry Processing
                            </Button>
                        )}
                    </div>
                </div>
                <SearchFilterBar
                    placeholder="Search by commit SHA or build number..."
                    statusOptions={UNIFIED_STATUS_OPTIONS}
                    onSearch={handleSearch}
                    onStatusFilter={handlePhaseFilter}
                    isLoading={tableLoading}
                />
            </CardHeader>
            <CardContent className="p-0">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                        <thead className="bg-slate-50 dark:bg-slate-900/40">
                            <tr>
                                <th className="px-4 py-3 w-[50px]" />
                                <th className="px-4 py-3 text-left font-medium text-slate-500">#</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">Commit</th>
                                <th className="px-4 py-3 text-center font-medium text-slate-500">Pipeline</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">Risk</th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">Time</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                            {builds.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                                        No builds found.
                                    </td>
                                </tr>
                            ) : (
                                builds.map((build) => {
                                    const isExpanded = expandedRows.has(build.model_import_build_id);
                                    const hasResources = Object.keys(build.resource_status || {}).length > 0;

                                    return (
                                        <Collapsible
                                            key={build.model_import_build_id}
                                            open={isExpanded}
                                            onOpenChange={() => toggleRow(build.model_import_build_id)}
                                            asChild
                                        >
                                            <>
                                                <tr
                                                    className="hover:bg-slate-50 dark:hover:bg-slate-900/40 transition cursor-pointer"
                                                    onClick={(e) => {
                                                        // Navigate to build detail if training_build_id exists
                                                        if (build.training_build_id) {
                                                            router.push(
                                                                `/repositories/${repoId}/build/${build.training_build_id}`
                                                            );
                                                        }
                                                    }}
                                                >
                                                    <td
                                                        className="px-4 py-3"
                                                        onClick={(e) => e.stopPropagation()}
                                                    >
                                                        {hasResources && (
                                                            <CollapsibleTrigger asChild>
                                                                <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                                                                    {isExpanded ? (
                                                                        <ChevronDown className="h-4 w-4" />
                                                                    ) : (
                                                                        <ChevronRight className="h-4 w-4" />
                                                                    )}
                                                                </Button>
                                                            </CollapsibleTrigger>
                                                        )}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex flex-col gap-0.5">
                                                            <span className="font-medium">
                                                                #{build.build_number || "—"}
                                                            </span>
                                                            {build.branch && (
                                                                <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 font-normal w-fit">
                                                                    {build.branch}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex items-center gap-1 font-mono text-xs">
                                                            <GitCommit className="h-3 w-3" />
                                                            <span title={build.commit_message}>
                                                                {build.commit_sha?.substring(0, 7)}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex items-center justify-center gap-2" title="Ingestion → Extraction → Prediction">
                                                            <div className="flex items-center gap-0.5" title={`Ingestion: ${build.ingestion_status}`}>
                                                                <PhaseStatusIcon status={build.ingestion_status} />
                                                            </div>
                                                            <span className="text-slate-300">→</span>
                                                            <div className="flex items-center gap-0.5" title={`Extraction: ${build.extraction_status || 'pending'}`}>
                                                                <PhaseStatusIcon status={build.extraction_status} />
                                                                {build.feature_count > 0 && (
                                                                    <span className="text-[10px] text-muted-foreground">
                                                                        {build.feature_count}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <span className="text-slate-300">→</span>
                                                            <div title={`Prediction: ${build.prediction_status || 'pending'}`}>
                                                                <PhaseStatusIcon status={build.prediction_status} />
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <RiskBadge
                                                            level={build.predicted_label}
                                                            confidence={build.prediction_confidence}
                                                            uncertainty={build.prediction_uncertainty}
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                                                        {formatTimestamp(build.created_at)}
                                                    </td>
                                                </tr>
                                                {hasResources && (
                                                    <CollapsibleContent asChild>
                                                        <tr className="bg-slate-50 dark:bg-slate-900/20 shadow-inner">
                                                            <td colSpan={6} className="px-4 py-4">
                                                                <div className="space-y-3">
                                                                    <h4 className="font-medium text-sm text-slate-900 dark:text-slate-100">
                                                                        Resource Status
                                                                    </h4>
                                                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                                                        {Object.entries(build.resource_status || {}).map(
                                                                            ([resourceName, resourceData]) => (
                                                                                <ResourceStatusIndicator
                                                                                    key={resourceName}
                                                                                    resourceName={resourceName}
                                                                                    status={resourceData.status}
                                                                                    error={resourceData.error}
                                                                                />
                                                                            )
                                                                        )}
                                                                    </div>
                                                                    {build.extraction_error && (
                                                                        <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                                                                            <p className="font-medium text-red-600 text-sm">
                                                                                Extraction Error:
                                                                            </p>
                                                                            <p className="text-red-700 text-xs mt-1">
                                                                                {build.extraction_error}
                                                                            </p>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    </CollapsibleContent>
                                                )}
                                            </>
                                        </Collapsible>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
                <TablePagination
                    currentPage={page}
                    totalPages={totalPages}
                    totalItems={total}
                    pageSize={PAGE_SIZE}
                    onPageChange={(newPage) => loadBuilds(newPage, true)}
                    isLoading={tableLoading}
                />
            </CardContent>
        </Card>
    );
}
