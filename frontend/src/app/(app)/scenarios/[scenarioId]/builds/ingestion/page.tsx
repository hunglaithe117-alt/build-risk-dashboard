"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import {
    trainingScenariosApi,
    TrainingIngestionBuildRecord,
    PaginatedResponse,
} from "@/lib/api/training-scenarios";
import { useSSE } from "@/contexts/sse-context";

const statusColors: Record<string, string> = {
    pending: "bg-slate-100 text-slate-700",
    ingesting: "bg-blue-100 text-blue-700",
    ingested: "bg-green-100 text-green-700",
    missing_resource: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
};

export default function IngestionBuildsPage() {
    const params = useParams<{ scenarioId: string }>();
    const scenarioId = params.scenarioId;
    const { subscribe } = useSSE();

    const [data, setData] = useState<PaginatedResponse<TrainingIngestionBuildRecord> | null>(null);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const pageSize = 20;

    const fetchBuilds = useCallback(async () => {
        setLoading(true);
        try {
            const response = await trainingScenariosApi.getIngestionBuilds(scenarioId, {
                skip: (page - 1) * pageSize,
                limit: pageSize,
            });
            setData(response);
        } catch (err) {
            console.error("Failed to fetch ingestion builds:", err);
        } finally {
            setLoading(false);
        }
    }, [scenarioId, page]);

    useEffect(() => {
        fetchBuilds();
    }, [fetchBuilds]);

    // SSE subscription - refetch on scenario updates
    useEffect(() => {
        const unsubscribe = subscribe("SCENARIO_UPDATE", (payload: { scenario_id?: string }) => {
            if (payload.scenario_id === scenarioId) {
                fetchBuilds();
            }
        });
        return () => unsubscribe();
    }, [subscribe, scenarioId, fetchBuilds]);

    const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

    return (
        <div className="space-y-4">
            {/* Header with refresh */}
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-muted-foreground">
                    {data?.total ?? 0} builds
                </h3>
                <Button variant="outline" size="sm" onClick={fetchBuilds} disabled={loading}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            <div className="border rounded-lg">

                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Repository</TableHead>
                            <TableHead>Commit</TableHead>
                            <TableHead>CI Run ID</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Created</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            Array.from({ length: 5 }).map((_, i) => (
                                <TableRow key={i}>
                                    <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                                    <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                                    <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                                    <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                                </TableRow>
                            ))
                        ) : data?.items.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                    No ingestion builds found
                                </TableCell>
                            </TableRow>
                        ) : (
                            data?.items.map((build) => (
                                <TableRow key={build.id}>
                                    <TableCell className="font-medium">{build.repo_full_name}</TableCell>
                                    <TableCell>
                                        <code className="text-xs">{build.commit_sha.slice(0, 7)}</code>
                                    </TableCell>
                                    <TableCell>
                                        <code className="text-xs">{build.ci_run_id}</code>
                                    </TableCell>
                                    <TableCell>
                                        <Badge className={statusColors[build.status] || "bg-slate-100"}>
                                            {build.status}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-sm text-muted-foreground">
                                        {build.created_at
                                            ? new Date(build.created_at).toLocaleDateString()
                                            : "-"}
                                    </TableCell>
                                </TableRow>
                            ))
                        )}
                    </TableBody>
                </Table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                        Page {page} of {totalPages} ({data?.total} total)
                    </p>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page === 1}
                            onClick={() => setPage((p) => p - 1)}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page >= totalPages}
                            onClick={() => setPage((p) => p + 1)}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
