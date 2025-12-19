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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { buildApi } from "@/lib/api";
import type { Build, BuildListResponse } from "@/types";
import {
    ArrowLeft,
    CheckCircle2,
    AlertCircle,
    Clock,
    FolderGit2,
    GitCommit,
    Loader2,
    XCircle,
    FileText,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";

interface DatasetRepo {
    id: string;
    raw_repo_id: string | null;
    repo_name: string;
    full_name: string;
    validation_status: string;
    validation_error?: string;
    builds_in_csv: number;
    builds_found: number;
    builds_processed: number;
}

interface DatasetReposResponse {
    items: DatasetRepo[];
    total: number;
}

interface RepoBuildsViewProps {
    datasetId: string;
    isIngested: boolean;
}

function ValidationStatusBadge({ status }: { status: string }) {
    if (status === "valid") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Valid
            </Badge>
        );
    }
    if (status === "invalid" || status === "not_found") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> {status === "not_found" ? "Not Found" : "Invalid"}
            </Badge>
        );
    }
    if (status === "pending") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Pending
            </Badge>
        );
    }
    return <Badge variant="secondary">{status}</Badge>;
}

function BuildStatusBadge({ conclusion }: { conclusion: string }) {
    const c = conclusion.toLowerCase();
    if (c === "success" || c === "passed") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Passed
            </Badge>
        );
    }
    if (c === "failure" || c === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }
    return <Badge variant="secondary">{conclusion}</Badge>;
}

function ExtractionBadge({ hasTrainingData, status }: { hasTrainingData: boolean; status?: string }) {
    if (!hasTrainingData) {
        return (
            <Badge variant="outline" className="border-slate-400 text-slate-500 gap-1">
                <Clock className="h-3 w-3" /> Not Started
            </Badge>
        );
    }
    if (status === "completed") {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Done
            </Badge>
        );
    }
    if (status === "pending") {
        return (
            <Badge variant="secondary" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> Processing
            </Badge>
        );
    }
    if (status === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }
    return <Badge variant="secondary">{status}</Badge>;
}

export function RepoBuildsView({ datasetId, isIngested }: RepoBuildsViewProps) {
    const [repos, setRepos] = useState<DatasetRepo[]>([]);
    const [loadingRepos, setLoadingRepos] = useState(false);

    // Drill-down state
    const [selectedRepo, setSelectedRepo] = useState<DatasetRepo | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loadingBuilds, setLoadingBuilds] = useState(false);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const pageSize = 20;

    // Load repos list
    const loadRepos = useCallback(async () => {
        setLoadingRepos(true);
        try {
            const res = await api.get<DatasetReposResponse>(`/datasets/${datasetId}/repos`);
            setRepos(res.data.items);
        } catch (err) {
            console.error("Failed to load repos:", err);
        } finally {
            setLoadingRepos(false);
        }
    }, [datasetId]);

    // Load builds for selected repo
    const loadBuilds = useCallback(async () => {
        if (!selectedRepo?.raw_repo_id) return;
        setLoadingBuilds(true);
        try {
            const res = await buildApi.getByRepo(selectedRepo.raw_repo_id, {
                skip: page * pageSize,
                limit: pageSize,
            });
            setBuilds(res.items);
            setTotal(res.total);
        } catch (err) {
            console.error("Failed to load builds:", err);
        } finally {
            setLoadingBuilds(false);
        }
    }, [selectedRepo, page]);

    useEffect(() => {
        loadRepos();
    }, [loadRepos]);

    useEffect(() => {
        if (selectedRepo) {
            loadBuilds();
        }
    }, [selectedRepo, loadBuilds]);

    const handleRepoClick = (repo: DatasetRepo) => {
        if (repo.raw_repo_id && isIngested) {
            setSelectedRepo(repo);
            setPage(0);
        }
    };

    const handleBack = () => {
        setSelectedRepo(null);
        setBuilds([]);
        setPage(0);
        setTotal(0);
    };

    // Builds view
    if (selectedRepo) {
        const totalPages = Math.ceil(total / pageSize);
        return (
            <Card>
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <Button variant="ghost" size="icon" onClick={handleBack}>
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <FolderGit2 className="h-5 w-5" />
                                {selectedRepo.repo_name}
                            </CardTitle>
                            <CardDescription>
                                {total} builds found
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    {loadingBuilds ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : builds.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground">
                            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p>No builds found for this repository.</p>
                            <p className="text-sm">Run ingestion to collect build data.</p>
                        </div>
                    ) : (
                        <>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Build #</TableHead>
                                        <TableHead>CI ID</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Commit</TableHead>
                                        <TableHead>Branch</TableHead>
                                        <TableHead>Extraction</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {builds.map((build) => (
                                        <TableRow key={build.id}>
                                            <TableCell className="font-medium">
                                                #{build.build_number || "—"}
                                            </TableCell>
                                            <TableCell className="font-mono text-xs">
                                                {build.build_id}
                                            </TableCell>
                                            <TableCell>
                                                <BuildStatusBadge conclusion={build.conclusion} />
                                            </TableCell>
                                            <TableCell className="font-mono text-xs">
                                                <div className="flex items-center gap-1">
                                                    <GitCommit className="h-3 w-3" />
                                                    {build.commit_sha.substring(0, 7)}
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-xs">
                                                {build.branch}
                                            </TableCell>
                                            <TableCell>
                                                <ExtractionBadge
                                                    hasTrainingData={build.has_training_data}
                                                    status={build.extraction_status}
                                                />
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between px-4 py-3 border-t">
                                    <span className="text-sm text-muted-foreground">
                                        Page {page + 1} of {totalPages}
                                    </span>
                                    <div className="flex gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            disabled={page === 0}
                                            onClick={() => setPage(p => p - 1)}
                                        >
                                            <ChevronLeft className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            disabled={page >= totalPages - 1}
                                            onClick={() => setPage(p => p + 1)}
                                        >
                                            <ChevronRight className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </CardContent>
            </Card>
        );
    }

    // Repos list view (default)
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <FolderGit2 className="h-5 w-5" />
                    Repositories in Dataset
                </CardTitle>
                <CardDescription>
                    Click on a repository to view its builds
                </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
                {loadingRepos ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : repos.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                        <FolderGit2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>No repositories found.</p>
                        <p className="text-sm">Complete validation to discover repositories.</p>
                    </div>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Repository</TableHead>
                                <TableHead>Validation</TableHead>
                                <TableHead>Builds in CSV</TableHead>
                                <TableHead>Builds Found</TableHead>
                                <TableHead>Processed</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {repos.map((repo) => (
                                <TableRow
                                    key={repo.id}
                                    className={repo.raw_repo_id && isIngested ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-900/40" : ""}
                                    onClick={() => handleRepoClick(repo)}
                                >
                                    <TableCell className="font-mono text-sm">
                                        <div className="flex items-center gap-2">
                                            <FolderGit2 className="h-4 w-4 text-muted-foreground" />
                                            {repo.repo_name}
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <ValidationStatusBadge status={repo.validation_status} />
                                    </TableCell>
                                    <TableCell>{repo.builds_in_csv}</TableCell>
                                    <TableCell>{repo.builds_found}</TableCell>
                                    <TableCell>{repo.builds_processed}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
            </CardContent>
        </Card>
    );
}
