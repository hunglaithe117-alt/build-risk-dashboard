"use client";

import {
    CheckCircle2,
    Clock,
    GitCommit,
    Loader2,
    XCircle
} from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BuildDrawer } from "@/components/build-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi, reposApi } from "@/lib/api";
import { formatDurationFromSeconds, formatTimestamp } from "@/lib/utils";
import type { Build, RepoDetail } from "@/types";

const PAGE_SIZE = 20;



function StatusBadge({ status }: { status: string }) {
    switch (status.toLowerCase()) {
        case "completed":
        case "success":
            return (
                <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                    <CheckCircle2 className="h-3 w-3" /> Passed
                </Badge>
            );
        case "failed":
        case "failure":
            return (
                <Badge variant="destructive" className="gap-1">
                    <XCircle className="h-3 w-3" /> Failed
                </Badge>
            );
        case "in_progress":
        case "running":
            return (
                <Badge variant="default" className="bg-blue-500 hover:bg-blue-600 gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" /> Running
                </Badge>
            );
        case "queued":
        case "pending":
            return (
                <Badge variant="secondary" className="gap-1">
                    <Clock className="h-3 w-3" /> Pending
                </Badge>
            );
        default:
            return <Badge variant="secondary">{status}</Badge>;
    }
}

export default function RepoBuildsPage() {
    const params = useParams();
    const repoId = params.repoId as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [selectedBuildId, setSelectedBuildId] = useState<string | null>(null);

    const { subscribe } = useWebSocket();

    const loadRepo = useCallback(async () => {
        try {
            const data = await reposApi.get(repoId);
            setRepo(data);
        } catch (err) {
            console.error(err);
            setError("Unable to load repository details.");
        }
    }, [repoId]);

    const loadBuilds = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) {
                setTableLoading(true);
            }
            try {
                const data = await buildApi.getByRepo(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                });
                setBuilds(data.items);
                setTotal(data.total);
                setPage(pageNumber);
            } catch (err) {
                console.error(err);
                setError("Unable to load builds.");
            } finally {
                setLoading(false);
                setTableLoading(false);
            }
        },
        [repoId]
    );

    useEffect(() => {
        loadRepo();
        loadBuilds(1, true);
    }, [loadRepo, loadBuilds]);

    // WebSocket connection
    useEffect(() => {
        const unsubscribe = subscribe("BUILD_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                // If it's a new build or update, reload the list
                // Optimally we would update the list in place, but reloading is safer for now
                loadBuilds(page);
            }
        });

        return () => {
            unsubscribe();
        };
    }, [subscribe, loadBuilds, page, repoId]);

    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
    const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

    const handlePageChange = (direction: "prev" | "next") => {
        const targetPage =
            direction === "prev"
                ? Math.max(1, page - 1)
                : Math.min(totalPages, page + 1);
        if (targetPage !== page) {
            void loadBuilds(targetPage, true);
        }
    };

    if (loading && !repo) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">
                        {repo?.full_name || "Repository Builds"}
                    </h1>
                    <p className="text-muted-foreground">
                        View and analyze build history.
                    </p>
                </div>
            </div>

            {error ? (
                <Card className="border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
                    <CardHeader>
                        <CardTitle className="text-red-700 dark:text-red-300">
                            Error
                        </CardTitle>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                </Card>
            ) : null}

            <Card>
                <CardHeader>
                    <CardTitle>Build History</CardTitle>
                    <CardDescription>
                        List of all recorded workflow runs.
                    </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Build #
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Status
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Commit
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Date
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Duration
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Tests
                                    </th>
                                    <th className="px-6 py-3" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {builds.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={7}
                                            className="px-6 py-6 text-center text-sm text-muted-foreground"
                                        >
                                            No builds recorded yet.
                                        </td>
                                    </tr>
                                ) : (
                                    builds.map((build) => (
                                        <tr
                                            key={build.id}
                                            className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                            onClick={() => setSelectedBuildId(build.id)}
                                        >
                                            <td className="px-6 py-4 font-medium">
                                                #{build.build_number}
                                            </td>
                                            <td className="px-6 py-4">
                                                <StatusBadge status={build.status} />
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-1 font-mono text-xs">
                                                    <GitCommit className="h-3 w-3" />
                                                    {build.commit_sha.substring(0, 7)}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {formatTimestamp(build.created_at)}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {formatDurationFromSeconds(build.duration)}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {build.num_tests !== null ? build.num_tests : "—"}
                                            </td>
                                            <td className="px-6 py-4">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setSelectedBuildId(build.id);
                                                    }}
                                                >
                                                    View
                                                </Button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
                <div className="flex flex-col gap-3 border-t border-slate-200 px-6 py-4 text-sm text-muted-foreground dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        {total > 0
                            ? `Showing ${pageStart}-${pageEnd} of ${total} builds`
                            : "No builds to display"}
                    </div>
                    <div className="flex items-center gap-3">
                        {tableLoading ? (
                            <div className="flex items-center gap-2">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-xs">Refreshing...</span>
                            </div>
                        ) : null}
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
            </Card>

            <BuildDrawer
                repoId={repoId}
                buildId={selectedBuildId}
                onClose={() => setSelectedBuildId(null)}
            />
        </div>
    );
}
