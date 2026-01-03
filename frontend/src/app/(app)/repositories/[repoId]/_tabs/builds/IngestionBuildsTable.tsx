"use client";

import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    ExternalLink,
    GitCommit,
    Loader2,
    RotateCcw,
    XCircle,
} from "lucide-react";
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
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    SearchFilterBar,
    INGESTION_STATUS_OPTIONS,
    IngestionStatusBadge,
    ResourceStatusIndicator,
    TablePagination,
} from "@/components/builds";
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi } from "@/lib/api";
import { formatTimestamp, cn } from "@/lib/utils";
import type { ImportBuild } from "@/types";

const PAGE_SIZE = 20;

// Status badges and resource indicators moved to @/components/builds

interface IngestionBuildsTableProps {
    repoId: string;
    onRetryAllFailed?: () => void;
    retryAllLoading?: boolean;
}

export function IngestionBuildsTable({
    repoId,
    onRetryAllFailed,
    retryAllLoading,
}: IngestionBuildsTableProps) {
    const [builds, setBuilds] = useState<ImportBuild[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

    // Search and filter state
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");

    const { subscribe } = useWebSocket();

    const loadBuilds = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) setTableLoading(true);
            try {
                const data = await buildApi.getImportBuilds(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: searchQuery || undefined,
                    status: statusFilter !== "all" ? statusFilter : undefined,
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
        [repoId, searchQuery, statusFilter]
    );

    useEffect(() => {
        loadBuilds(1, true);
    }, [loadBuilds]);

    // Search handler - reset to page 1
    const handleSearch = useCallback((query: string) => {
        setSearchQuery(query);
        setPage(1);
    }, []);

    // Status filter handler - reset to page 1
    const handleStatusFilter = useCallback((status: string) => {
        setStatusFilter(status);
        setPage(1);
    }, []);

    useEffect(() => {
        const unsubscribeBuild = subscribe("BUILD_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                loadBuilds(page);
            }
        });

        // Subscribe to REPO_UPDATE to reload when ingestion status changes
        const unsubscribeRepo = subscribe("REPO_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                // Reload builds when status changes (especially to ingested/processed/failed)
                // This ensures resource_status is refreshed from DB
                loadBuilds(page);
            }
        });

        const unsubscribeIngestion = subscribe("INGESTION_BUILD_UPDATE", (data: any) => {
            // Check if this update is for our repo (model pipeline)
            if (data.repo_id === repoId && data.pipeline_type === "model") {
                const {
                    resource,
                    // New separate lists for completed/failed
                    completed_commit_shas,
                    failed_commit_shas,
                    completed_build_ids,
                    failed_build_ids,
                    status,
                } = data;

                setBuilds((prevBuilds) =>
                    prevBuilds.map((build) => {
                        let newStatus: string | null = null;

                        if (resource === "git_history") {
                            // git_history: Update ALL builds with the overall status
                            newStatus = status;
                        } else if (resource === "git_worktree") {
                            // git_worktree: Check if this build's commit_sha is in completed or failed list
                            if (completed_commit_shas?.includes(build.commit_sha)) {
                                newStatus = "completed";
                            } else if (failed_commit_shas?.includes(build.commit_sha)) {
                                newStatus = "failed";
                            }
                        } else if (resource === "build_logs") {
                            // build_logs: Check if this build's build_id is in completed or failed list
                            if (completed_build_ids?.includes(build.build_id)) {
                                newStatus = "completed";
                            } else if (failed_build_ids?.includes(build.build_id)) {
                                newStatus = "failed";
                            }
                        }

                        if (newStatus) {
                            return {
                                ...build,
                                resource_status: {
                                    ...build.resource_status,
                                    [resource]: {
                                        ...build.resource_status?.[resource],
                                        status: newStatus,
                                    },
                                },
                            };
                        }
                        return build;
                    })
                );
            }
        });

        return () => {
            unsubscribeBuild();
            unsubscribeRepo();
            unsubscribeIngestion();
        };
    }, [subscribe, loadBuilds, page, repoId]);

    const toggleRow = (id: string) => {
        setExpandedRows((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const failedCount = builds.filter((b) => b.status === "missing_resource").length;
    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
    const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

    const handlePageChange = (direction: "prev" | "next") => {
        const target =
            direction === "prev"
                ? Math.max(1, page - 1)
                : Math.min(totalPages, page + 1);
        if (target !== page) loadBuilds(target, true);
    };

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
                        <CardTitle>Ingestion Builds</CardTitle>
                        <CardDescription>
                            Builds fetched from CI with resource ingestion status
                        </CardDescription>
                    </div>
                    {/* Retry Failed button - always visible, disabled when no failed builds */}
                    {onRetryAllFailed && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRetryAllFailed}
                            disabled={retryAllLoading || failedCount === 0}
                            className={cn(
                                "text-amber-600 border-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/30",
                                failedCount === 0 && "opacity-50 cursor-not-allowed"
                            )}
                        >
                            {retryAllLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <RotateCcw className="mr-2 h-4 w-4" />
                            )}
                            Retry Failed ({failedCount})
                        </Button>
                    )}
                </div>
                {/* Search and Filter Bar */}
                <SearchFilterBar
                    placeholder="Search by commit SHA or build ID..."
                    statusOptions={INGESTION_STATUS_OPTIONS}
                    onSearch={handleSearch}
                    onStatusFilter={handleStatusFilter}
                    isLoading={tableLoading}
                />
            </CardHeader>
            <CardContent className="p-0">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                        <thead className="bg-slate-50 dark:bg-slate-900/40">
                            <tr>
                                <th className="px-4 py-3" />
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    Build
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    Commit
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    Status
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    Created At
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                            {builds.length === 0 ? (
                                <tr>
                                    <td
                                        colSpan={6}
                                        className="px-4 py-8 text-center text-muted-foreground"
                                    >
                                        No ingestion builds found.
                                    </td>
                                </tr>
                            ) : (
                                builds.map((build) => {
                                    const isExpanded = expandedRows.has(build.id);
                                    const hasErrors = Object.values(
                                        build.resource_status || {}
                                    ).some((r) => r.error);

                                    return (
                                        <Collapsible
                                            key={build.id}
                                            open={isExpanded}
                                            onOpenChange={() => toggleRow(build.id)}
                                            asChild
                                        >
                                            <>
                                                <tr
                                                    className="hover:bg-slate-50 dark:hover:bg-slate-900/40 transition cursor-pointer"
                                                    onClick={(e) => {
                                                        if ((e.target as HTMLElement).closest("a, button")) return;
                                                        toggleRow(build.id);
                                                    }}
                                                >
                                                    <td className="px-4 py-3 w-[50px]">
                                                        <CollapsibleTrigger asChild>
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                className="h-6 w-6 p-0"
                                                            >
                                                                {isExpanded ? (
                                                                    <ChevronDown className="h-4 w-4" />
                                                                ) : (
                                                                    <ChevronRight className="h-4 w-4" />
                                                                )}
                                                            </Button>
                                                        </CollapsibleTrigger>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex flex-col gap-0.5">
                                                            <div className="flex items-center gap-2">
                                                                <span className="font-medium">
                                                                    #{build.build_number || "—"}
                                                                </span>
                                                                {build.branch && (
                                                                    <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 font-normal">
                                                                        {build.branch}
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex flex-col gap-1">
                                                            <div className="flex items-center gap-1 font-mono text-xs">
                                                                <GitCommit className="h-3 w-3" />
                                                                <span title={build.commit_message}>
                                                                    {build.commit_sha?.substring(0, 7)}
                                                                </span>
                                                            </div>
                                                            {build.commit_author && (
                                                                <span className="text-xs text-muted-foreground truncate max-w-[150px]" title={build.commit_author}>
                                                                    {build.commit_author}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <IngestionStatusBadge status={build.status} />
                                                    </td>
                                                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                                                        {formatTimestamp(build.created_at)}
                                                    </td>
                                                </tr>
                                                <CollapsibleContent asChild>
                                                    <tr className="bg-slate-50 dark:bg-slate-900/20 shadow-inner">
                                                        <td colSpan={5} className="px-4 py-4">
                                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                                                {/* Build Info Column */}
                                                                <div className="space-y-3">
                                                                    <h4 className="font-medium text-sm text-slate-900 dark:text-slate-100 flex items-center gap-2">
                                                                        Build Details
                                                                    </h4>
                                                                    <div className="space-y-2 text-sm bg-white dark:bg-slate-950 p-3 rounded-lg border">
                                                                        <div className="flex justify-between">
                                                                            <span className="text-muted-foreground">CI Status:</span>
                                                                            <span className={`flex items-center gap-1.5 capitalize font-medium ${build.conclusion === 'success' ? 'text-green-600' :
                                                                                build.conclusion === 'failure' ? 'text-red-600' :
                                                                                    'text-slate-600'
                                                                                }`}>
                                                                                {build.conclusion === "success" && <CheckCircle2 className="h-3.5 w-3.5" />}
                                                                                {build.conclusion === "failure" && <XCircle className="h-3.5 w-3.5" />}
                                                                                {build.conclusion || "Unknown"}
                                                                            </span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                            <span className="text-muted-foreground">Duration:</span>
                                                                            <span className="font-mono">
                                                                                {build.duration_seconds ? `${Math.round(build.duration_seconds)}s` : "—"}
                                                                            </span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                            <span className="text-muted-foreground">Link:</span>
                                                                            <a
                                                                                href={build.web_url || "#"}
                                                                                target="_blank"
                                                                                rel="noreferrer"
                                                                                className="flex items-center gap-1 text-blue-500 hover:underline"
                                                                            >
                                                                                Open in CI <ExternalLink className="h-3 w-3" />
                                                                            </a>
                                                                        </div>
                                                                        {build.commit_message && (
                                                                            <div className="pt-2 border-t mt-2">
                                                                                <p className="text-xs text-muted-foreground line-clamp-3 italic">
                                                                                    &quot;{build.commit_message}&quot;
                                                                                </p>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                {/* Resources Column */}
                                                                <div className="md:col-span-2 space-y-3">
                                                                    <h4 className="font-medium text-sm text-slate-900 dark:text-slate-100">
                                                                        Resources
                                                                    </h4>
                                                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                                                        {Object.entries(
                                                                            build.resource_status || {}
                                                                        ).map(([key, val]) => (
                                                                            <ResourceStatusIndicator
                                                                                key={key}
                                                                                resourceName={key}
                                                                                status={val.status}
                                                                                error={val.error}
                                                                            />
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                </CollapsibleContent>
                                            </>
                                        </Collapsible>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
                {/* Pagination */}
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
