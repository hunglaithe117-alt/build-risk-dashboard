"use client";

import { useParams, usePathname } from "next/navigation";
import { Loader2, Play, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
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
        builds,
        handleStartProcessing,
        startProcessingLoading,
    } = useRepo();

    const repoStatus = repo?.status || "";
    const isSyncing = SYNCING_STATUSES.includes(repoStatus.toLowerCase());
    const canStartProcessing = ["ingested", "processed"].includes(repoStatus.toLowerCase());

    // Check if checkpoint matches the last ingested build (nothing new to process)
    const lastIngestedBuildNumber = builds?.[0]?.build_number;
    const checkpointBuildNumber = progress?.checkpoint?.current_processing_build_number;
    const isFullyProcessed = Boolean(
        lastIngestedBuildNumber &&
        checkpointBuildNumber &&
        lastIngestedBuildNumber === checkpointBuildNumber
    );

    // Check if we're on sub-pages (processing/[buildId] detail pages)
    const isDetailPage = pathname.includes("/processing/") && pathname.split("/").length > 5;

    const handleSync = async () => {
        try {
            await reposApi.triggerLazySync(repoId);
        } catch (err) {
            console.error(err);
        }
    };

    return (
        <div className="space-y-4">
            {/* Action Bar - only show on main builds page, not on detail pages */}
            {!isDetailPage && (
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        {/* Checkpoint indicator */}
                        {progress?.checkpoint?.current_processing_build_number && !isSyncing && (
                            <div className="flex items-center gap-2 text-sm">
                                <span className="text-muted-foreground">Checkpoint:</span>
                                <span className="font-mono text-xs bg-muted px-2 py-1 rounded">
                                    #{progress.checkpoint.current_processing_build_number}
                                </span>
                                {isFullyProcessed && (
                                    <span className="text-xs text-green-600">(Up to date)</span>
                                )}
                            </div>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
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
                            disabled={startProcessingLoading || !canStartProcessing || isSyncing || isFullyProcessed}
                            title={isFullyProcessed ? "All builds are already processed" : undefined}
                        >
                            {startProcessingLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <Play className="mr-2 h-4 w-4" />
                            )}
                            Start Processing
                        </Button>
                        <ExportPanel repoId={repoId} repoName={repo?.full_name} />
                    </div>
                </div>
            )}

            {/* Page Content */}
            {children}
        </div>
    );
}
