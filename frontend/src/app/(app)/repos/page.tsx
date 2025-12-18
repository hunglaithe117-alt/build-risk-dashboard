"use client";

import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { reposApi } from "@/lib/api";
import type { RepositoryRecord } from "@/types";

function formatTimestamp(value?: string) {
    if (!value) return "—";
    try {
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(value));
    } catch {
        return value;
    }
}

const PAGE_SIZE = 20;

export default function UserReposPage() {
    const router = useRouter();

    const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [tableLoading, setTableLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearchQuery = useDebounce(searchQuery, 500);

    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);

    const loadRepositories = useCallback(
        async (pageNumber = 1, withSpinner = false) => {
            if (withSpinner) setTableLoading(true);
            try {
                const data = await reposApi.list({
                    skip: (pageNumber - 1) * PAGE_SIZE,
                    limit: PAGE_SIZE,
                    q: debouncedSearchQuery || undefined,
                });
                setRepositories(data.items);
                setTotal(data.total);
                setPage(pageNumber);
                setError(null);
            } catch (err) {
                console.error(err);
                setError("Unable to load repositories.");
            } finally {
                setLoading(false);
                setTableLoading(false);
            }
        },
        [debouncedSearchQuery]
    );

    useEffect(() => {
        loadRepositories(1, true);
    }, [loadRepositories]);

    const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
    const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

    const handlePageChange = (direction: "prev" | "next") => {
        const targetPage =
            direction === "prev"
                ? Math.max(1, page - 1)
                : Math.min(totalPages, page + 1);
        if (targetPage !== page) {
            void loadRepositories(targetPage, true);
        }
    };

    if (loading) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <CardTitle>Loading repositories...</CardTitle>
                        <CardDescription>Fetching your accessible repositories.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </CardContent>
                </Card>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Card className="w-full max-w-md border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
                    <CardHeader>
                        <CardTitle className="text-red-700 dark:text-red-300">
                            Unable to load data
                        </CardTitle>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <Card>
                <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                        <CardTitle>My Repositories</CardTitle>
                        <CardDescription>
                            Repositories you have access to on GitHub
                        </CardDescription>
                    </div>
                    <div className="w-64">
                        <Input
                            placeholder="Search repositories..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="h-9"
                        />
                    </div>
                </CardHeader>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Repository List</CardTitle>
                    <CardDescription>
                        Click on a repository to view its builds
                    </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                            <thead className="bg-slate-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Repository
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Status
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Last Sync
                                    </th>
                                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                                        Total Builds
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {repositories.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={4}
                                            className="px-6 py-8 text-center text-sm text-muted-foreground"
                                        >
                                            No repositories available.
                                        </td>
                                    </tr>
                                ) : (
                                    repositories.map((repo) => (
                                        <tr
                                            key={repo.id}
                                            className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                            onClick={() => router.push(`/repos/${repo.id}/builds`)}
                                        >
                                            <td className="px-6 py-4 font-medium text-foreground">
                                                {repo.full_name}
                                            </td>
                                            <td className="px-6 py-4">
                                                {repo.import_status === "imported" ? (
                                                    <Badge variant="outline" className="border-green-500 text-green-600">
                                                        Ready
                                                    </Badge>
                                                ) : repo.import_status === "importing" ? (
                                                    <Badge variant="default" className="bg-blue-500">
                                                        <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                                                        Syncing
                                                    </Badge>
                                                ) : (
                                                    <Badge variant="secondary">{repo.import_status}</Badge>
                                                )}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {formatTimestamp(repo.last_scanned_at)}
                                            </td>
                                            <td className="px-6 py-4 text-muted-foreground">
                                                {repo.total_builds_imported.toLocaleString()}
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
                            ? `Showing ${pageStart}-${pageEnd} of ${total} repositories`
                            : "No repositories to display"}
                    </div>
                    <div className="flex items-center gap-2">
                        {tableLoading && (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        )}
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePageChange("prev")}
                            disabled={page === 1 || tableLoading}
                        >
                            Previous
                        </Button>
                        <span className="text-xs">
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
            </Card>
        </div>
    );
}
