"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Loader2, AlertCircle, Sparkles } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { DatasetRecord } from "@/types";
import { VersionHistoryTable } from "../VersionHistoryTable";
import { useDatasetVersions, type DatasetVersion } from "../../_hooks/useDatasetVersions";
import { useWebSocket } from "@/contexts/websocket-context";
import { CheckCircle2, Play, RotateCcw } from "lucide-react";

interface EnrichmentTabProps {
    datasetId: string;
    dataset: DatasetRecord;
    onEnrichmentStatusChange?: (hasActiveJob: boolean) => void;
}

export function EnrichmentTab({
    datasetId,
    dataset,
    onEnrichmentStatusChange,
}: EnrichmentTabProps) {
    const router = useRouter();
    const { subscribe } = useWebSocket();

    const {
        versions,
        activeVersion,
        loading,
        error,
        refresh,
        deleteVersion,
        downloadVersion,
        startProcessing,
        retryIngestion,
        retryProcessing,
    } = useDatasetVersions(datasetId);

    // Find version waiting for user action
    const waitingVersion = versions.find(
        (v) => v.status === "ingested"
    );

    // Find version with failed processing
    const failedVersion = versions.find(
        (v) => v.status === "failed"
    );

    // WebSocket subscription for real-time enrichment updates
    useEffect(() => {
        const unsubscribe = subscribe("ENRICHMENT_UPDATE", (data: {
            version_id: string;
            status: string;
            processed_rows: number;
            total_rows: number;
            enriched_rows: number;
            failed_rows: number;
            progress: number;
        }) => {
            // Check if this update is for one of our versions
            const isOurVersion = versions.some(v => v.id === data.version_id);
            if (isOurVersion) {
                // Refresh to get updated data
                refresh();
            }
        });

        return () => unsubscribe();
    }, [subscribe, refresh, versions]);

    // Notify parent when active version status changes
    const hasActiveVersion = !!activeVersion;

    const notifyParent = useCallback(() => {
        onEnrichmentStatusChange?.(hasActiveVersion);
    }, [hasActiveVersion, onEnrichmentStatusChange]);

    // Check if dataset is validated
    const isValidated = dataset.validation_status === "completed";
    const mappingReady = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );

    // Navigate to full-page wizard
    const handleCreateVersion = () => {
        router.push(`/projects/${datasetId}/versions/new`);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Show warning if not validated
    if (!isValidated) {
        return (
            <Alert variant="destructive" className="my-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Dataset validation must be completed before creating enriched
                    versions. Please go to the Configuration tab to validate.
                </AlertDescription>
            </Alert>
        );
    }

    // Show warning if mapping not ready
    if (!mappingReady) {
        return (
            <Alert variant="destructive" className="my-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Dataset must have <code>build_id</code> and{" "}
                    <code>repo_name</code> columns mapped before enrichment.
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header with Create Button */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold">Dataset Enrichment</h2>
                    <p className="text-sm text-muted-foreground">
                        Create enriched versions of your dataset with extracted features
                    </p>
                </div>
                <Button
                    onClick={handleCreateVersion}
                    disabled={hasActiveVersion}
                    className="gap-2"
                >
                    <Sparkles className="h-4 w-4" />
                    Create New Version
                </Button>
            </div>

            {/* Error Alert */}
            {error && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            {/* Active Version Progress */}
            {activeVersion && (
                <ActiveVersionCard version={activeVersion} />
            )}

            {/* Failed/Partial Processing - Show retry */}
            {failedVersion && (
                <FailedVersionCard
                    version={failedVersion}
                    onRetryProcessing={() => retryProcessing(failedVersion.id)}
                />
            )}

            {/* Waiting for user action - Start Processing */}
            {waitingVersion && (
                <WaitingVersionCard
                    version={waitingVersion}
                    onStartProcessing={() => startProcessing(waitingVersion.id)}
                    onRetryIngestion={() => retryIngestion(waitingVersion.id)}
                />
            )}

            {/* Version History Table */}
            <VersionHistoryTable
                datasetId={datasetId}
                versions={versions}
                loading={loading}
                onRefresh={refresh}
                onDownload={downloadVersion}
                onDelete={deleteVersion}
            />
        </div>
    );
}

interface ActiveVersionCardProps {
    version: {
        id: string;
        name: string;
        status: string;
        progress_percent: number;
        processed_rows: number;
        total_rows: number;
        failed_rows: number;
        enriched_rows?: number;
    };
}

function ActiveVersionCard({ version }: ActiveVersionCardProps) {
    // Determine current phase
    const isIngesting = version.status.startsWith("ingesting");
    const isProcessing = version.status === "processing";

    return (
        <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        {isIngesting ? "Ingesting" : "Processing"}: {version.name}
                    </CardTitle>
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                {/* Phase Indicator */}
                <div className="flex items-center justify-center gap-2 text-xs">
                    <div className={`flex items-center gap-1 ${isIngesting ? "text-blue-600 font-medium" : "text-muted-foreground"}`}>
                        <div className={`w-2 h-2 rounded-full ${isIngesting ? "bg-blue-500" : "bg-green-500"}`} />
                        Ingesting
                    </div>
                    <div className="w-6 h-px bg-muted-foreground/30" />
                    <div className={`flex items-center gap-1 ${isProcessing ? "text-blue-600 font-medium" : "text-muted-foreground"}`}>
                        <div className={`w-2 h-2 rounded-full ${isProcessing ? "bg-blue-500" : isIngesting ? "bg-muted-foreground/30" : "bg-green-500"}`} />
                        Processing
                    </div>
                    <div className="w-6 h-px bg-muted-foreground/30" />
                    <div className="flex items-center gap-1 text-muted-foreground">
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/30" />
                        Complete
                    </div>
                </div>

                <Progress value={version.progress_percent} className="h-2" />
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                        {version.processed_rows.toLocaleString()} /{" "}
                        {version.total_rows.toLocaleString()} {isIngesting ? "builds ingested" : "builds processed"}
                    </span>
                    <span>{version.progress_percent.toFixed(1)}%</span>
                </div>
                {version.failed_rows > 0 && (
                    <p className="text-sm text-amber-600">
                        ⚠️ {version.failed_rows} rows failed
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

interface WaitingVersionCardProps {
    version: DatasetVersion;
    onStartProcessing: () => void;
    onRetryIngestion: () => void;
}

function WaitingVersionCard({ version, onStartProcessing, onRetryIngestion }: WaitingVersionCardProps) {
    const isPartial = version.status === "ingesting_partial";

    return (
        <Card className={isPartial
            ? "border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20"
            : "border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20"
        }>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <CheckCircle2 className={`h-4 w-4 ${isPartial ? "text-amber-500" : "text-green-500"}`} />
                        {isPartial ? "Ingestion Partial" : "Ingestion Complete"}: {version.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        {isPartial && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onRetryIngestion}
                            >
                                <RotateCcw className="mr-1 h-4 w-4" />
                                Retry Failed
                            </Button>
                        )}
                        <Button
                            size="sm"
                            onClick={onStartProcessing}
                            className="bg-green-600 hover:bg-green-700"
                        >
                            <Play className="mr-1 h-4 w-4" />
                            Start Processing
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <p className="text-sm text-muted-foreground">
                    {version.enriched_rows} / {version.total_rows} builds ingested.
                    {isPartial && ` ${version.failed_rows} failed.`}
                    {" "}Click &quot;Start Processing&quot; to begin feature extraction.
                </p>
            </CardContent>
        </Card>
    );
}

// Card for failed/partial processing versions
interface FailedVersionCardProps {
    version: DatasetVersion;
    onRetryProcessing: () => void;
}

function FailedVersionCard({ version, onRetryProcessing }: FailedVersionCardProps) {
    const isPartial = version.status === "partial";

    return (
        <Card className="border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <AlertCircle className="h-4 w-4 text-red-500" />
                        {isPartial ? "Processing Partial" : "Processing Failed"}: {version.name}
                    </CardTitle>
                    <Button
                        size="sm"
                        onClick={onRetryProcessing}
                        className="gap-2"
                    >
                        <RotateCcw className="h-4 w-4" />
                        Retry Failed Builds
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                <p className="text-sm text-muted-foreground">
                    {version.enriched_rows} / {version.total_rows} builds processed.
                    <span className="text-red-600 font-medium"> {version.failed_rows} failed.</span>
                    {" "}Click &quot;Retry Failed Builds&quot; to reprocess failed extractions.
                </p>
            </CardContent>
        </Card>
    );
}
