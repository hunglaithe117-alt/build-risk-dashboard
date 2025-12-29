"use client";

import { Loader2, Play, RefreshCw, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ActionPanelProps {
    status: string;
    hasFailed: boolean;
    hasIngestionFailed: boolean;
    hasProcessingFailed: boolean;
    hasPredictionFailed: boolean;
    isStartProcessingLoading: boolean;
    isSyncLoading: boolean;
    isRetryIngestionLoading: boolean;
    isRetryProcessingLoading: boolean;
    isRetryPredictionLoading: boolean;
    onStartProcessing: () => void;
    onSync: () => void;
    onRetryIngestion: () => void;
    onRetryProcessing: () => void;
    onRetryPrediction: () => void;
}

export function ActionPanel({
    status,
    hasFailed,
    hasIngestionFailed,
    hasProcessingFailed,
    hasPredictionFailed,
    isStartProcessingLoading,
    isSyncLoading,
    isRetryIngestionLoading,
    isRetryProcessingLoading,
    isRetryPredictionLoading,
    onStartProcessing,
    onSync,
    onRetryIngestion,
    onRetryProcessing,
    onRetryPrediction,
}: ActionPanelProps) {
    const statusLower = status.toLowerCase();
    const isProcessing = ["queued", "ingesting", "processing"].includes(statusLower);

    // Primary action based on status
    const renderPrimaryAction = () => {
        // When ingestion is complete, primary action is Start Processing
        if (statusLower === "ingestion_complete" || statusLower === "ingestion_partial") {
            return (
                <Button
                    onClick={onStartProcessing}
                    disabled={isStartProcessingLoading}
                    className="gap-2 bg-green-600 hover:bg-green-700"
                >
                    {isStartProcessingLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <Play className="h-4 w-4" />
                    )}
                    Start Processing
                </Button>
            );
        }

        // When processing failed, primary action is Retry Failed
        if ((statusLower === "partial" || statusLower === "failed") && hasProcessingFailed) {
            return (
                <Button
                    onClick={onRetryProcessing}
                    disabled={isRetryProcessingLoading}
                    className="gap-2"
                >
                    {isRetryProcessingLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <RotateCcw className="h-4 w-4" />
                    )}
                    Retry Failed Extractions
                </Button>
            );
        }

        // During processing, show processing indicator
        if (isProcessing) {
            return (
                <Button disabled className="gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {statusLower === "queued" && "Queued..."}
                    {statusLower === "ingesting" && "Ingesting..."}
                    {statusLower === "processing" && "Processing..."}
                </Button>
            );
        }

        // Default - Sync new builds
        return (
            <Button
                onClick={onSync}
                disabled={isSyncLoading || isProcessing}
                variant="outline"
                className="gap-2"
            >
                {isSyncLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                    <RefreshCw className="h-4 w-4" />
                )}
                Sync New Builds
            </Button>
        );
    };

    // Secondary actions
    const renderSecondaryActions = () => {
        const actions = [];

        // Show Sync button when ingestion/processing is complete
        const showSyncAsSecondary = [
            "ingestion_complete",
            "ingestion_partial",
            "imported",
            "partial"
        ].includes(statusLower);

        if (showSyncAsSecondary) {
            actions.push(
                <Button
                    key="sync"
                    variant="outline"
                    onClick={onSync}
                    disabled={isSyncLoading || isProcessing}
                    className="gap-2"
                >
                    {isSyncLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <RefreshCw className="h-4 w-4" />
                    )}
                    Sync New Builds
                </Button>
            );
        }

        // Retry ingestion failures
        if (hasIngestionFailed && (statusLower === "ingestion_partial" || statusLower === "failed")) {
            actions.push(
                <Button
                    key="retry-ingestion"
                    variant="outline"
                    onClick={onRetryIngestion}
                    disabled={isRetryIngestionLoading}
                    className="gap-2"
                >
                    {isRetryIngestionLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <RotateCcw className="h-4 w-4" />
                    )}
                    Retry Failed Ingestion
                </Button>
            );
        }

        // Retry prediction failures
        if (hasPredictionFailed) {
            actions.push(
                <Button
                    key="retry-prediction"
                    variant="outline"
                    onClick={onRetryPrediction}
                    disabled={isRetryPredictionLoading}
                    className="gap-2"
                >
                    {isRetryPredictionLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <RotateCcw className="h-4 w-4" />
                    )}
                    Retry Failed Predictions
                </Button>
            );
        }

        return actions;
    };

    return (
        <div className="flex flex-wrap items-center gap-2">
            {renderPrimaryAction()}
            {renderSecondaryActions()}
        </div>
    );
}
