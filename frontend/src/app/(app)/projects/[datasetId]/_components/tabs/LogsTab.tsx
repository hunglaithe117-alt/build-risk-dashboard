"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle, XCircle, Clock, Loader2, GitBranch, ScrollText } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface RepoInfo {
    full_name?: string;
    name?: string;
}

interface BuildInfo {
    run_number?: number;
    event?: string;
    head_branch?: string;
    workflow_name?: string;
}

interface FeatureAuditLog {
    id: string;
    category: "model_training" | "dataset_enrichment";
    raw_repo_id: string;
    raw_build_run_id: string;
    repo?: RepoInfo;
    build?: BuildInfo;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    duration_ms: number | null;
    feature_count: number;
    nodes_executed: number;
    nodes_succeeded: number;
    nodes_failed: number;
    errors: string[];
}

interface LogsTabProps {
    datasetId: string;
}

const statusConfig: Record<
    string,
    { icon: React.ReactNode; variant: "default" | "destructive" | "secondary" | "outline" }
> = {
    completed: {
        icon: <CheckCircle className="h-3 w-3" />,
        variant: "default",
    },
    failed: {
        icon: <XCircle className="h-3 w-3" />,
        variant: "destructive",
    },
    running: {
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
        variant: "secondary",
    },
    pending: {
        icon: <Clock className="h-3 w-3" />,
        variant: "outline",
    },
};

export function LogsTab({ datasetId }: LogsTabProps) {
    const [logs, setLogs] = useState<FeatureAuditLog[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [hasMore, setHasMore] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingMore, setIsLoadingMore] = useState(false);

    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const loadMoreTriggerRef = useRef<HTMLDivElement>(null);

    const fetchLogs = useCallback(async (cursor?: string | null) => {
        const isInitial = !cursor;
        if (isInitial) {
            setIsLoading(true);
        } else {
            setIsLoadingMore(true);
        }

        try {
            const params = new URLSearchParams({ limit: "20" });
            if (cursor) params.set("cursor", cursor);

            const res = await fetch(
                `${API_BASE}/datasets/${datasetId}/audit-logs/cursor?${params.toString()}`,
                { credentials: "include" }
            );

            if (res.ok) {
                const data = await res.json();
                if (isInitial) {
                    setLogs(data.logs);
                } else {
                    setLogs((prev) => [...prev, ...data.logs]);
                }
                setNextCursor(data.next_cursor);
                setHasMore(data.has_more);
            }
        } catch (error) {
            console.error("Failed to fetch audit logs:", error);
        } finally {
            setIsLoading(false);
            setIsLoadingMore(false);
        }
    }, [datasetId]);

    // Initial fetch
    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    // Infinite scroll
    const handleObserver = useCallback(
        (entries: IntersectionObserverEntry[]) => {
            const [entry] = entries;
            if (entry.isIntersecting && hasMore && !isLoadingMore && !isLoading) {
                fetchLogs(nextCursor);
            }
        },
        [hasMore, isLoadingMore, isLoading, nextCursor, fetchLogs]
    );

    useEffect(() => {
        const element = loadMoreTriggerRef.current;
        if (!element) return;

        const observer = new IntersectionObserver(handleObserver, {
            root: scrollContainerRef.current,
            rootMargin: "100px",
            threshold: 0.1,
        });

        observer.observe(element);
        return () => observer.disconnect();
    }, [handleObserver]);

    if (isLoading && logs.length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-lg">
                        <ScrollText className="h-5 w-5" />
                        Feature Extraction Logs
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="animate-pulse space-y-2">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <div key={i} className="h-12 bg-muted rounded" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-lg">
                        <ScrollText className="h-5 w-5" />
                        Feature Extraction Logs
                    </CardTitle>
                    <Badge variant="outline">{logs.length} loaded</Badge>
                </div>
            </CardHeader>
            <CardContent
                ref={scrollContainerRef}
                className="max-h-[500px] overflow-y-auto"
            >
                {logs.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                        <ScrollText className="h-12 w-12 mx-auto mb-3 opacity-50" />
                        <p>No extraction logs yet.</p>
                        <p className="text-sm">Logs will appear here when you run enrichment.</p>
                    </div>
                ) : (
                    <Table>
                        <TableHeader className="sticky top-0 bg-background z-10">
                            <TableRow>
                                <TableHead className="w-[100px]">Status</TableHead>
                                <TableHead>Repository / Build</TableHead>
                                <TableHead className="w-[70px]">Features</TableHead>
                                <TableHead className="w-[90px]">Nodes</TableHead>
                                <TableHead className="w-[70px]">Duration</TableHead>
                                <TableHead className="w-[100px]">Started</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {logs.map((log) => {
                                const config = statusConfig[log.status] || statusConfig.pending;
                                return (
                                    <TableRow key={log.id}>
                                        <TableCell>
                                            <Badge variant={config.variant} className="gap-1">
                                                {config.icon}
                                                {log.status}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex flex-col gap-1">
                                                <span
                                                    className="font-medium text-sm truncate max-w-[180px]"
                                                    title={log.repo?.full_name}
                                                >
                                                    {log.repo?.full_name || log.repo?.name || "Unknown"}
                                                </span>
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    {log.build?.run_number && (
                                                        <span className="font-mono">#{log.build.run_number}</span>
                                                    )}
                                                    {log.build?.head_branch && (
                                                        <span className="flex items-center gap-0.5">
                                                            <GitBranch className="h-3 w-3" />
                                                            <span
                                                                className="truncate max-w-[80px]"
                                                                title={log.build.head_branch}
                                                            >
                                                                {log.build.head_branch}
                                                            </span>
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-center">{log.feature_count}</TableCell>
                                        <TableCell>
                                            <span className="text-green-600">{log.nodes_succeeded}</span>
                                            {log.nodes_failed > 0 && (
                                                <>
                                                    {" / "}
                                                    <span className="text-red-600">{log.nodes_failed}</span>
                                                </>
                                            )}
                                            <span className="text-muted-foreground">
                                                {" "}/ {log.nodes_executed}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            {log.duration_ms
                                                ? `${(log.duration_ms / 1000).toFixed(1)}s`
                                                : "-"}
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">
                                            {log.started_at
                                                ? formatDistanceToNow(new Date(log.started_at), {
                                                    addSuffix: true,
                                                })
                                                : "-"}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                )}

                {/* Load more trigger */}
                <div ref={loadMoreTriggerRef} className="h-4" />

                {/* Loading more indicator */}
                {isLoadingMore && (
                    <div className="flex items-center justify-center py-4">
                        <Loader2 className="h-5 w-5 animate-spin mr-2" />
                        <span className="text-sm text-muted-foreground">Loading more...</span>
                    </div>
                )}

                {/* End of list indicator */}
                {!hasMore && logs.length > 0 && (
                    <div className="text-center py-2 text-xs text-muted-foreground">
                        All {logs.length} logs loaded
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
