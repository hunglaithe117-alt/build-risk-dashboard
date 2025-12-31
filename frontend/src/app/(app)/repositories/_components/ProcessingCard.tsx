"use client";

import { Loader2, Play, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface ProcessingCardProps {
    extractedCount: number;
    extractedTotal: number;
    predictedCount: number;
    predictedTotal: number;
    failedExtractionCount: number;
    failedPredictionCount: number;
    status: string;
    canStartProcessing: boolean;
    onStartProcessing: () => void;
    onRetryFailed: () => void; // Unified: handles both extraction + prediction
    startLoading: boolean;
    retryFailedLoading: boolean;
}

export function ProcessingCard({
    extractedCount,
    extractedTotal,
    predictedCount,
    predictedTotal,
    failedExtractionCount,
    failedPredictionCount,
    status,
    canStartProcessing,
    onStartProcessing,
    onRetryFailed,
    startLoading,
    retryFailedLoading,
}: ProcessingCardProps) {
    const s = status.toLowerCase();
    const isProcessing = s === "processing";
    const isComplete = s === "imported" || s === "partial" || s === "processed";
    const notStarted = ["ingested", "ingestion_complete", "ingestion_partial"].includes(s);

    const extractionPercent = extractedTotal > 0 ? Math.round((extractedCount / extractedTotal) * 100) : 0;
    const predictionPercent = predictedTotal > 0 ? Math.round((predictedCount / predictedTotal) * 100) : 0;

    const totalFailed = failedExtractionCount + failedPredictionCount;

    return (
        <Card>
            <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-lg flex items-center gap-2">
                            Processing
                            {isProcessing && (
                                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                            )}
                        </CardTitle>
                        <CardDescription>
                            Extract features and predict build risk
                        </CardDescription>
                    </div>
                    {canStartProcessing && notStarted && (
                        <Button
                            onClick={onStartProcessing}
                            disabled={startLoading}
                            className="gap-2"
                        >
                            {startLoading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Play className="h-4 w-4" />
                            )}
                            Start Processing
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Progress Bars */}
                <div className="grid md:grid-cols-2 gap-4">
                    {/* Extraction Progress */}
                    <div className="p-4 rounded-lg border bg-slate-50 dark:bg-slate-900/50">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Feature Extraction</span>
                            <span className={cn(
                                "text-sm",
                                extractionPercent === 100 ? "text-green-600" : "text-muted-foreground"
                            )}>
                                {extractedCount}/{extractedTotal}
                            </span>
                        </div>
                        <Progress value={extractionPercent} className="h-2" />
                        <p className="text-xs text-muted-foreground mt-2">
                            {notStarted && "Not started"}
                            {isProcessing && "In progress..."}
                            {isComplete && extractionPercent === 100 && "Complete"}
                            {isComplete && extractionPercent < 100 && `${failedExtractionCount} failed`}
                        </p>
                    </div>

                    {/* Prediction Progress */}
                    <div className="p-4 rounded-lg border bg-slate-50 dark:bg-slate-900/50">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Risk Prediction</span>
                            <span className={cn(
                                "text-sm",
                                predictionPercent === 100 && predictedTotal > 0 ? "text-green-600" : "text-muted-foreground"
                            )}>
                                {predictedTotal > 0 ? `${predictedCount}/${predictedTotal}` : "—"}
                            </span>
                        </div>
                        <Progress value={predictionPercent} className="h-2" />
                        <p className="text-xs text-muted-foreground mt-2">
                            {predictedTotal === 0 && "Waiting for extraction"}
                            {predictedTotal > 0 && predictionPercent === 100 && "Complete"}
                            {predictedTotal > 0 && predictionPercent < 100 && failedPredictionCount > 0 && `${failedPredictionCount} failed`}
                            {predictedTotal > 0 && predictionPercent < 100 && failedPredictionCount === 0 && "In progress..."}
                        </p>
                    </div>
                </div>

                {/* Unified Retry Action */}
                {totalFailed > 0 && (
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRetryFailed}
                            disabled={retryFailedLoading || isProcessing}
                        >
                            {retryFailedLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <RotateCcw className="mr-2 h-4 w-4" />
                            )}
                            Retry Failed ({totalFailed})
                        </Button>
                        <span className="text-xs text-muted-foreground self-center">
                            {failedExtractionCount > 0 && failedPredictionCount > 0
                                ? `${failedExtractionCount} extraction + ${failedPredictionCount} prediction`
                                : failedExtractionCount > 0
                                    ? `${failedExtractionCount} extraction failures`
                                    : `${failedPredictionCount} prediction failures`
                            }
                        </span>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
