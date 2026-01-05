"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
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
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Loader2,
    XCircle,
    AlertTriangle,
    Clock,
    RotateCcw,
    RefreshCw,
} from "lucide-react";
import { datasetVersionApi, type EnrichedBuildData } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import {
    SearchFilterBar,
    PROCESSING_STATUS_OPTIONS,
} from "@/components/builds";

const ITEMS_PER_PAGE = 20;

/** Format relative time */


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

export default function ProcessingPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const router = useRouter();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    const [currentPage, setCurrentPage] = useState(1);
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [builds, setBuilds] = useState<EnrichedBuildData[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [retryLoading, setRetryLoading] = useState(false);
    const [failedCount, setFailedCount] = useState(0);

    // Fetch enrichment builds
    useEffect(() => {
        async function fetchBuilds() {
            setLoading(true);
            try {
                const skip = (currentPage - 1) * ITEMS_PER_PAGE;
                const response = await datasetVersionApi.getEnrichmentBuilds(
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
                        item.raw_build_run_id.toLowerCase().includes(searchLower) ||
                        item.repo_full_name.toLowerCase().includes(searchLower)
                    );
                }
                setBuilds(filteredItems);
                setTotal(searchQuery ? filteredItems.length : response.total);
            } catch (err) {
                console.error("Failed to fetch enrichment builds:", err);
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
                const response = await datasetVersionApi.getEnrichmentBuilds(
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

    const handleRetryProcessing = async () => {
        setRetryLoading(true);
        try {
            await datasetVersionApi.retryProcessing(datasetId, versionId);
            // Refresh builds
            setCurrentPage(1);
        } catch (err) {
            console.error("Failed to retry processing:", err);
        } finally {
            setRetryLoading(false);
        }
    };

    const totalPages = Math.ceil(total / ITEMS_PER_PAGE);
    const canRetryProcessing = failedCount > 0;

    const handleRefresh = useCallback(async () => {
        setLoading(true);
        try {
            const skip = (currentPage - 1) * ITEMS_PER_PAGE;
            const response = await datasetVersionApi.getEnrichmentBuilds(
                datasetId,
                versionId,
                skip,
                ITEMS_PER_PAGE,
                statusFilter !== "all" ? statusFilter : undefined
            );
            setBuilds(response.items);
            setTotal(response.total);
        } catch (err) {
            console.error("Failed to refresh builds:", err);
        } finally {
            setLoading(false);
        }
    }, [datasetId, versionId, currentPage, statusFilter]);

    return (
        <div className="space-y-4">
            {/* Search and Filter */}
            <SearchFilterBar
                placeholder="Search by build ID or repository..."
                statusOptions={PROCESSING_STATUS_OPTIONS}
                onSearch={handleSearch}
                onStatusFilter={handleStatusFilter}
                isLoading={loading}
            />

            {/* Builds Table */}
            {loading ? (
                <div className="flex min-h-[200px] items-center justify-center">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : builds.length === 0 ? (
                <Card>
                    <CardContent className="py-8 text-center text-muted-foreground">
                        No enrichment builds found. Processing may not have started yet.
                    </CardContent>
                </Card>
            ) : (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base">Enrichment Builds</CardTitle>
                                <CardDescription>
                                    {total} builds with feature extraction
                                </CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleRefresh}
                                >
                                    <RefreshCw className="h-4 w-4 mr-1" />
                                    Refresh
                                </Button>
                                <Button
                                    variant="outline"
                                    onClick={handleRetryProcessing}
                                    disabled={retryLoading || failedCount === 0}
                                    className={cn("gap-2", failedCount === 0 && "opacity-50")}
                                >
                                    {retryLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <RotateCcw className="h-4 w-4" />
                                    )}
                                    Retry Failed ({failedCount})
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="rounded-md border overflow-hidden">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-8"></TableHead>
                                        <TableHead>Build ID</TableHead>
                                        <TableHead>Repository</TableHead>
                                        <TableHead className="text-center">Status</TableHead>
                                        <TableHead className="text-center">Features</TableHead>
                                        <TableHead className="text-right">Created At</TableHead>
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
                                                onClick={() => router.push(`/projects/${datasetId}/builds/${build.id}?versionId=${versionId}`)}
                                            >
                                                <TableCell className="py-2"></TableCell>
                                                <TableCell className="font-mono text-sm py-2" title={build.ci_run_id}>
                                                    {build.ci_run_id}
                                                </TableCell>
                                                <TableCell className="text-sm py-2">
                                                    {build.repo_full_name}
                                                </TableCell>
                                                <TableCell className="py-2">
                                                    <div className="flex justify-center">
                                                        <Badge variant="outline" className={cn("justify-center", statusConfig.color)}>
                                                            <StatusIcon className={cn("mr-1 h-3 w-3", build.extraction_status === "in_progress" && "animate-spin")} />
                                                            {statusConfig.label}
                                                        </Badge>
                                                    </div>
                                                </TableCell>
                                                <TableCell className="text-center text-sm py-2">
                                                    {build.feature_count}/{build.expected_feature_count}
                                                </TableCell>
                                                <TableCell className="text-right text-xs text-muted-foreground py-2">
                                                    {formatDateTime(build.created_at)}
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        </div>
                    </CardContent>
                </Card>
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
        </div >
    );
}
