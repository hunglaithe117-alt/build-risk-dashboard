"use client";

import { ArrowRight, GitBranch, ExternalLink, Globe, Lock, CheckCircle2, XCircle, Clock, GitCommit, AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { formatTimestamp } from "@/lib/utils";
import type { Build, RepoDetail } from "@/types";

import { MiniStepper } from "../../_components/MiniStepper";
import { CollectionCard } from "../../_components/CollectionCard";
import { ProcessingCard } from "../../_components/ProcessingCard";
import { CurrentPhaseCard } from "../../_components/CurrentPhaseCard";

interface ImportProgress {

    checkpoint: {
        has_checkpoint: boolean;
        last_checkpoint_at: string | null;
        accepted_failed: number;
        stats: Record<string, number>;
    };
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
        total: number;
    };
    resource_status?: Record<string, Record<string, number>>;
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

interface OverviewTabProps {
    repo: RepoDetail;
    progress: ImportProgress | null;
    builds: Build[];
    // Action handlers
    onSync: () => void;
    onRetryIngestion: () => void;
    onStartProcessing: () => void;
    onRetryFailed: () => void;
    // Loading states
    syncLoading: boolean;
    retryIngestionLoading: boolean;
    startProcessingLoading: boolean;
    retryFailedLoading: boolean;
}

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

function ExtractionBadge({ status, hasTrainingData }: { status?: string; hasTrainingData: boolean }) {
    if (!hasTrainingData) {
        return (
            <Badge variant="outline" className="border-slate-400 text-slate-500 gap-1">
                <Clock className="h-3 w-3" /> Pending
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
    if (s === "partial") {
        return (
            <Badge variant="outline" className="border-amber-500 text-amber-600 gap-1">
                <AlertCircle className="h-3 w-3" /> Partial
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
    return <Badge variant="secondary">{status || "—"}</Badge>;
}

export function OverviewTab({
    repo,
    progress,
    builds,
    onSync,
    onRetryIngestion,
    onStartProcessing,
    onRetryFailed,
    syncLoading,
    retryIngestionLoading,
    startProcessingLoading,
    retryFailedLoading,
}: OverviewTabProps) {
    const router = useRouter();
    const repoId = repo.id;
    const status = repo.status || "queued";

    const canStartProcessing = ["ingested", "processed"].includes(status.toLowerCase());

    return (
        <div className="space-y-6">
            {/* Mini Stepper */}
            <MiniStepper status={status} progress={progress} />

            {/* Current Phase Details - shown during active phases */}
            {["queued", "ingesting", "processing"].includes(status.toLowerCase()) && (
                <CurrentPhaseCard
                    status={status}
                    progress={progress}
                    isLoading={false}
                    onRetryFailed={onRetryIngestion}
                />
            )}

            {/* Collection Card - shows current batch (after checkpoint) */}
            <CollectionCard
                fetchedCount={progress?.import_builds.total || 0}
                ingestedCount={progress?.import_builds.ingested || 0}
                totalCount={progress?.import_builds.total || 0}
                failedCount={progress?.import_builds.missing_resource || 0}
                lastSyncedAt={repo.last_synced_at}
                status={status}
                onSync={onSync}
                onRetryFailed={onRetryIngestion}
                syncLoading={syncLoading}
                retryLoading={retryIngestionLoading}
                // Checkpoint props
                hasCheckpoint={progress?.checkpoint?.has_checkpoint || false}
                checkpointAt={progress?.checkpoint?.last_checkpoint_at}
                acceptedFailedCount={progress?.checkpoint?.accepted_failed || 0}
            />

            {/* Processing Card */}
            <ProcessingCard
                extractedCount={(progress?.training_builds.completed || 0) + (progress?.training_builds.partial || 0)}
                extractedTotal={progress?.training_builds.total || progress?.import_builds.ingested || 0}
                predictedCount={progress?.training_builds.with_prediction || 0}
                predictedTotal={(progress?.training_builds.completed || 0) + (progress?.training_builds.partial || 0)}
                failedExtractionCount={progress?.training_builds.failed || 0}
                failedPredictionCount={progress?.training_builds.prediction_failed || 0}
                status={status}
                canStartProcessing={canStartProcessing}
                onStartProcessing={onStartProcessing}
                onRetryFailed={onRetryFailed}
                startLoading={startProcessingLoading}
                retryFailedLoading={retryFailedLoading}
            />

            {/* Repository Info */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Repository Info</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-6 text-sm">
                        <div className="flex items-center gap-2">
                            <GitBranch className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">Default:</span>
                            <span className="font-medium">{repo.default_branch || "main"}</span>
                        </div>
                        {repo.main_lang && (
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Language:</span>
                                <Badge variant="outline">{repo.main_lang}</Badge>
                            </div>
                        )}
                        <div className="flex items-center gap-2">
                            <span className="text-muted-foreground">CI:</span>
                            <Badge variant="outline">{repo.ci_provider}</Badge>
                        </div>
                        <div className="flex items-center gap-2">
                            {repo.is_private ? <Lock className="h-4 w-4" /> : <Globe className="h-4 w-4" />}
                            <span>{repo.is_private ? "Private" : "Public"}</span>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
