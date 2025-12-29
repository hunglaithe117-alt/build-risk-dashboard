"use client";

import { AlertCircle, CheckCircle2, Clock, Loader2, RotateCcw, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface ImportProgress {
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        failed: number;
        total: number;
    };
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
        const { ingested, ingesting, total, failed } = progress.import_builds;
        return {
            title: "Ingestion",
            description: "Cloning repository, creating worktrees, downloading logs",
            current: ingested + ingesting,
            total,
            failed,
            isActive: true,
            canRetry: failed > 0,
        };
    }

    // Ingestion complete/partial - waiting for user to start processing
    if (statusLower === "ingestion_complete" || statusLower === "ingestion_partial") {
        const { ingested, total, failed } = progress.import_builds;
        return {
            title: "Ingestion Complete",
            description: failed > 0
                ? "Some builds failed ingestion. You can retry or start processing."
                : "All builds ingested successfully. Ready to start processing.",
            current: ingested,
            total,
            failed,
            isActive: false,
            canRetry: failed > 0,
        };
    }

    // Processing phase
    if (statusLower === "processing") {
        const { completed, partial, pending, total, failed } = progress.training_builds;
        return {
            title: "Feature Extraction",
            description: "Extracting features from builds using Hamilton DAG",
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
            </CardContent>
        </Card>
    );
}
