"use client";

import { AlertCircle, AlertTriangle, Loader2, RotateCcw } from "lucide-react";

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

interface VersionIngestionCardProps {
    buildsIngested: number;
    buildsTotal: number;
    buildsMissingResource: number;
    buildsIngestionFailed?: number; // New: actual failures (retryable)
    status: string;
    onRetryFailed?: () => void;
    retryLoading?: boolean;
}

export function VersionIngestionCard({
    buildsIngested,
    buildsTotal,
    buildsMissingResource,
    buildsIngestionFailed = 0,
    status,
    onRetryFailed,
    retryLoading = false,
}: VersionIngestionCardProps) {
    const s = status.toLowerCase();
    const isIngesting = ["queued", "ingesting"].includes(s);
    const isComplete = ["ingested", "processing", "processed"].includes(s);

    // Total accountable = ingested + missing + failed
    const totalAccounted = buildsIngested + buildsMissingResource + buildsIngestionFailed;
    const percent = buildsTotal > 0 ? Math.round((totalAccounted / buildsTotal) * 100) : 0;

    return (
        <Card>
            <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-lg flex items-center gap-2">
                            Data Collection
                            {isIngesting && (
                                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                            )}
                        </CardTitle>
                        <CardDescription>
                            Ingest builds and prepare resources for processing
                        </CardDescription>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Progress */}
                <div className="p-4 rounded-lg border bg-slate-50 dark:bg-slate-900/50">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium">Ingestion Progress</span>
                        <span className={cn(
                            "text-sm",
                            isComplete ? "text-green-600" : "text-muted-foreground"
                        )}>
                            {buildsIngested}/{buildsTotal}
                        </span>
                    </div>
                    <Progress value={percent} className="h-2" />
                    <div className="flex justify-between mt-2 flex-wrap gap-1">
                        <p className="text-xs text-muted-foreground">
                            {isIngesting && "In progress..."}
                            {isComplete && "Complete"}
                            {!isIngesting && !isComplete && "Not started"}
                        </p>
                        <div className="flex gap-2">
                            {buildsIngestionFailed > 0 && (
                                <p className="text-xs text-red-600">
                                    {buildsIngestionFailed} failed (retryable)
                                </p>
                            )}
                            {buildsMissingResource > 0 && (
                                <p className="text-xs text-amber-600">
                                    {buildsMissingResource} missing resources
                                </p>
                            )}
                        </div>
                    </div>
                </div>

                {/* Warning for failed builds (retryable) */}
                {buildsIngestionFailed > 0 && isComplete && (
                    <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900">
                        <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
                        <span className="text-sm text-red-700 dark:text-red-400">
                            {buildsIngestionFailed} build(s) failed with errors. You can retry these.
                        </span>
                    </div>
                )}

                {/* Info for missing resources (not retryable) */}
                {buildsMissingResource > 0 && isComplete && (
                    <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900">
                        <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                        <span className="text-sm text-amber-700 dark:text-amber-400">
                            {buildsMissingResource} build(s) have expired logs (not retryable).
                        </span>
                    </div>
                )}

                {/* Retry Action - only for FAILED builds (retryable) */}
                {onRetryFailed && buildsIngestionFailed > 0 && (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onRetryFailed}
                        disabled={retryLoading || isIngesting}
                    >
                        {retryLoading ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <RotateCcw className="mr-2 h-4 w-4" />
                        )}
                        Retry Failed ({buildsIngestionFailed})
                    </Button>
                )}
            </CardContent>
        </Card>
    );
}

