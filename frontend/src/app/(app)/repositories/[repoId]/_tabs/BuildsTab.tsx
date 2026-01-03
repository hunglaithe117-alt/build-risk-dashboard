"use client";

import { Loader2, Play, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { reposApi } from "@/lib/api";

import { ExportPanel } from "../builds/_components/ExportPanel";
import { IngestionBuildsTable } from "./builds/IngestionBuildsTable";
import { ProcessingBuildsTable } from "./builds/ProcessingBuildsTable";

// Statuses that indicate sync/ingestion is in progress
const SYNCING_STATUSES = ["queued", "fetching", "ingesting"];

interface BuildsTabProps {
    repoId: string;
    repoName?: string;
    repoStatus?: string;
    // Props for Start Processing button
    onStartProcessing?: () => void;
    startProcessingLoading?: boolean;
    canStartProcessing?: boolean;
    // Failed counts for showing retry buttons
    failedIngestionCount?: number;
    failedProcessingCount?: number;
    // Checkpoint info
    lastProcessedBuildId?: string | null;
}

export function BuildsTab({
    repoId,
    repoName,
    repoStatus = "",
    onStartProcessing,
    startProcessingLoading = false,
    canStartProcessing = false,
    failedIngestionCount = 0,
    failedProcessingCount = 0,
    lastProcessedBuildId,
}: BuildsTabProps) {
    const [activeSubTab, setActiveSubTab] = useState<"ingestion" | "processing">("ingestion");
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);

    // Sync is in progress if status is queued, fetching, or ingesting
    const isSyncing = SYNCING_STATUSES.includes(repoStatus.toLowerCase());

    const handleSync = async () => {
        try {
            await reposApi.triggerLazySync(repoId);
            // Button will be disabled via repoStatus update from WebSocket
        } catch (err) {
            console.error(err);
        }
    };

    const handleRetryIngestion = async () => {
        setRetryIngestionLoading(true);
        try {
            // Only retries builds after checkpoint
            await reposApi.reingestFailed(repoId);
        } catch (err) {
            console.error(err);
        } finally {
            setRetryIngestionLoading(false);
        }
    };

    const handleRetryProcessing = async () => {
        setRetryProcessingLoading(true);
        try {
            await reposApi.reprocessFailed(repoId);
        } catch (err) {
            console.error(err);
        } finally {
            setRetryProcessingLoading(false);
        }
    };

    return (
        <div className="space-y-4">
            {/* Header Actions */}
            <div className="flex items-center justify-between">
                <Tabs
                    value={activeSubTab}
                    onValueChange={(v) => setActiveSubTab(v as "ingestion" | "processing")}
                >
                    <TabsList>
                        <TabsTrigger value="ingestion">Data Collection</TabsTrigger>
                        <TabsTrigger value="processing">Features & Predictions</TabsTrigger>
                    </TabsList>
                </Tabs>

                {/* Conditional buttons based on active tab */}
                {activeSubTab === "ingestion" ? (
                    <div className="flex items-center gap-2">
                        {/* Retry Ingestion button - only show if there are failed builds */}
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
                        {onStartProcessing && (
                            <Button
                                size="sm"
                                onClick={onStartProcessing}
                                disabled={startProcessingLoading || !canStartProcessing || isSyncing}
                            >
                                {startProcessingLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Play className="mr-2 h-4 w-4" />
                                )}
                                Start Processing
                            </Button>
                        )}
                    </div>
                ) : (
                    <div className="flex items-center gap-2">
                        {/* Retry Processing button - only show if there are failed builds */}
                        {failedProcessingCount > 0 && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleRetryProcessing}
                                disabled={retryProcessingLoading}
                                className="text-amber-600 border-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                            >
                                {retryProcessingLoading ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry Failed ({failedProcessingCount})
                            </Button>
                        )}
                        {/* Last Processed Build Checkpoint */}
                        {lastProcessedBuildId && (
                            <div className="flex items-center gap-2 text-sm">
                                <span className="text-muted-foreground">Checkpoint:</span>
                                <Badge variant="outline" className="font-mono">
                                    #{lastProcessedBuildId}
                                </Badge>
                            </div>
                        )}
                        <ExportPanel repoId={repoId} repoName={repoName} />
                    </div>
                )}
            </div>

            {/* Sub-tab Content */}
            {activeSubTab === "ingestion" ? (
                <IngestionBuildsTable
                    repoId={repoId}
                    onRetryAllFailed={handleRetryIngestion}
                    retryAllLoading={retryIngestionLoading}
                />
            ) : (
                <ProcessingBuildsTable
                    repoId={repoId}
                    onRetryAllFailed={handleRetryProcessing}
                    retryAllLoading={retryProcessingLoading}
                />
            )}
        </div>
    );
}
