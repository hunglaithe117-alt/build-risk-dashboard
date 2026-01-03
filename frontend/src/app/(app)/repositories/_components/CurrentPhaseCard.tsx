"use client";

import { AlertCircle, CheckCircle2, Clock, Loader2, RotateCcw, XCircle, SkipForward } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Resource status from FeatureResource enum values
type ResourceStatusCounts = Record<string, number>;

interface ResourceStatus {
    git_history?: ResourceStatusCounts;
    git_worktree?: ResourceStatusCounts;
    build_logs?: ResourceStatusCounts;
}

interface ImportProgress {
    checkpoint?: {
        has_checkpoint: boolean;
        last_checkpoint_at: string | null;
        accepted_failed: number;
        stats: Record<string, number>;
        current_processing_build_number?: number | null;
    };
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
        total: number;
    };
    resource_status?: ResourceStatus;
    training_builds: {
        pending: number;
        completed: number;
        partial: number;
        failed: number;
        total: number;
        with_prediction?: number;
        pending_prediction?: number;
        prediction_failed?: number;
    };
}

interface CurrentPhaseCardProps {
    status: string;
    progress: ImportProgress | null;
    isLoading: boolean;
    onRetryFailed?: () => void;
}

type PhaseInfo = {
    title: string;
    description: string;
    current: number;
    total: number;
    failed: number;
    isActive: boolean;
    canRetry: boolean;
};

// Resource name mapping for display
const RESOURCE_DISPLAY_NAMES: Record<string, string> = {
    git_history: "Git Clone",
    git_worktree: "Worktrees",
    build_logs: "Build Logs",
};

function ResourceStatusDisplay({ resourceStatus }: { resourceStatus?: ResourceStatus }) {
    if (!resourceStatus) return null;

    const resources = ["git_history", "git_worktree", "build_logs"] as const;

    // Check if any resource has data
    const hasData = resources.some(r => resourceStatus[r] && Object.keys(resourceStatus[r] || {}).length > 0);
    if (!hasData) return null;

    return (
        <div className="mt-4 pt-4 border-t">
            <p className="text-sm font-medium mb-2">Resource Status</p>
            <div className="grid gap-2">
                {resources.map(resourceKey => {
                    const counts = resourceStatus[resourceKey];
                    if (!counts || Object.keys(counts).length === 0) return null;

                    const displayName = RESOURCE_DISPLAY_NAMES[resourceKey] || resourceKey;
                    const completed = counts["completed"] || 0;
                    const failed = counts["failed"] || 0;
                    const skipped = counts["skipped"] || 0;
                    const pending = counts["pending"] || 0;
                    const inProgress = counts["in_progress"] || 0;
                    const total = completed + failed + skipped + pending + inProgress;

                    // Determine status icon and color
                    let StatusIcon = Clock;
                    let statusColor = "text-slate-400";
                    let badgeVariant: "default" | "secondary" | "destructive" | "outline" = "outline";
                    let statusText = "Pending";

                    if (skipped === total && total > 0) {
                        StatusIcon = SkipForward;
                        statusColor = "text-slate-400";
                        badgeVariant = "secondary";
                        statusText = "Skipped";
                    } else if (failed > 0) {
                        StatusIcon = XCircle;
                        statusColor = "text-red-500";
                        badgeVariant = "destructive";
                        statusText = `${failed} Failed`;
                    } else if (inProgress > 0) {
                        StatusIcon = Loader2;
                        statusColor = "text-blue-500";
                        badgeVariant = "default";
                        statusText = "In Progress";
                    } else if (completed === total && total > 0) {
                        StatusIcon = CheckCircle2;
                        statusColor = "text-green-500";
                        badgeVariant = "outline";
                        statusText = "Completed";
                    }

                    return (
                        <div key={resourceKey} className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-2">
                                <StatusIcon className={cn("h-4 w-4", statusColor, StatusIcon === Loader2 && "animate-spin")} />
                                <span className="text-muted-foreground">{displayName}</span>
                            </div>
                            <Badge variant={badgeVariant} className="text-xs font-normal">
                                {statusText}
                            </Badge>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function getPhaseInfo(status: string, progress: ImportProgress | null): PhaseInfo | null {
    if (!progress) return null;

    const statusLower = status.toLowerCase();

    // Queued - waiting to start
    if (statusLower === "queued") {
        return {
            title: "Queued",
            description: "Waiting to start fetching builds from CI provider",
            current: 0,
            total: 0,
            failed: 0,
            isActive: false,
            canRetry: false,
        };
    }

    // Ingesting phase
    if (statusLower === "ingesting") {
        const { ingested, ingesting, total, missing_resource } = progress.import_builds;
        return {
            title: "Ingestion",
            description: "Cloning repository, creating worktrees, downloading logs",
            current: ingested + ingesting,
            total,
            failed: missing_resource,
            isActive: true,
            canRetry: missing_resource > 0,
        };
    }

    // Ingestion complete/partial - waiting for user to start processing
    if (statusLower === "ingestion_complete" || statusLower === "ingestion_partial") {
        const { ingested, total, missing_resource } = progress.import_builds;
        return {
            title: "Ingestion Complete",
            description: missing_resource > 0
                ? "Some builds failed ingestion. You can retry or start processing."
                : "All builds ingested successfully. Ready to start processing.",
            current: ingested,
            total,
            failed: missing_resource,
            isActive: false,
            canRetry: missing_resource > 0,
        };
    }

    // Processing phase
    if (statusLower === "processing") {
        const { completed, partial, pending, total, failed } = progress.training_builds;
        const currentBuildNumber = progress.checkpoint?.current_processing_build_number;
        return {
            title: "Feature Extraction",
            description: currentBuildNumber ? `Processing build #${currentBuildNumber}` : "",
            current: completed + partial,
            total: total || progress.import_builds.ingested,
            failed,
            isActive: true,
            canRetry: false,
        };
    }

    // Imported/Partial - completed
    if (statusLower === "imported" || statusLower === "partial") {
        const { completed, partial, total, failed, with_prediction, pending_prediction } = progress.training_builds;

        // Check if prediction is in progress
        if (pending_prediction && pending_prediction > 0) {
            return {
                title: "Risk Prediction",
                description: "Running Bayesian LSTM model for risk prediction",
                current: with_prediction || 0,
                total: completed + partial,
                failed: progress.training_builds.prediction_failed || 0,
                isActive: true,
                canRetry: false,
            };
        }

        return {
            title: "Completed",
            description: failed > 0
                ? "Processing complete with some failures. You can retry failed builds."
                : "All builds processed and predicted successfully.",
            current: completed + partial,
            total,
            failed,
            isActive: false,
            canRetry: failed > 0,
        };
    }

    // Failed
    if (statusLower === "failed") {
        return {
            title: "Failed",
            description: "Pipeline encountered a critical error",
            current: 0,
            total: progress.import_builds.total,
            failed: progress.import_builds.total,
            isActive: false,
            canRetry: true,
        };
    }

    return null;
}

export function CurrentPhaseCard({ status, progress, isLoading, onRetryFailed }: CurrentPhaseCardProps) {
    const phaseInfo = getPhaseInfo(status, progress);

    if (isLoading || !phaseInfo) {
        return (
            <Card>
                <CardContent className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    const { title, description, current, total, failed, isActive, canRetry } = phaseInfo;
    const progressPercent = total > 0 ? Math.round((current / total) * 100) : 0;
    const remaining = total - current - failed;

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        {isActive ? (
                            <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
                        ) : failed > 0 ? (
                            <AlertCircle className="h-5 w-5 text-amber-500" />
                        ) : current === total && total > 0 ? (
                            <CheckCircle2 className="h-5 w-5 text-green-500" />
                        ) : (
                            <Clock className="h-5 w-5 text-slate-400" />
                        )}
                        <CardTitle className="text-lg">{title}</CardTitle>
                    </div>
                    {canRetry && onRetryFailed && (
                        <Button variant="outline" size="sm" onClick={onRetryFailed} className="gap-1">
                            <RotateCcw className="h-4 w-4" />
                            Retry Failed
                        </Button>
                    )}
                </div>
                <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent>
                {total > 0 && (
                    <div className="space-y-3">
                        {/* Progress Bar */}
                        <div className="space-y-1">
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Progress</span>
                                <span className="font-medium">{progressPercent}%</span>
                            </div>
                            <Progress
                                value={progressPercent}
                                className={cn(
                                    "h-2",
                                    failed > 0 && "bg-red-100 dark:bg-red-950"
                                )}
                            />
                        </div>

                        {/* Stats */}
                        <div className="flex flex-wrap gap-4 text-sm">
                            <div className="flex items-center gap-1">
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                <span className="text-muted-foreground">Completed:</span>
                                <span className="font-medium">{current}</span>
                            </div>
                            {remaining > 0 && (
                                <div className="flex items-center gap-1">
                                    <Clock className="h-4 w-4 text-slate-400" />
                                    <span className="text-muted-foreground">Remaining:</span>
                                    <span className="font-medium">{remaining}</span>
                                </div>
                            )}
                            {failed > 0 && (
                                <div className="flex items-center gap-1">
                                    <XCircle className="h-4 w-4 text-red-500" />
                                    <span className="text-muted-foreground">Failed:</span>
                                    <span className="font-medium text-red-600">{failed}</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {total === 0 && status.toLowerCase() === "queued" && (
                    <p className="text-sm text-muted-foreground">
                        Pipeline is queued and will start shortly...
                    </p>
                )}

                {/* Last Processed Build Checkpoint - shown when checkpoint exists */}
                {progress?.checkpoint?.current_processing_build_number && (
                    <div className="mt-4 pt-4 border-t">
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">Last Processed Build:</span>
                            <Badge variant="outline" className="font-mono">
                                #{progress.checkpoint.current_processing_build_number}
                            </Badge>
                        </div>
                    </div>
                )}

                {/* Resource Status Display - shown during/after ingestion */}
                {progress?.resource_status && (
                    <ResourceStatusDisplay resourceStatus={progress.resource_status} />
                )}
            </CardContent>
        </Card>
    );
}
