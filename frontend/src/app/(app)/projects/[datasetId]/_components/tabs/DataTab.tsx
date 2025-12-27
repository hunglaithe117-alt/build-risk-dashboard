"use client";

import { useEffect, useState, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
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
import { api } from "@/lib/api";
import type { DatasetRecord } from "@/types";
import {
    ChevronLeft,
    ChevronRight,
    ExternalLink,
    FolderGit2,
    Loader2,
    RefreshCw,
    AlertTriangle,
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
    logs_available?: boolean;
    logs_expired?: boolean;
    web_url?: string;
}

function formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

export function DataTab({ datasetId, dataset, onRefresh }: DataTabProps) {
    const [builds, setBuilds] = useState<BuildItem[]>([]);
    const [loadingBuilds, setLoadingBuilds] = useState(false);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    const isValidated = dataset.validation_status === "completed";

    // Load builds
    const loadBuilds = useCallback(async () => {
        if (!isValidated) return;
        setLoadingBuilds(true);
        try {
            const buildsRes = await api.get<{ items: BuildItem[]; total: number }>(`/datasets/${datasetId}/builds?skip=${page * pageSize}&limit=${pageSize}&status_filter=found`);
            setBuilds(buildsRes.data.items);
            setTotal(buildsRes.data.total);
        } catch (err) {
            console.error("Failed to load builds:", err);
        } finally {
            setLoadingBuilds(false);
        }
    }, [datasetId, page, isValidated]);

    // Initial load
    useEffect(() => {
        if (isValidated) {
            loadBuilds();
        }
    }, [isValidated, loadBuilds]);

    if (!isValidated) {
        return (
            <div className="flex flex-col items-center justify-center py-12 border rounded-lg border-dashed bg-slate-50 dark:bg-slate-900/50">
                <AlertTriangle className="h-10 w-10 text-amber-500 mb-4" />
                <h3 className="text-lg font-semibold">Validation Required</h3>
                <p className="text-sm text-muted-foreground text-center max-w-sm mt-2">
                    Dataset validation must be completed to view validated build details.
                    Please check your configuration or wait for the background validation to finish.
                </p>
            </div>
        );
    }

    return (
        <Card>
            <CardHeader className="border-b px-4 py-3 flex flex-row items-center justify-between">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                    <FolderGit2 className="h-4 w-4" />
                    Build List
                </CardTitle>
                <Button variant="ghost" size="sm" onClick={() => { onRefresh(); loadBuilds(); }} className="h-8 w-8 p-0">
                    <RefreshCw className={`h-4 w-4 ${loadingBuilds ? "animate-spin" : ""}`} />
                </Button>
            </CardHeader>
            <CardContent className="p-0">
                {loadingBuilds ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <div className="flex flex-col">
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow className="hover:bg-transparent">
                                        <TableHead>Build ID</TableHead>
                                        <TableHead>Repository</TableHead>
                                        <TableHead>Ref</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Duration</TableHead>
                                        <TableHead className="w-[50px]"></TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {builds.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                                                No builds found
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        builds.map((build) => (
                                            <TableRow key={build.id}>
                                                <TableCell className="font-mono text-xs">
                                                    #{build.build_number || build.build_id_from_csv}
                                                </TableCell>
                                                <TableCell className="max-w-[200px]">
                                                    <div className="flex flex-col">
                                                        <span className="font-mono text-xs truncate" title={build.repo_name_from_csv}>{build.repo_name_from_csv}</span>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex flex-col gap-0.5 max-w-[150px]">
                                                        <span className="text-xs truncate font-medium">{build.branch || "HEAD"}</span>
                                                        {build.commit_sha && (
                                                            <span className="text-[10px] font-mono text-muted-foreground truncate">{build.commit_sha.slice(0, 7)}</span>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="secondary" className={`text-[10px] px-1.5 ${build.conclusion === "success" ? "bg-green-50 text-green-700 border-green-200" :
                                                            build.conclusion === "failure" ? "bg-red-50 text-red-700 border-red-200" : ""
                                                        }`}>
                                                        {build.conclusion || build.status}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="text-xs text-muted-foreground">
                                                    {build.duration_seconds ? formatDuration(build.duration_seconds) : "-"}
                                                </TableCell>
                                                <TableCell>
                                                    {build.web_url && (
                                                        <a href={build.web_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center p-2 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                                                            <ExternalLink className="h-4 w-4 text-slate-500" />
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
                            <div className="flex items-center justify-between px-4 py-3 border-t bg-slate-50/50 dark:bg-slate-900/50">
                                <span className="text-xs text-muted-foreground">
                                    Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} of {total}
                                </span>
                                <div className="flex gap-2">
                                    <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)} className="h-7 w-7 p-0">
                                        <ChevronLeft className="h-4 w-4" />
                                    </Button>
                                    <Button variant="outline" size="sm" disabled={(page + 1) * pageSize >= total} onClick={() => setPage(p => p + 1)} className="h-7 w-7 p-0">
                                        <ChevronRight className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
