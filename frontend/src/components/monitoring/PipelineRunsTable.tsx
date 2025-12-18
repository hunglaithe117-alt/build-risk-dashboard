"use client";

import React, { useRef, useCallback, useEffect } from "react";
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
import { CheckCircle, XCircle, Clock, Loader2, GitBranch } from "lucide-react";

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

interface PipelineRun {
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

interface PipelineRunsTableProps {
    runs: PipelineRun[];
    hasMore: boolean;
    isLoading: boolean;
    isLoadingMore: boolean;
    onLoadMore: () => void;
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

export function PipelineRunsTable({
    runs,
    hasMore,
    isLoading,
    isLoadingMore,
    onLoadMore,
}: PipelineRunsTableProps) {
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const loadMoreTriggerRef = useRef<HTMLDivElement>(null);

    // Infinite scroll with IntersectionObserver
    const handleObserver = useCallback(
        (entries: IntersectionObserverEntry[]) => {
            const [entry] = entries;
            if (entry.isIntersecting && hasMore && !isLoadingMore && !isLoading) {
                onLoadMore();
            }
        },
        [hasMore, isLoadingMore, isLoading, onLoadMore]
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

    if (isLoading && runs.length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-lg">Pipeline Runs</CardTitle>
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
                    <CardTitle className="text-lg">Pipeline Runs</CardTitle>
                    <Badge variant="outline">{runs.length} loaded</Badge>
                </div>
            </CardHeader>
            <CardContent
                ref={scrollContainerRef}
                className="max-h-[400px] overflow-y-auto"
            >
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
                        {runs.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center text-muted-foreground">
                                    No pipeline runs found
                                </TableCell>
                            </TableRow>
                        ) : (
                            runs.map((run) => {
                                const config = statusConfig[run.status] || statusConfig.pending;
                                return (
                                    <TableRow key={run.id}>
                                        <TableCell>
                                            <Badge variant={config.variant} className="gap-1">
                                                {config.icon}
                                                {run.status}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex flex-col gap-1">
                                                <span className="font-medium text-sm truncate max-w-[180px]" title={run.repo?.full_name}>
                                                    {run.repo?.full_name || run.repo?.name || "Unknown"}
                                                </span>
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <Badge variant="outline" className="text-xs px-1.5 py-0">
                                                        {run.category === "model_training" ? "🔧 Model" : "📊 Dataset"}
                                                    </Badge>
                                                    {run.build?.run_number && (
                                                        <span className="font-mono">#{run.build.run_number}</span>
                                                    )}
                                                    {run.build?.head_branch && (
                                                        <span className="flex items-center gap-0.5">
                                                            <GitBranch className="h-3 w-3" />
                                                            <span className="truncate max-w-[80px]" title={run.build.head_branch}>
                                                                {run.build.head_branch}
                                                            </span>
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-center">{run.feature_count}</TableCell>
                                        <TableCell>
                                            <span className="text-green-600">{run.nodes_succeeded}</span>
                                            {run.nodes_failed > 0 && (
                                                <>
                                                    {" / "}
                                                    <span className="text-red-600">{run.nodes_failed}</span>
                                                </>
                                            )}
                                            <span className="text-muted-foreground">
                                                {" "}/ {run.nodes_executed}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            {run.duration_ms
                                                ? `${(run.duration_ms / 1000).toFixed(1)}s`
                                                : "-"}
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">
                                            {run.started_at
                                                ? formatDistanceToNow(new Date(run.started_at), {
                                                    addSuffix: true,
                                                })
                                                : "-"}
                                        </TableCell>
                                    </TableRow>
                                );
                            })
                        )}
                    </TableBody>
                </Table>

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
                {!hasMore && runs.length > 0 && (
                    <div className="text-center py-2 text-xs text-muted-foreground">
                        All {runs.length} runs loaded
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
