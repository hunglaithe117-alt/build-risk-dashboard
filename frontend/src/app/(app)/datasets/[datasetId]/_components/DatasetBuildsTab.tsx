"use client";

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
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { enrichmentApi } from "@/lib/api";
import type { DatasetRecord, EnrichmentJob } from "@/types";
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    Loader2,
    RefreshCw,
    RotateCcw,
    Search,
    XCircle,
} from "lucide-react";

interface DatasetBuildsTabProps {
    datasetId: string;
    dataset: DatasetRecord;
}

interface EnrichmentBuild {
    id: string;
    build_id: string;
    repo_name: string;
    commit_sha: string;
    extraction_status: "pending" | "running" | "completed" | "failed";
    features_count: number;
    error_message?: string;
    created_at: string;
    updated_at: string;
}

type StatusFilter = "all" | "pending" | "running" | "completed" | "failed";

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; className: string }> = {
    pending: {
        label: "Pending",
        icon: Clock,
        className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    },
    running: {
        label: "Processing",
        icon: Loader2,
        className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
    },
    completed: {
        label: "Completed",
        icon: CheckCircle2,
        className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
    },
    failed: {
        label: "Failed",
        icon: XCircle,
        className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    },
};

export function DatasetBuildsTab({
    datasetId,
    dataset,
}: DatasetBuildsTabProps) {
    const [builds, setBuilds] = useState<EnrichmentBuild[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
    const [enrichmentJob, setEnrichmentJob] = useState<EnrichmentJob | null>(null);

    // Load builds
    const loadBuilds = useCallback(async () => {
        setLoading(true);
        try {
            // Try to get enrichment status and builds
            const status = await enrichmentApi.getStatus(datasetId);
            setEnrichmentJob(status as unknown as EnrichmentJob);

            // For now, simulate builds from dataset rows
            // In production, this would come from the API
            const mockBuilds: EnrichmentBuild[] = [];
            setBuilds(mockBuilds);
        } catch {
            // No enrichment job yet
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    useEffect(() => {
        loadBuilds();
    }, [loadBuilds]);

    // Filter builds
    const filteredBuilds = builds.filter((build) => {
        const matchesSearch =
            build.build_id.toLowerCase().includes(search.toLowerCase()) ||
            build.repo_name.toLowerCase().includes(search.toLowerCase()) ||
            build.commit_sha.toLowerCase().includes(search.toLowerCase());
        const matchesStatus = statusFilter === "all" || build.extraction_status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    // Stats
    const stats = {
        total: builds.length,
        completed: builds.filter((b) => b.extraction_status === "completed").length,
        processing: builds.filter((b) => b.extraction_status === "running").length,
        failed: builds.filter((b) => b.extraction_status === "failed").length,
        pending: builds.filter((b) => b.extraction_status === "pending").length,
    };

    const totalFeatures = dataset.selected_features?.length || 0;

    return (
        <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-2xl font-bold">{dataset.rows}</div>
                        <p className="text-xs text-muted-foreground">Total Rows</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
                        <p className="text-xs text-muted-foreground">Completed</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-2xl font-bold text-blue-600">{stats.processing}</div>
                        <p className="text-xs text-muted-foreground">Processing</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-2xl font-bold text-red-600">{stats.failed}</div>
                        <p className="text-xs text-muted-foreground">Failed</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="text-2xl font-bold text-slate-600">{stats.pending}</div>
                        <p className="text-xs text-muted-foreground">Pending</p>
                    </CardContent>
                </Card>
            </div>

            {/* Enrichment Status */}
            {enrichmentJob && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg">Enrichment Progress</CardTitle>
                                <CardDescription>
                                    Job ID: {enrichmentJob.id}
                                </CardDescription>
                            </div>
                            <Badge
                                className={
                                    enrichmentJob.status === "completed"
                                        ? "bg-green-500"
                                        : enrichmentJob.status === "running"
                                            ? "bg-blue-500"
                                            : enrichmentJob.status === "failed"
                                                ? "bg-red-500"
                                                : "bg-slate-500"
                                }
                            >
                                {enrichmentJob.status}
                            </Badge>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            <div className="flex justify-between text-sm">
                                <span>Progress</span>
                                <span>{enrichmentJob.progress_percent?.toFixed(1) || 0}%</span>
                            </div>
                            <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-blue-500 transition-all"
                                    style={{ width: `${enrichmentJob.progress_percent || 0}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>
                                    {enrichmentJob.processed_rows || 0} / {enrichmentJob.total_rows || 0} rows
                                </span>
                                <span>
                                    {enrichmentJob.enriched_rows || 0} enriched, {enrichmentJob.failed_rows || 0} failed
                                </span>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* No Enrichment Started */}
            {!enrichmentJob && !loading && (
                <Card className="border-dashed">
                    <CardContent className="flex flex-col items-center justify-center py-12">
                        <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
                        <h3 className="text-lg font-semibold mb-2">No Enrichment Started</h3>
                        <p className="text-sm text-muted-foreground text-center max-w-md mb-4">
                            Start the enrichment process from the Features tab to extract
                            features for each build in your dataset.
                        </p>
                        <Button variant="outline">
                            Go to Features Tab
                        </Button>
                    </CardContent>
                </Card>
            )}

            {/* Filters */}
            {builds.length > 0 && (
                <>
                    <div className="flex items-center gap-4">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                placeholder="Search by build ID, repo, or commit..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as StatusFilter)}>
                            <SelectTrigger className="w-[180px]">
                                <SelectValue placeholder="Filter by status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All Status</SelectItem>
                                <SelectItem value="completed">Completed</SelectItem>
                                <SelectItem value="running">Processing</SelectItem>
                                <SelectItem value="failed">Failed</SelectItem>
                                <SelectItem value="pending">Pending</SelectItem>
                            </SelectContent>
                        </Select>
                        <Button variant="outline" size="icon" onClick={loadBuilds}>
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </div>

                    {/* Builds Table */}
                    <Card>
                        <CardContent className="p-0">
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700">
                                    <thead className="bg-slate-50 dark:bg-slate-800">
                                        <tr>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Build ID
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Repository
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Commit
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Status
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Features
                                            </th>
                                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                                Actions
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                                        {filteredBuilds.length === 0 ? (
                                            <tr>
                                                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                                                    {search || statusFilter !== "all"
                                                        ? "No builds match your filters"
                                                        : "No builds found"}
                                                </td>
                                            </tr>
                                        ) : (
                                            filteredBuilds.map((build) => {
                                                const statusConfig = STATUS_CONFIG[build.extraction_status];
                                                const StatusIcon = statusConfig.icon;
                                                return (
                                                    <tr key={build.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                                                        <td className="px-4 py-3 font-mono text-sm">{build.build_id}</td>
                                                        <td className="px-4 py-3 text-sm">{build.repo_name}</td>
                                                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                                                            {build.commit_sha.slice(0, 7)}
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            <Badge className={statusConfig.className}>
                                                                <StatusIcon
                                                                    className={`h-3 w-3 mr-1 ${build.extraction_status === "running" ? "animate-spin" : ""
                                                                        }`}
                                                                />
                                                                {statusConfig.label}
                                                            </Badge>
                                                        </td>
                                                        <td className="px-4 py-3 text-sm">
                                                            <span className="font-medium">{build.features_count}</span>
                                                            <span className="text-muted-foreground">/{totalFeatures}</span>
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            {build.extraction_status === "failed" && (
                                                                <Button variant="ghost" size="sm">
                                                                    <RotateCcw className="h-4 w-4 mr-1" />
                                                                    Retry
                                                                </Button>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </>
            )}

            {/* Loading */}
            {loading && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            )}
        </div>
    );
}
