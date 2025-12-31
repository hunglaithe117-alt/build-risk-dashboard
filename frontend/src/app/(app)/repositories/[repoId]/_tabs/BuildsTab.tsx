"use client";

import { Loader2, RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { reposApi } from "@/lib/api";

import { ExportPanel } from "../builds/_components/ExportPanel";
import { IngestionBuildsTable } from "./builds/IngestionBuildsTable";
import { ProcessingBuildsTable } from "./builds/ProcessingBuildsTable";

interface BuildsTabProps {
    repoId: string;
    repoName?: string;
}

export function BuildsTab({ repoId, repoName }: BuildsTabProps) {
    const [activeSubTab, setActiveSubTab] = useState<"ingestion" | "processing">("ingestion");
    const [syncing, setSyncing] = useState(false);
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);

    const handleSync = async () => {
        setSyncing(true);
        try {
            await reposApi.triggerLazySync(repoId);
        } catch (err) {
            console.error(err);
        } finally {
            setSyncing(false);
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
                <div className="flex items-center gap-2">
                    <ExportPanel repoId={repoId} repoName={repoName} />
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSync}
                        disabled={syncing}
                    >
                        {syncing ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <RefreshCw className="mr-2 h-4 w-4" />
                        )}
                        Sync Builds
                    </Button>
                </div>
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
