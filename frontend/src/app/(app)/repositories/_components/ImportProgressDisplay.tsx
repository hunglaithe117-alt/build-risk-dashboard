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

export function ImportProgressDisplay({
    repoId,
    totalFetched,
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

    const processedPercent =
        totalFetched > 0 ? Math.round((totalProcessed / totalFetched) * 100) : 0;

    const isActive = importStatus === "ingesting" || importStatus === "processing" || importStatus === "queued";
    const isComplete = totalFetched > 0 && totalProcessed >= totalFetched && totalFailed === 0;

    return (
        <TooltipProvider>
            <Tooltip open={isOpen} onOpenChange={setIsOpen}>
                <TooltipTrigger asChild>
                    <div
                        className="space-y-1 cursor-help"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center gap-2 text-sm">
                            <span className="font-medium">
                                {totalProcessed}/{totalFetched}
                            </span>
                            {isComplete ? (
                                <span className="text-green-600 dark:text-green-400">✓</span>
                            ) : totalFailed > 0 ? (
                                <span className="text-red-500 text-xs">
                                    ({totalFailed} failed)
                                </span>
                            ) : null}
                            <span className="text-muted-foreground text-xs">
                                ({processedPercent}%)
                            </span>
                        </div>
                        {totalFetched > 0 && (
                            <div className="h-1.5 w-28 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                                <div
                                    className={`h-full transition-all ${totalFailed > 0
                                        ? "bg-red-500"
                                        : isActive
                                            ? "bg-blue-500 animate-pulse"
                                            : "bg-green-500"
                                        }`}
                                    style={{ width: `${processedPercent}%` }}
                                />
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
                                    {progress.import_builds.failed > 0 && (
                                        <div className="flex justify-between col-span-2">
                                            <span className="text-muted-foreground">Failed:</span>
                                            <span className="text-red-500">
                                                {progress.import_builds.failed}
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
