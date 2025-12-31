"use client";

import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock,
    ExternalLink,
    GitCommit,
    Loader2,
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
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi } from "@/lib/api";
import { formatTimestamp } from "@/lib/utils";
import type { ImportBuild } from "@/types";

const PAGE_SIZE = 20;

function IngestionStatusBadge({ status }: { status: string }) {
    const s = status.toLowerCase();
    if (s === "ingested") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Ingested
            </Badge>
        );
    }
    if (s === "ingesting") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> Ingesting
            </Badge>
        );
    }
    if (s === "fetched") {
        return (
            <Badge variant="outline" className="border-blue-500 text-blue-600 gap-1">
                <Clock className="h-3 w-3" /> Fetched
            </Badge>
        );
    }
    if (s === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }
    return <Badge variant="secondary">{status}</Badge>;
}

function ResourceStatusIcon({ status }: { status: string }) {
    const s = status?.toLowerCase() || "pending";
    if (s === "completed" || s === "skipped") {
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    }
    if (s === "failed") {
        return <XCircle className="h-4 w-4 text-red-500" />;
    }
    if (s === "in_progress") {
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    }
    return <Clock className="h-4 w-4 text-muted-foreground" />;
}

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

    const { subscribe } = useWebSocket();

    const loadBuilds = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) setTableLoading(true);
            try {
                const data = await buildApi.getImportBuilds(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
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
        [repoId]
    );

    useEffect(() => {
        loadBuilds(1, true);
    }, [loadBuilds]);

    useEffect(() => {
        const unsubscribe = subscribe("BUILD_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                loadBuilds(page);
            }
        });
        return () => unsubscribe();
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

    const failedCount = builds.filter((b) => b.status === "failed").length;
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
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>Ingestion Builds</CardTitle>
                    <CardDescription>
                        Builds fetched from CI with resource ingestion status
                    </CardDescription>
                </div>
                {onRetryAllFailed && failedCount > 0 && (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onRetryAllFailed}
                        disabled={retryAllLoading}
                    >
                        {retryAllLoading ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        Retry All Failed ({failedCount})
                    </Button>
                )}
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
                                    git_history
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    git_worktree
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    build_logs
                                </th>
                                <th className="px-4 py-3 text-left font-medium text-slate-500">
                                    Date
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                            {builds.length === 0 ? (
                                <tr>
                                    <td
                                        colSpan={8}
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
                                                    className={`hover:bg-slate-50 dark:hover:bg-slate-900/40 transition ${hasErrors ? "cursor-pointer" : ""
                                                        }`}
                                                >
                                                    <td className="px-4 py-3">
                                                        {hasErrors && (
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
                                                        )}
                                                    </td>
                                                    <td className="px-4 py-3 font-medium">
                                                        #{build.build_number || "—"}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex items-center gap-1 font-mono text-xs">
                                                            <GitCommit className="h-3 w-3" />
                                                            {build.commit_sha?.substring(0, 7)}
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <IngestionStatusBadge status={build.status} />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <ResourceStatusIcon
                                                            status={
                                                                build.resource_status?.git_history?.status ||
                                                                "pending"
                                                            }
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <ResourceStatusIcon
                                                            status={
                                                                build.resource_status?.git_worktree?.status ||
                                                                "pending"
                                                            }
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <ResourceStatusIcon
                                                            status={
                                                                build.resource_status?.build_logs?.status ||
                                                                "pending"
                                                            }
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3 text-muted-foreground">
                                                        {formatTimestamp(build.created_at)}
                                                    </td>
                                                </tr>
                                                {hasErrors && (
                                                    <CollapsibleContent asChild>
                                                        <tr className="bg-red-50 dark:bg-red-900/10">
                                                            <td colSpan={8} className="px-4 py-3">
                                                                <div className="space-y-2 text-sm">
                                                                    <p className="font-medium text-red-600">
                                                                        Resource Errors:
                                                                    </p>
                                                                    <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                                                                        {Object.entries(
                                                                            build.resource_status || {}
                                                                        ).map(
                                                                            ([key, val]) =>
                                                                                val.error && (
                                                                                    <li key={key}>
                                                                                        <span className="font-mono">{key}</span>:{" "}
                                                                                        {val.error}
                                                                                    </li>
                                                                                )
                                                                        )}
                                                                    </ul>
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
                {/* Pagination */}
                <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
                    <div>
                        {total > 0
                            ? `Showing ${pageStart}-${pageEnd} of ${total}`
                            : "No builds"}
                    </div>
                    <div className="flex items-center gap-2">
                        {tableLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePageChange("prev")}
                            disabled={page === 1 || tableLoading}
                        >
                            Previous
                        </Button>
                        <span className="text-xs">
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
            </CardContent>
        </Card>
    );
}
