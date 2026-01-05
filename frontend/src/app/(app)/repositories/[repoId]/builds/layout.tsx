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
        handleStartProcessing,
        startProcessingLoading,
    } = useRepo();

    const repoStatus = repo?.status || "";
    const isSyncing = SYNCING_STATUSES.includes(repoStatus.toLowerCase());
    const canStartProcessing = ["ingested", "processed"].includes(repoStatus.toLowerCase());

    // Get counts from progress API
    const lastProcessedCiRunId = progress?.checkpoint?.last_processed_ci_run_id;
    const pendingProcessingCount = progress?.checkpoint?.pending_processing_count ?? 0;

    // Disable Start Processing if no pending builds
    const hasNothingToProcess = pendingProcessingCount === 0;

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
                        {/* Last Processed indicator */}
                        {lastProcessedCiRunId && !isSyncing && (
                            <div className="flex items-center gap-2 text-sm">
                                <span className="text-muted-foreground">Last Processed:</span>
                                <span className="font-mono text-xs bg-muted px-2 py-1 rounded">
                                    {lastProcessedCiRunId}
                                </span>
                                {hasNothingToProcess && (
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
                            disabled={startProcessingLoading || !canStartProcessing || isSyncing || hasNothingToProcess}
                            title={hasNothingToProcess ? "All builds are already processed" : undefined}
                        >
                            {startProcessingLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <Play className="mr-2 h-4 w-4" />
                            )}
                            Start Processing{pendingProcessingCount > 0 && ` (${pendingProcessingCount})`}
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
