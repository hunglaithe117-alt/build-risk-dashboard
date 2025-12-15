"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type { DatasetRecord } from "@/types";
import {
    AlertCircle,
    AlertTriangle,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock,
    Database,
    Download,
    ExternalLink,
    FileText,
    FolderGit2,
    GitBranch,
    GitCommit,
    Loader2,
    RefreshCw,
    XCircle,
} from "lucide-react";

interface DataTabProps {
    datasetId: string;
    dataset: DatasetRecord;
    onRefresh: () => void;
}

interface BuildItem {
    id: string;
    build_id_from_csv: string;
    repo_name_from_csv: string;
    status: string;
    validation_error?: string;
    validated_at?: string;
    build_number?: number;
    branch?: string;
    commit_sha?: string;
    commit_message?: string;
    commit_author?: string;
    conclusion?: string;
    started_at?: string;
    completed_at?: string;
    duration_seconds?: number;
    jobs_count?: number;
    logs_available?: boolean;
    logs_expired?: boolean;
    web_url?: string;
}

interface BuildsStats {
    status_breakdown: Record<string, number>;
    conclusion_breakdown: Record<string, number>;
    builds_per_repo: { repo: string; count: number }[];
    avg_duration_seconds?: number;
    logs_stats: { available: number; unavailable: number; expired: number };
    total_builds: number;
    found_builds: number;
}

interface LogFile {
    job_name: string;
    filename: string;
    content?: string;
    size_bytes?: number;
    error?: string;
}

interface LogsResponse {
    logs: LogFile[];
    logs_available: boolean;
    logs_expired: boolean;
    build_id?: string;
    repo_name?: string;
    error?: string;
}

function StatCard({
    icon: Icon,
    label,
    value,
    variant = "default",
}: {
    icon: React.ElementType;
    label: string;
    value: number | string;
    variant?: "default" | "success" | "warning" | "error";
}) {
    const colors = {
        default: "bg-slate-50 dark:bg-slate-800 text-slate-600",
        success: "bg-green-50 dark:bg-green-900/20 text-green-600",
        warning: "bg-amber-50 dark:bg-amber-900/20 text-amber-600",
        error: "bg-red-50 dark:bg-red-900/20 text-red-600",
    };

    return (
        <div className={`flex items-center gap-3 p-4 rounded-lg border ${colors[variant]}`}>
            <Icon className="h-5 w-5" />
            <div>
                <p className="text-2xl font-bold">{typeof value === "number" ? value.toLocaleString() : value}</p>
                <p className="text-xs text-muted-foreground">{label}</p>
            </div>
        </div>
    );
}

function formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DataTab({ datasetId, dataset, onRefresh }: DataTabProps) {
    const [polling, setPolling] = useState(false);
    const [builds, setBuilds] = useState<BuildItem[]>([]);
    const [stats, setStats] = useState<BuildsStats | null>(null);
    const [loadingBuilds, setLoadingBuilds] = useState(false);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    // Logs viewer state
    const [logsDialogOpen, setLogsDialogOpen] = useState(false);
    const [selectedBuild, setSelectedBuild] = useState<BuildItem | null>(null);
    const [logs, setLogs] = useState<LogsResponse | null>(null);
    const [loadingLogs, setLoadingLogs] = useState(false);

    const isValidated = dataset.validation_status === "completed";
    const ingestionStatus = dataset.ingestion_status || "pending";
    const ingestionProgress = dataset.ingestion_progress || 0;
    const isIngested = ingestionStatus === "completed";

    // Load builds and stats
    const loadBuilds = useCallback(async () => {
        if (!isIngested) return;
        setLoadingBuilds(true);
        try {
            const [buildsRes, statsRes] = await Promise.all([
                api.get<{ items: BuildItem[]; total: number }>(`/datasets/${datasetId}/builds?skip=${page * pageSize}&limit=${pageSize}&status_filter=found`),
                api.get<BuildsStats>(`/datasets/${datasetId}/builds/stats`),
            ]);
            setBuilds(buildsRes.data.items);
            setTotal(buildsRes.data.total);
            setStats(statsRes.data);
        } catch (err) {
            console.error("Failed to load builds:", err);
        } finally {
            setLoadingBuilds(false);
        }
    }, [datasetId, page, isIngested]);

    // Load logs for a build
    const loadLogs = async (build: BuildItem) => {
        setSelectedBuild(build);
        setLogsDialogOpen(true);
        setLoadingLogs(true);
        setLogs(null);
        try {
            const res = await api.get<LogsResponse>(`/datasets/${datasetId}/builds/${build.id}/logs`);
            setLogs(res.data);
        } catch (err) {
            console.error("Failed to load logs:", err);
            setLogs({ logs: [], logs_available: false, logs_expired: true, error: "Failed to load logs" });
        } finally {
            setLoadingLogs(false);
        }
    };

    // Poll for updates when ingesting
    useEffect(() => {
        if (ingestionStatus !== "ingesting") {
            setPolling(false);
            return;
        }
        setPolling(true);
        const interval = setInterval(() => { onRefresh(); }, 3000);
        return () => clearInterval(interval);
    }, [ingestionStatus, onRefresh]);

    // Load builds when ingested
    useEffect(() => { loadBuilds(); }, [loadBuilds]);

    if (!isValidated) {
        return (
            <Alert variant="destructive" className="my-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Dataset validation must be completed before data collection can start.
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-6">
            {/* Status Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Build Data</h2>
                <div className="flex items-center gap-2">
                    {ingestionStatus === "ingesting" && (
                        <Badge variant="outline" className="border-blue-500 text-blue-600">
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            Collecting...
                        </Badge>
                    )}
                    {ingestionStatus === "completed" && (
                        <Badge className="bg-green-500">
                            <CheckCircle2 className="mr-1 h-3 w-3" />
                            Ready
                        </Badge>
                    )}
                    {ingestionStatus === "failed" && (
                        <Badge variant="destructive">
                            <XCircle className="mr-1 h-3 w-3" />
                            Failed
                        </Badge>
                    )}
                    {ingestionStatus === "pending" && (
                        <Badge variant="secondary">
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            Queued
                        </Badge>
                    )}
                    <Button variant="outline" size="sm" onClick={() => { onRefresh(); loadBuilds(); }}>
                        <RefreshCw className={`h-4 w-4 ${polling ? "animate-spin" : ""}`} />
                    </Button>
                </div>
            </div>

            {/* Progress Card */}
            {(ingestionStatus === "ingesting" || ingestionStatus === "pending") && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5" />
                            Collecting Build Data
                        </CardTitle>
                        <CardDescription>
                            Cloning repositories, creating worktrees, and downloading build logs...
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Progress value={ingestionProgress} className="h-3" />
                        <p className="text-sm text-muted-foreground mt-2">{ingestionProgress}% complete</p>
                    </CardContent>
                </Card>
            )}

            {/* Stats Cards */}
            {stats && isIngested && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <StatCard icon={Database} label="Total Builds" value={stats.total_builds} variant="default" />
                    <StatCard icon={CheckCircle2} label="Found" value={stats.found_builds} variant="success" />
                    <StatCard icon={Clock} label="Avg Duration" value={stats.avg_duration_seconds ? formatDuration(stats.avg_duration_seconds) : "N/A"} variant="default" />
                    <StatCard icon={FileText} label="Logs Available" value={stats.logs_stats.available} variant={stats.logs_stats.available > 0 ? "success" : "warning"} />
                    <StatCard icon={AlertTriangle} label="Logs Expired" value={stats.logs_stats.expired} variant={stats.logs_stats.expired > 0 ? "error" : "default"} />
                </div>
            )}

            {/* Conclusion breakdown */}
            {stats && isIngested && Object.keys(stats.conclusion_breakdown).length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <GitCommit className="h-5 w-5" />
                            Build Results
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-3">
                            {Object.entries(stats.conclusion_breakdown).map(([conclusion, count]) => (
                                <div key={conclusion} className="flex items-center gap-2">
                                    <Badge variant={conclusion === "success" ? "default" : "secondary"}
                                        className={conclusion === "success" ? "bg-green-500" : conclusion === "failure" ? "bg-red-500" : ""}>
                                        {conclusion}
                                    </Badge>
                                    <span className="text-sm font-medium">{count}</span>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Builds per repo */}
            {stats && isIngested && stats.builds_per_repo.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <GitBranch className="h-5 w-5" />
                            Builds per Repository (Top 10)
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {stats.builds_per_repo.map((item) => (
                                <div key={item.repo} className="flex items-center justify-between">
                                    <span className="text-sm font-mono truncate max-w-[60%]">{item.repo}</span>
                                    <div className="flex items-center gap-2">
                                        <div className="w-32 h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(item.count / stats.builds_per_repo[0].count) * 100}%` }} />
                                        </div>
                                        <span className="text-sm font-medium w-12 text-right">{item.count}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Builds Table */}
            {isIngested && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <FolderGit2 className="h-5 w-5" />
                            Builds ({total} found)
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        {loadingBuilds ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : (
                            <>
                                <div className="overflow-x-auto">
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Build</TableHead>
                                                <TableHead>Repository</TableHead>
                                                <TableHead>Branch</TableHead>
                                                <TableHead>Commit</TableHead>
                                                <TableHead>Result</TableHead>
                                                <TableHead>Duration</TableHead>
                                                <TableHead>Logs</TableHead>
                                                <TableHead></TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {builds.length === 0 ? (
                                                <TableRow>
                                                    <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                                                        No builds found
                                                    </TableCell>
                                                </TableRow>
                                            ) : (
                                                builds.map((build) => (
                                                    <TableRow key={build.id}>
                                                        <TableCell className="font-mono text-xs">
                                                            #{build.build_number || build.build_id_from_csv}
                                                        </TableCell>
                                                        <TableCell className="font-mono text-xs max-w-[150px] truncate">
                                                            {build.repo_name_from_csv}
                                                        </TableCell>
                                                        <TableCell className="text-xs">{build.branch || "-"}</TableCell>
                                                        <TableCell className="font-mono text-xs">
                                                            {build.commit_sha?.slice(0, 7) || "-"}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Badge variant="secondary" className={
                                                                build.conclusion === "success" ? "bg-green-100 text-green-700" :
                                                                    build.conclusion === "failure" ? "bg-red-100 text-red-700" : ""
                                                            }>
                                                                {build.conclusion || "-"}
                                                            </Badge>
                                                        </TableCell>
                                                        <TableCell className="text-xs">
                                                            {build.duration_seconds ? formatDuration(build.duration_seconds) : "-"}
                                                        </TableCell>
                                                        <TableCell>
                                                            {build.logs_available ? (
                                                                <Button variant="ghost" size="sm" onClick={() => loadLogs(build)} className="h-7 px-2">
                                                                    <FileText className="h-3 w-3 mr-1 text-green-600" />
                                                                    View
                                                                </Button>
                                                            ) : build.logs_expired ? (
                                                                <Badge variant="secondary" className="bg-amber-100 text-amber-700">
                                                                    <AlertTriangle className="h-3 w-3 mr-1" />
                                                                    Expired
                                                                </Badge>
                                                            ) : (
                                                                <Badge variant="secondary">N/A</Badge>
                                                            )}
                                                        </TableCell>
                                                        <TableCell>
                                                            {build.web_url && (
                                                                <a href={build.web_url} target="_blank" rel="noopener noreferrer">
                                                                    <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                                                                </a>
                                                            )}
                                                        </TableCell>
                                                    </TableRow>
                                                ))
                                            )}
                                        </TableBody>
                                    </Table>
                                </div>

                                {total > pageSize && (
                                    <div className="flex items-center justify-between px-4 py-3 border-t">
                                        <span className="text-sm text-muted-foreground">
                                            {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} of {total}
                                        </span>
                                        <div className="flex gap-2">
                                            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
                                                <ChevronLeft className="h-4 w-4" />
                                            </Button>
                                            <Button variant="outline" size="sm" disabled={(page + 1) * pageSize >= total} onClick={() => setPage(p => p + 1)}>
                                                <ChevronRight className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Completion Message */}
            {ingestionStatus === "completed" && (
                <Alert className="border-green-200 bg-green-50 dark:bg-green-900/20">
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    <AlertDescription className="text-green-600">
                        Data collection is complete! You can now create enriched dataset versions
                        in the <strong>Enrichment</strong> tab.
                    </AlertDescription>
                </Alert>
            )}

            {/* Logs Viewer Dialog */}
            <Dialog open={logsDialogOpen} onOpenChange={setLogsDialogOpen}>
                <DialogContent className="max-w-4xl max-h-[85vh]">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <FileText className="h-5 w-5" />
                            Build Logs - #{selectedBuild?.build_number || selectedBuild?.build_id_from_csv}
                        </DialogTitle>
                        <DialogDescription>
                            {selectedBuild?.repo_name_from_csv} • {selectedBuild?.branch}
                        </DialogDescription>
                    </DialogHeader>

                    {loadingLogs ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : logs?.logs_expired ? (
                        <Alert variant="destructive">
                            <AlertTriangle className="h-4 w-4" />
                            <AlertDescription>
                                Build logs have expired and are no longer available.
                            </AlertDescription>
                        </Alert>
                    ) : !logs?.logs_available ? (
                        <Alert>
                            <AlertCircle className="h-4 w-4" />
                            <AlertDescription>
                                No logs available for this build.
                            </AlertDescription>
                        </Alert>
                    ) : logs?.logs && logs.logs.length > 0 ? (
                        <Tabs defaultValue={logs.logs[0].job_name} className="flex-1">
                            <TabsList className="flex flex-wrap h-auto gap-1">
                                {logs.logs.map((log) => (
                                    <TabsTrigger key={log.job_name} value={log.job_name} className="text-xs">
                                        {log.job_name}
                                        {log.size_bytes && (
                                            <span className="ml-1 text-muted-foreground">({formatBytes(log.size_bytes)})</span>
                                        )}
                                    </TabsTrigger>
                                ))}
                            </TabsList>
                            {logs.logs.map((log) => (
                                <TabsContent key={log.job_name} value={log.job_name} className="mt-4">
                                    <ScrollArea className="h-[50vh] rounded border bg-slate-950 p-4">
                                        <pre className="text-xs text-slate-100 font-mono whitespace-pre-wrap">
                                            {log.content || log.error || "No content"}
                                        </pre>
                                    </ScrollArea>
                                </TabsContent>
                            ))}
                        </Tabs>
                    ) : (
                        <p className="text-muted-foreground text-center py-8">No log files found.</p>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
