"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { Loader2, Play, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { reposApi } from "@/lib/api";
import { useRepo } from "../repo-context";

import { ExportPanel } from "../builds/_components/ExportPanel";

// Statuses that indicate sync/ingestion is in progress
const SYNCING_STATUSES = ["queued", "fetching", "ingesting"];

export default function BuildsLayout({ children }: { children: React.ReactNode }) {
    const params = useParams();
    const pathname = usePathname();
    const repoId = params.repoId as string;

    const {
        repo,
        progress,
        handleStartProcessing,
        startProcessingLoading,
    } = useRepo();

    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);

    const repoStatus = repo?.status || "";
    const isSyncing = SYNCING_STATUSES.includes(repoStatus.toLowerCase());
    const canStartProcessing = ["ingested", "processed"].includes(repoStatus.toLowerCase());

    const failedIngestionCount = progress?.import_builds.missing_resource_retryable || 0;

    // Determine active sub-tab
    const isIngestionActive = pathname.endsWith("/ingestion");
    const isProcessingActive = pathname.endsWith("/processing");

    const handleSync = async () => {
        try {
            await reposApi.triggerLazySync(repoId);
        } catch (err) {
            console.error(err);
        }
    };

    const handleRetryIngestion = async () => {
        setRetryIngestionLoading(true);
        try {
            await reposApi.reingestFailed(repoId);
        } catch (err) {
            console.error(err);
        } finally {
            setRetryIngestionLoading(false);
        }
    };

    return (
        <div className="space-y-4">
            {/* Sub-tab Navigation + Actions */}
            <div className="flex items-center justify-between">
                {/* Sub-tabs */}
                <div className="flex gap-1 rounded-lg bg-muted p-1">
                    <Link
                        href={`/repositories/${repoId}/builds/ingestion`}
                        className={cn(
                            "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
                            isIngestionActive
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Data Collection
                    </Link>
                    <Link
                        href={`/repositories/${repoId}/builds/processing`}
                        className={cn(
                            "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
                            isProcessingActive
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Features & Predictions
                    </Link>
                </div>

                {/* Actions based on active sub-tab */}
                {isIngestionActive ? (
                    <div className="flex items-center gap-2">
                        {failedIngestionCount > 0 && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleRetryIngestion}
                                disabled={retryIngestionLoading || isSyncing}
                                className="text-amber-600 border-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                            >
                                {retryIngestionLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry Failed ({failedIngestionCount})
                            </Button>
                        )}
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleSync}
                            disabled={isSyncing}
                        >
                            {isSyncing ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <RefreshCw className="mr-2 h-4 w-4" />
                            )}
                            {isSyncing ? "Syncing..." : "Sync Builds"}
                        </Button>
                        <Button
                            size="sm"
                            onClick={handleStartProcessing}
                            disabled={startProcessingLoading || !canStartProcessing || isSyncing}
                        >
                            {startProcessingLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <Play className="mr-2 h-4 w-4" />
                            )}
                            Start Processing
                        </Button>
                    </div>
                ) : isProcessingActive ? (
                    <div className="flex items-center gap-2">
                        {/* Last Processed Build Checkpoint - hide during sync/processing */}
                        {progress?.checkpoint?.current_processing_ci_run_id && !isSyncing && repoStatus.toLowerCase() !== "processing" && (
                            <div className="flex items-center gap-2 text-sm">
                                <span className="text-muted-foreground">Checkpoint:</span>
                                <span className="font-mono text-xs bg-muted px-2 py-1 rounded">
                                    #{progress.checkpoint.current_processing_ci_run_id}
                                </span>
                            </div>
                        )}
                        <ExportPanel repoId={repoId} repoName={repo?.full_name} />
                    </div>
                ) : null}
            </div>

            {/* Sub-page Content */}
            {children}
        </div>
    );
}
