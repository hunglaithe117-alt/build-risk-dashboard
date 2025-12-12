"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
    AlertTriangle,
    CheckCircle2,
    Clock,
    FileDiff,
    GitCommit,
    LayoutList,
    Loader2,
    X,
    XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buildApi } from "@/lib/api";
import type { BuildDetail } from "@/types";

const Portal = ({ children }: { children: React.ReactNode }) => {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) return null;
    return createPortal(children, document.body);
};

export enum BuildStatus {
    SUCCESS = "success",
    PASSED = "passed",
    FAILURE = "failure",
    CANCELLED = "cancelled",
    SKIPPED = "skipped",
    TIMED_OUT = "timed_out",
    NEUTRAL = "neutral",
    ACTION_REQUIRED = "action_required",
    STARTUP_FAILURE = "startup_failure",
    STALE = "stale",
    QUEUED = "queued",
    UNKNOWN = "unknown",
}

export enum ExtractionStatus {
    PENDING = "pending",
    COMPLETED = "completed",
    PARTIAL = "partial",
    FAILED = "failed",
    UNKNOWN = "unknown",
}

function StatusBadge({ status }: { status: string }) {
    const normalizedStatus = status.toLowerCase();

    // Success / Passed
    if (normalizedStatus === BuildStatus.SUCCESS || normalizedStatus === BuildStatus.PASSED) {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Passed
            </Badge>
        );
    }

    // Failure
    if (normalizedStatus === BuildStatus.FAILURE || normalizedStatus === "failed") {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }

    // Cancelled
    if ([BuildStatus.CANCELLED, "canceled"].includes(normalizedStatus as BuildStatus)) {
        return (
            <Badge variant="secondary" className="gap-1">
                <XCircle className="h-3 w-3" /> Cancelled
            </Badge>
        );
    }

    // Skipped
    if (normalizedStatus === BuildStatus.SKIPPED) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Skipped
            </Badge>
        );
    }

    // Timed out
    if (normalizedStatus === BuildStatus.TIMED_OUT) {
        return (
            <Badge variant="destructive" className="gap-1">
                <Clock className="h-3 w-3" /> Timed Out
            </Badge>
        );
    }

    // Neutral
    if (normalizedStatus === BuildStatus.NEUTRAL) {
        return (
            <Badge variant="secondary" className="gap-1">
                <CheckCircle2 className="h-3 w-3" /> Neutral
            </Badge>
        );
    }

    // Action Required
    if (normalizedStatus === BuildStatus.ACTION_REQUIRED) {
        return (
            <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                <AlertTriangle className="h-3 w-3" /> Action Required
            </Badge>
        );
    }

    // Startup Failure
    if (normalizedStatus === BuildStatus.STARTUP_FAILURE) {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Startup Failed
            </Badge>
        );
    }

    // Stale
    if (normalizedStatus === BuildStatus.STALE) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Stale
            </Badge>
        );
    }

    // Queued
    if (normalizedStatus === BuildStatus.QUEUED) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Queued
            </Badge>
        );
    }

    // Unknown
    if (normalizedStatus === BuildStatus.UNKNOWN) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Unknown
            </Badge>
        );
    }

    // Default fallback
    return (
        <Badge variant="secondary" className="gap-1">
            <Clock className="h-3 w-3" /> {status}
        </Badge>
    );
}

function ExtractionStatusBadge({ status }: { status: string }) {
    const normalizedStatus = status.toLowerCase();

    if (normalizedStatus === ExtractionStatus.COMPLETED) {
        return (
            <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle2 className="h-3 w-3" /> Done
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.PARTIAL) {
        return (
            <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                <AlertTriangle className="h-3 w-3" /> Partial
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.FAILED) {
        return (
            <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Failed
            </Badge>
        );
    }

    if (normalizedStatus === ExtractionStatus.PENDING) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" /> Pending
            </Badge>
        );
    }

    return (
        <Badge variant="secondary" className="text-xs">{status}</Badge>
    );
}


interface BuildDrawerProps {
    repoId: string;
    buildId: string | null;
    onClose: () => void;
}

export function BuildDrawer({ repoId, buildId, onClose }: BuildDrawerProps) {
    const [build, setBuild] = useState<BuildDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!buildId) {
            setBuild(null);
            return;
        }

        const loadBuild = async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await buildApi.getById(repoId, buildId);
                setBuild(data);
            } catch (err) {
                console.error(err);
                setError("Unable to load build details.");
            } finally {
                setLoading(false);
            }
        };

        loadBuild();
    }, [repoId, buildId]);

    if (!buildId) return null;

    // Helper to get feature value with fallback
    const f = build?.features || {};
    // Type-safe helper to extract feature values as renderable types
    const feat = (key: string): string | number | null => {
        const value = f[key];
        if (value === null || value === undefined) return null;
        if (typeof value === 'string' || typeof value === 'number') return value;
        return String(value);
    };

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm transition-all duration-300">
                <div
                    className="h-full w-full max-w-2xl transform bg-white shadow-2xl transition-transform duration-300 dark:bg-slate-950"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="flex h-full flex-col">
                        {/* Header */}
                        <div className="flex items-center justify-between border-b px-6 py-4">
                            <div>
                                <h2 className="text-lg font-semibold">Build Details</h2>
                                <p className="text-sm text-muted-foreground">
                                    ID: {buildId}
                                </p>
                            </div>
                            <Button variant="ghost" size="icon" onClick={onClose}>
                                <X className="h-5 w-5" />
                            </Button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-6">
                            {loading ? (
                                <div className="flex h-40 items-center justify-center">
                                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                </div>
                            ) : error ? (
                                <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-200">
                                    <div className="flex items-center gap-2">
                                        <AlertTriangle className="h-5 w-5" />
                                        <p className="font-medium">Error loading build</p>
                                    </div>
                                    <p className="mt-1 text-sm">{error}</p>
                                </div>
                            ) : build ? (
                                <div className="space-y-8">
                                    {/* Overview */}
                                    <section className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h3 className="text-2xl font-bold">
                                                    Build #{build.build_number}
                                                </h3>
                                                <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                                                    <GitCommit className="h-4 w-4" />
                                                    <span className="font-mono">{build.commit_sha.substring(0, 7)}</span>
                                                </div>
                                            </div>
                                            <StatusBadge status={build.build_conclusion} />
                                        </div>

                                        <div className="grid grid-cols-2 gap-4 rounded-lg border p-4 sm:grid-cols-4">
                                            <div>
                                                <p className="text-xs text-muted-foreground">Workflow ID</p>
                                                <p className="font-medium font-mono text-xs mt-1">
                                                    {build.workflow_run_id}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Duration</p>
                                                <p className="font-medium">
                                                    {build.duration ? `${build.duration.toFixed(1)}s` : "—"}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Jobs</p>
                                                <p className="font-medium">{build.num_jobs ?? feat("tr_log_num_jobs") ?? "—"}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Tests</p>
                                                <p className="font-medium">{build.num_tests ?? feat("tr_log_tests_run_sum") ?? "—"}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Repo Age</p>
                                                <p className="font-medium">
                                                    {feat("gh_repo_age") ? `${Number(feat("gh_repo_age")).toFixed(0)} days` : "—"}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Total Commits</p>
                                                <p className="font-medium">
                                                    {feat("gh_repo_num_commits") ?? "—"}
                                                </p>
                                            </div>
                                        </div>
                                    </section>

                                    {/* Git Diff Features */}
                                    <section>
                                        <h4 className="mb-3 flex items-center gap-2 font-semibold">
                                            <FileDiff className="h-4 w-4" /> Code Changes
                                        </h4>
                                        <div className="grid gap-4 sm:grid-cols-2">
                                            <div className="rounded-lg border p-4">
                                                <p className="text-sm font-medium text-muted-foreground">
                                                    File Changes
                                                </p>
                                                <div className="mt-2 space-y-1">
                                                    <div className="flex justify-between text-sm">
                                                        <span>Added</span>
                                                        <span className="font-mono text-green-600">
                                                            +{feat("gh_diff_files_added") ?? 0}
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span>Modified</span>
                                                        <span className="font-mono text-blue-600">
                                                            ~{feat("gh_diff_files_modified") ?? 0}
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span>Deleted</span>
                                                        <span className="font-mono text-red-600">
                                                            -{feat("gh_diff_files_deleted") ?? 0}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="rounded-lg border p-4">
                                                <p className="text-sm font-medium text-muted-foreground">
                                                    Test Changes
                                                </p>
                                                <div className="mt-2 space-y-1">
                                                    <div className="flex justify-between text-sm">
                                                        <span>Tests Added</span>
                                                        <span className="font-mono text-green-600">
                                                            +{feat("gh_diff_tests_added") ?? 0}
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span>Tests Deleted</span>
                                                        <span className="font-mono text-red-600">
                                                            -{feat("gh_diff_tests_deleted") ?? 0}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </section>

                                    {/* Git & Team Metrics */}
                                    <section>
                                        <h4 className="mb-3 flex items-center gap-2 font-semibold">
                                            <GitCommit className="h-4 w-4" /> Git & Team Metrics
                                        </h4>
                                        <div className="grid gap-4 sm:grid-cols-2">
                                            <div className="rounded-lg border p-4">
                                                <p className="text-sm font-medium text-muted-foreground">
                                                    Team Context
                                                </p>
                                                <div className="mt-2 space-y-2 text-sm">
                                                    <div className="flex justify-between">
                                                        <span>Team Size (3m)</span>
                                                        <span className="font-medium">{feat("gh_team_size") ?? "—"}</span>
                                                    </div>
                                                    <div className="flex justify-between">
                                                        <span>Core Member</span>
                                                        <span className="font-medium">
                                                            {feat("gh_by_core_team_member") === "true" || feat("gh_by_core_team_member") === 1
                                                                ? "Yes"
                                                                : feat("gh_by_core_team_member") === "false" || feat("gh_by_core_team_member") === 0
                                                                    ? "No"
                                                                    : "—"}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="rounded-lg border p-4">
                                                <p className="text-sm font-medium text-muted-foreground">
                                                    Commit History
                                                </p>
                                                <div className="mt-2 space-y-2 text-sm">
                                                    <div className="flex justify-between">
                                                        <span>Commits in Build</span>
                                                        <span className="font-medium">
                                                            {feat("git_num_all_built_commits") ?? "—"}
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between">
                                                        <span>Prev Build ID</span>
                                                        <span className="font-medium">
                                                            {feat("tr_prev_build") ? `#${feat("tr_prev_build")}` : "—"}
                                                        </span>
                                                    </div>
                                                    <div className="flex justify-between">
                                                        <span>Prev Resolution</span>
                                                        <span className="font-medium text-xs">
                                                            {feat("git_prev_commit_resolution_status") ?? "—"}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="col-span-2 rounded-lg border p-4">
                                                <div className="flex justify-between text-sm">
                                                    <span className="text-muted-foreground">Commits on touched files (3m)</span>
                                                    <span className="font-medium">
                                                        {feat("gh_num_commits_on_files_touched") ?? "—"}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    </section>

                                    {/* Churn Metrics */}
                                    <section>
                                        <h4 className="mb-3 flex items-center gap-2 font-semibold">
                                            <LayoutList className="h-4 w-4" /> Churn Metrics
                                        </h4>
                                        <div className="grid gap-4 sm:grid-cols-3">
                                            <div className="rounded-lg border bg-slate-50 p-3 dark:bg-slate-900/50">
                                                <p className="text-xs text-muted-foreground">Source Churn</p>
                                                <p className="text-lg font-semibold">
                                                    {feat("git_diff_src_churn") ?? 0}
                                                </p>
                                            </div>
                                            <div className="rounded-lg border bg-slate-50 p-3 dark:bg-slate-900/50">
                                                <p className="text-xs text-muted-foreground">Test Churn</p>
                                                <p className="text-lg font-semibold">
                                                    {feat("git_diff_test_churn") ?? 0}
                                                </p>
                                            </div>
                                            <div className="rounded-lg border bg-slate-50 p-3 dark:bg-slate-900/50">
                                                <p className="text-xs text-muted-foreground">SLOC</p>
                                                <p className="text-lg font-semibold">
                                                    {feat("gh_sloc") ? Number(feat("gh_sloc")).toLocaleString() : "—"}
                                                </p>
                                            </div>
                                        </div>
                                    </section>

                                    {/* Error Message */}
                                    {build.error_message ? (
                                        <section className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-900/20">
                                            <h4 className="mb-2 flex items-center gap-2 font-semibold text-red-800 dark:text-red-200">
                                                <AlertTriangle className="h-4 w-4" /> Error Log
                                            </h4>
                                            <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-white p-2 text-xs font-mono text-red-700 dark:bg-black/20 dark:text-red-300">
                                                {build.error_message}
                                            </pre>
                                        </section>
                                    ) : null}
                                </div>
                            ) : null}
                        </div>
                    </div>
                </div>
            </div>
        </Portal>
    );
}
