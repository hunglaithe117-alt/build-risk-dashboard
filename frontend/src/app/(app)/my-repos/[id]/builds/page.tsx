"use client";

import {
    ArrowLeft,
    CheckCircle2,
    Clock,
    GitCommit,
    Loader2,
    XCircle,
    AlertCircle,
    Globe,
    Lock,
    GitBranch,
    ExternalLink,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { useParams, useRouter } from "next/navigation";
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
import { buildApi, reposApi } from "@/lib/api";
import { formatTimestamp } from "@/lib/utils";
import type { Build, RepoDetail } from "@/types";

const PAGE_SIZE = 20;

function StatusBadge({ status }: { status: string }) {
    const s = status.toLowerCase();
    if (s === "success" || s === "passed") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Passed
            </Badge>
        );
    }
    if (s === "failure" || s === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }
    return <Badge variant="secondary">{status}</Badge>;
}

function ExtractionStatusBadge({ status, hasTrainingData }: { status?: string; hasTrainingData: boolean }) {
    if (!hasTrainingData) {
        return (
            <Badge variant="outline" className="border-slate-400 text-slate-500 gap-1">
                <Clock className="h-3 w-3" /> Not Started
            </Badge>
        );
    }
    const s = (status || "").toLowerCase();
    if (s === "completed") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Done
            </Badge>
        );
    }
    if (s === "pending") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> Processing
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
    return <Badge variant="secondary">{status || "Unknown"}</Badge>;
}

export default function UserBuildsPage() {
    const params = useParams();
    const router = useRouter();
    const repoId = params.id as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);

    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearchQuery = useDebounce(searchQuery, 500);

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
            if (withSpinner) setTableLoading(true);
            try {
                const data = await buildApi.getByRepo(repoId, {
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: debouncedSearchQuery || undefined,
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
        [repoId, debouncedSearchQuery]
    );

    useEffect(() => {
        loadRepo();
        loadBuilds(1, true);
    }, [loadRepo, loadBuilds]);

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
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push("/repos")}
                        className="gap-2"
                    >
                        <ArrowLeft className="h-4 w-4" />
                        Back to Repos
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">
                            {repo?.full_name || "Repository Builds"}
                        </h1>
                        <p className="text-muted-foreground">
                            View build history and details
                        </p>
                    </div>
                </div>
                <div className="w-64">
                    <Input
                        placeholder="Search builds..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="h-9"
                    />
                </div>
            </div>

            {error && (
                <Card className="border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
                    <CardHeader>
                        <CardTitle className="text-red-700 dark:text-red-300">Error</CardTitle>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                </Card>
            )}

            {repo && (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <CardTitle className="text-lg">{repo.full_name}</CardTitle>
                                <Badge variant={repo.is_private ? "secondary" : "outline"} className="gap-1">
                                    {repo.is_private ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                                    {repo.is_private ? "Private" : "Public"}
                                </Badge>
                            </div>
                            {repo.metadata?.html_url && (
                                <a
                                    href={repo.metadata.html_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                                >
                                    <ExternalLink className="h-4 w-4" />
                                    View on GitHub
                                </a>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-6 text-sm">
                            <div className="flex items-center gap-2">
                                <GitBranch className="h-4 w-4 text-muted-foreground" />
                                <span className="text-muted-foreground">Branch:</span>
                                <span className="font-medium">{repo.default_branch || "main"}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Total builds:</span>
                                <span className="font-medium">{repo.total_builds_imported.toLocaleString()}</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader>
                    <CardTitle>Build History</CardTitle>
                    <CardDescription>Click a build to view details and extracted features</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Build #</th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Status</th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Commit</th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Branch</th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Date</th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">Features</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {builds.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="px-6 py-6 text-center text-muted-foreground">
                                            No builds recorded yet.
                                        </td>
                                    </tr>
                                ) : (
                                    builds.map((build) => (
                                        <tr
                                            key={build.id}
                                            className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                            onClick={() => router.push(`/repos/${repoId}/builds/${build.id}`)}
                                        >
                                            <td className="px-6 py-4 font-medium">#{build.build_number || "—"}</td>
                                            <td className="px-6 py-4">
                                                <StatusBadge status={build.conclusion} />
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-1 font-mono text-xs">
                                                    <GitCommit className="h-3 w-3" />
                                                    {build.commit_sha.substring(0, 7)}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground text-xs">{build.branch}</td>
                                            <td className="px-6 py-4 text-muted-foreground">{formatTimestamp(build.created_at)}</td>
                                            <td className="px-6 py-4">
                                                <ExtractionStatusBadge status={build.extraction_status} hasTrainingData={build.has_training_data} />
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
                <div className="flex items-center justify-between border-t px-6 py-4 text-sm text-muted-foreground">
                    <div>
                        {total > 0 ? `Showing ${pageStart}-${pageEnd} of ${total} builds` : "No builds"}
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
                        <span className="text-xs">Page {page} of {totalPages}</span>
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
            </Card>
        </div>
    );
}
