"use client";

import {
    UploadCloud,
    Database,
    GitBranch,
    Loader2,
    Plus,
    RefreshCw,
    Settings2,
    Trash2,
    CheckCircle2,
    TrendingUp,
} from "lucide-react";
import { useRouter } from "next/navigation";
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
import { toast } from "@/components/ui/use-toast";
import { useDebounce } from "@/hooks/use-debounce";
import { trainingScenariosApi } from "@/lib/api";
import type { TrainingScenarioRecord, TrainingScenarioStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useSSE } from "@/contexts/sse-context";

const PAGE_SIZE = 20;

function formatNumber(value: number) {
    return value.toLocaleString("en-US");
}

function getStatusBadge(status: TrainingScenarioStatus) {
    const statusConfig: Record<
        TrainingScenarioStatus,
        { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className?: string }
    > = {
        queued: { label: "Queued", variant: "outline", className: "border-slate-400 text-slate-400" },
        filtering: { label: "Filtering...", variant: "outline", className: "border-blue-500 text-blue-500" },
        ingesting: { label: "Ingesting...", variant: "outline", className: "border-blue-500 text-blue-500" },
        ingested: { label: "Ingested", variant: "outline", className: "border-emerald-500 text-emerald-500" },
        processing: { label: "Processing...", variant: "outline", className: "border-purple-500 text-purple-500" },
        processed: { label: "Processed", variant: "outline", className: "border-emerald-500 text-emerald-500" },
        splitting: { label: "Splitting...", variant: "outline", className: "border-orange-500 text-orange-500" },
        completed: { label: "Completed", variant: "default", className: "bg-emerald-600 text-white" },
        failed: { label: "Failed", variant: "destructive" },
    };

    const config = statusConfig[status] || statusConfig.queued;
    return (
        <Badge variant={config.variant} className={config.className}>
            {config.label}
        </Badge>
    );
}

export default function ScenariosPage() {
    const router = useRouter();
    const [scenarios, setScenarios] = useState<TrainingScenarioRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);

    // Statistics
    const [stats, setStats] = useState({
        totalBuilds: 0,
        totalRepos: 0,
        successRate: 0,
    });

    // Search and pagination
    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearchQuery = useDebounce(searchQuery, 500);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);

    const loadScenarios = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) {
                setTableLoading(true);
            }
            try {
                const data = await trainingScenariosApi.list({
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: debouncedSearchQuery || undefined,
                });
                setScenarios(data.items || []);
                setTotal(data.total);
                setPage(pageNumber);
            } catch (err) {
                console.error(err);
                toast({
                    title: "Error",
                    description: "Failed to load scenarios",
                    variant: "destructive",
                });
            } finally {
                setLoading(false);
                setTableLoading(false);
            }
        },
        [debouncedSearchQuery]
    );

    // Load stats from preview endpoint
    const loadStats = useCallback(async () => {
        try {
            const response = await trainingScenariosApi.previewBuilds({ limit: 1 });
            setStats({
                totalBuilds: response.stats.total_builds,
                totalRepos: response.stats.total_repos,
                successRate: response.stats.total_builds > 0
                    ? Math.round((response.stats.outcome_distribution.success / response.stats.total_builds) * 1000) / 10
                    : 0,
            });
        } catch (err) {
            console.error("Failed to load stats:", err);
        }
    }, []);

    useEffect(() => {
        loadScenarios(1, true);
        loadStats();
    }, [loadScenarios, loadStats]);

    // SSE subscription for real-time updates
    const { subscribe } = useSSE();

    useEffect(() => {
        const unsubscribe = subscribe("SCENARIO_UPDATE", (data: {
            scenario_id: string;
            status?: TrainingScenarioStatus;
            builds_ingested?: number;
            builds_total?: number;
            builds_features_extracted?: number;
            error_message?: string;
        }) => {
            setScenarios((prev) =>
                prev.map((s) => {
                    if (s.id === data.scenario_id) {
                        return {
                            ...s,
                            status: data.status ?? s.status,
                            builds_ingested: data.builds_ingested ?? s.builds_ingested,
                            builds_total: data.builds_total ?? s.builds_total,
                            builds_features_extracted: data.builds_features_extracted ?? s.builds_features_extracted,
                            error_message: data.error_message ?? s.error_message,
                        };
                    }
                    return s;
                })
            );

            if (data.status === "completed" || data.status === "failed") {
                loadScenarios(page, false);
            }
        });

        return () => unsubscribe();
    }, [subscribe, loadScenarios, page]);

    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
    const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

    const handlePageChange = (direction: "prev" | "next") => {
        const targetPage =
            direction === "prev"
                ? Math.max(1, page - 1)
                : Math.min(totalPages, page + 1);
        if (targetPage !== page) {
            void loadScenarios(targetPage, true);
        }
    };

    const handleDelete = async (scenario: TrainingScenarioRecord) => {
        if (!confirm(`Delete scenario "${scenario.name}"? This cannot be undone.`)) {
            return;
        }
        try {
            await trainingScenariosApi.delete(scenario.id);
            toast({ title: "Deleted", description: `Scenario "${scenario.name}" deleted.` });
            loadScenarios(page, true);
        } catch (err) {
            console.error(err);
            toast({
                title: "Error",
                description: "Failed to delete scenario",
                variant: "destructive",
            });
        }
    };

    if (loading) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Page Header with Action Buttons */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div>
                        <h1 className="text-2xl font-bold">Dataset Enrichments</h1>
                        <p className="text-sm text-muted-foreground">
                            Build and manage training datasets from your build data
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        onClick={() => router.push("/scenarios/upload")}
                    >
                        Upload CSV
                    </Button>
                    <Button
                        onClick={() => router.push("/scenarios/create")}
                        className="bg-emerald-600 hover:bg-emerald-700"
                    >
                        <Plus className="h-4 w-4 mr-2" />
                        New Version
                    </Button>
                </div>
            </div>

            {/* Statistics Bar */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                            <Database className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <div className="text-2xl font-bold">{formatNumber(stats.totalBuilds)}</div>
                                <p className="text-xs text-muted-foreground">Total Raw Builds</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                            <GitBranch className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <div className="text-2xl font-bold">{formatNumber(stats.totalRepos)}</div>
                                <p className="text-xs text-muted-foreground">Repositories</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                            <TrendingUp className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <div className="text-2xl font-bold">{stats.successRate}%</div>
                                <p className="text-xs text-muted-foreground">Success Rate</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Dataset Versions Table */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Dataset Versions</CardTitle>
                            <CardDescription>
                                Created dataset versions and their processing status
                            </CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="relative w-64">
                                <Input
                                    placeholder="Search versions..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="h-9"
                                />
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => loadScenarios(page, true)}
                                disabled={tableLoading}
                            >
                                <RefreshCw className={`h-4 w-4 mr-1 ${tableLoading ? "animate-spin" : ""}`} />
                                Refresh
                            </Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Name
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Status
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Builds
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Strategy
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Created
                                    </th>
                                    <th className="px-6 py-3" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {scenarios.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={6}
                                            className="px-6 py-12 text-center text-muted-foreground"
                                        >
                                            <div className="flex flex-col items-center gap-3">
                                                <CheckCircle2 className="h-12 w-12 text-slate-300" />
                                                <p>No dataset versions yet.</p>
                                                <p className="text-sm">Create your first version using the button above.</p>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    scenarios.map((scenario) => (
                                        <tr
                                            key={scenario.id}
                                            className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                            onClick={() => router.push(`/scenarios/${scenario.id}`)}
                                        >
                                            <td className="px-6 py-4">
                                                <div>
                                                    <p className="font-medium text-foreground">{scenario.name}</p>
                                                    {scenario.description && (
                                                        <p className="text-xs text-muted-foreground truncate max-w-xs">
                                                            {scenario.description}
                                                        </p>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                {getStatusBadge(scenario.status)}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                <span className="font-medium">{formatNumber(scenario.builds_ingested)}</span>
                                                <span className="text-slate-400"> / {formatNumber(scenario.builds_total)}</span>
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground capitalize">
                                                {scenario.splitting_strategy?.replace(/_/g, " ") || "—"}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {formatDateTime(scenario.created_at)}
                                            </td>
                                            <td className="px-6 py-4">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="h-8 w-8 p-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-900/20"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleDelete(scenario);
                                                    }}
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                    <span className="sr-only">Delete</span>
                                                </Button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
                {total > 0 && (
                    <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 text-sm text-muted-foreground dark:border-slate-800">
                        <div>
                            Showing {pageStart}-{pageEnd} of {total} versions
                        </div>
                        <div className="flex flex-wrap items-center gap-3">
                            {tableLoading && (
                                <div className="flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    <span className="text-xs">Refreshing...</span>
                                </div>
                            )}
                            <div className="flex items-center gap-2">
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => handlePageChange("prev")}
                                    disabled={page === 1 || tableLoading}
                                >
                                    Previous
                                </Button>
                                <span className="text-xs text-muted-foreground">
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
                    </div>
                )}
            </Card>
        </div>
    );
}
