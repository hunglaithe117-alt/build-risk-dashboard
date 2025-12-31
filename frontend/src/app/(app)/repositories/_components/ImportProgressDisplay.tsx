"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { reposApi } from "@/lib/api";

interface ImportProgressDisplayProps {
    repoId: string;
    totalFetched: number;
    totalIngested: number;
    totalProcessed: number;
    totalFailed: number;
    importStatus: string;
}

interface ImportProgress {
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
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

export function ImportProgressDisplay({
    repoId,
    totalFetched,
    totalIngested,
    totalProcessed,
    totalFailed,
    importStatus,
}: ImportProgressDisplayProps) {
    const [progress, setProgress] = useState<ImportProgress | null>(null);
    const [loading, setLoading] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

    useEffect(() => {
        if (isOpen && !progress && !loading) {
            setLoading(true);
            reposApi
                .getImportProgress(repoId)
                .then((data) => {
                    setProgress({
                        import_builds: data.import_builds,
                        training_builds: data.training_builds,
                    });
                })
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [isOpen, repoId, progress, loading]);

    // Display logic based on phase
    const isFetching = ["queued", "fetching"].includes(importStatus);
    const isIngesting = ["ingesting", "ingestion_partial"].includes(importStatus);
    const isIngested = ["ingested", "ingestion_complete"].includes(importStatus);
    const isProcessing = ["processing"].includes(importStatus);
    const isProcessed = ["processed", "imported", "partial"].includes(importStatus);

    let mainText = "";
    let subText = "";
    let progressValue = 0;
    let progressColor = "bg-slate-200";

    if (isFetching) {
        mainText = totalFetched > 0 ? `${totalFetched} fetched` : "Fetching...";
        progressValue = 100; // Indeterminate pulse
        progressColor = "bg-cyan-500 animate-pulse";
    } else if (isIngesting) {
        mainText = `${totalIngested}/${totalFetched} ingested`;
        progressValue = totalFetched > 0 ? (totalIngested / totalFetched) * 100 : 0;
        progressColor = "bg-blue-500 animate-pulse";
    } else if (isIngested) {
        mainText = `${totalIngested} ready`;
        subText = "Ready to process";
        progressValue = 100;
        progressColor = "bg-blue-500";
    } else if (isProcessing) {
        const totalToProcess = totalIngested > 0 ? totalIngested : totalFetched;
        mainText = `${totalProcessed}/${totalToProcess} processed`;
        progressValue = totalToProcess > 0 ? (totalProcessed / totalToProcess) * 100 : 0;
        progressColor = "bg-purple-500 animate-pulse";
    } else if (isProcessed) {
        mainText = `${totalProcessed} processed`;
        progressValue = 100;
        progressColor = "bg-green-500";
    } else {
        // Fallback for unknown states or 'failed'
        mainText = totalProcessed > 0 ? `${totalProcessed} processed` :
            totalIngested > 0 ? `${totalIngested} ingested` :
                totalFetched > 0 ? `${totalFetched} fetched` : "—";
        progressValue = 0;
    }

    // Override coloring for failures
    if (totalFailed > 0 && !isProcessing && !isIngesting && !isFetching) {
        progressColor = "bg-amber-500";
    }

    return (
        <TooltipProvider>
            <Tooltip open={isOpen} onOpenChange={setIsOpen}>
                <TooltipTrigger asChild>
                    <div
                        className="space-y-1.5 cursor-help"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between text-sm">
                            <span className="font-medium truncate mr-2">
                                {mainText}
                            </span>
                            {totalFailed > 0 && (
                                <span className="text-red-500 text-xs font-medium whitespace-nowrap">
                                    {totalFailed} missing
                                </span>
                            )}
                        </div>

                        <div className="h-2 w-full max-w-[140px] rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                            <div
                                className={`h-full transition-all duration-500 ${progressColor}`}
                                style={{ width: `${Math.max(5, progressValue)}%` }}
                            />
                        </div>

                        {subText && (
                            <div className="text-xs text-muted-foreground">
                                {subText}
                            </div>
                        )}
                    </div>
                </TooltipTrigger>
                <TooltipContent
                    side="bottom"
                    align="start"
                    className="w-72 p-0"
                    onClick={(e) => e.stopPropagation()}
                >
                    {loading ? (
                        <div className="flex items-center justify-center p-4">
                            <Loader2 className="h-4 w-4 animate-spin" />
                        </div>
                    ) : progress ? (
                        <div className="p-3 space-y-3">
                            {/* Import Phase */}
                            <div>
                                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                                    Import Phase
                                </h4>
                                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Pending:</span>
                                        <span>{progress.import_builds.pending}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Fetched:</span>
                                        <span className="text-blue-500">
                                            {progress.import_builds.fetched}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Ingesting:</span>
                                        <span className="text-yellow-500">
                                            {progress.import_builds.ingesting}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Ingested:</span>
                                        <span className="text-green-500">
                                            {progress.import_builds.ingested}
                                        </span>
                                    </div>
                                    {progress.import_builds.missing_resource > 0 && (
                                        <div className="flex justify-between col-span-2">
                                            <span className="text-muted-foreground">Missing Res:</span>
                                            <span className="text-red-500">
                                                {progress.import_builds.missing_resource}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Processing Phase */}
                            {progress.training_builds.total > 0 && (
                                <div className="border-t pt-2">
                                    <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                                        Feature Extraction
                                    </h4>
                                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Pending:</span>
                                            <span>{progress.training_builds.pending}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Completed:</span>
                                            <span className="text-green-500">
                                                {progress.training_builds.completed}
                                            </span>
                                        </div>
                                        {progress.training_builds.partial > 0 && (
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Partial:</span>
                                                <span className="text-yellow-500">
                                                    {progress.training_builds.partial}
                                                </span>
                                            </div>
                                        )}
                                        {progress.training_builds.failed > 0 && (
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Failed:</span>
                                                <span className="text-red-500">
                                                    {progress.training_builds.failed}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Prediction Phase */}
                            {((progress.training_builds.with_prediction ?? 0) > 0 ||
                                (progress.training_builds.pending_prediction ?? 0) > 0) && (
                                    <div className="border-t pt-2">
                                        <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                                            Risk Prediction
                                        </h4>
                                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Pending:</span>
                                                <span>{progress.training_builds.pending_prediction || 0}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Completed:</span>
                                                <span className="text-green-500">
                                                    {progress.training_builds.with_prediction || 0}
                                                </span>
                                            </div>
                                            {(progress.training_builds.prediction_failed || 0) > 0 && (
                                                <div className="flex justify-between">
                                                    <span className="text-muted-foreground">Failed:</span>
                                                    <span className="text-red-500">
                                                        {progress.training_builds.prediction_failed}
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                        </div>
                    ) : (
                        <div className="p-3 text-xs text-muted-foreground">
                            Hover to load details
                        </div>
                    )}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
