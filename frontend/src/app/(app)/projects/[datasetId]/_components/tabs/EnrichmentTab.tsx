"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Loader2, AlertCircle, Sparkles, X } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { DatasetRecord } from "@/types";
import { VersionHistoryTable } from "../VersionHistoryTable";
import { useDatasetVersions, type DatasetVersion } from "../../_hooks/useDatasetVersions";
import { useWebSocket } from "@/contexts/websocket-context";

interface EnrichmentTabProps {
    datasetId: string;
    dataset: DatasetRecord;
    onEnrichmentStatusChange?: (hasActiveJob: boolean) => void;
}

export function EnrichmentTab({
    datasetId,
    dataset,
    onEnrichmentStatusChange,
}: EnrichmentTabProps) {
    const router = useRouter();
    const { subscribe } = useWebSocket();

    const {
        versions,
        activeVersion,
        loading,
        error,
        refresh,
        cancelVersion,
        deleteVersion,
        downloadVersion,
    } = useDatasetVersions(datasetId);

    // WebSocket subscription for real-time enrichment updates
    useEffect(() => {
        const unsubscribe = subscribe("ENRICHMENT_UPDATE", (data: {
            version_id: string;
            status: string;
            processed_rows: number;
            total_rows: number;
            enriched_rows: number;
            failed_rows: number;
            progress: number;
        }) => {
            // Check if this update is for one of our versions
            const isOurVersion = versions.some(v => v.id === data.version_id);
            if (isOurVersion) {
                // Refresh to get updated data
                refresh();
            }
        });

        return () => unsubscribe();
    }, [subscribe, refresh, versions]);

    // Notify parent when active version status changes
    const hasActiveVersion = !!activeVersion;

    const notifyParent = useCallback(() => {
        onEnrichmentStatusChange?.(hasActiveVersion);
    }, [hasActiveVersion, onEnrichmentStatusChange]);

    // Check if dataset is validated
    const isValidated = dataset.validation_status === "completed";
    const mappingReady = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );

    // Handle cancel
    const handleCancel = async (versionId: string) => {
        await cancelVersion(versionId);
        notifyParent();
    };

    // Navigate to full-page wizard
    const handleCreateVersion = () => {
        router.push(`/projects/${datasetId}/versions/new`);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Show warning if not validated
    if (!isValidated) {
        return (
            <Alert variant="destructive" className="my-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Dataset validation must be completed before creating enriched
                    versions. Please go to the Configuration tab to validate.
                </AlertDescription>
            </Alert>
        );
    }

    // Show warning if mapping not ready
    if (!mappingReady) {
        return (
            <Alert variant="destructive" className="my-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                    Dataset must have <code>build_id</code> and{" "}
                    <code>repo_name</code> columns mapped before enrichment.
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header with Create Button */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold">Dataset Enrichment</h2>
                    <p className="text-sm text-muted-foreground">
                        Create enriched versions of your dataset with extracted features
                    </p>
                </div>
                <Button
                    onClick={handleCreateVersion}
                    disabled={hasActiveVersion}
                    className="gap-2"
                >
                    <Sparkles className="h-4 w-4" />
                    Create New Version
                </Button>
            </div>

            {/* Error Alert */}
            {error && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            {/* Active Version Progress */}
            {activeVersion && (
                <ActiveVersionCard version={activeVersion} onCancel={handleCancel} />
            )}

            {/* Version History Table */}
            <VersionHistoryTable
                datasetId={datasetId}
                versions={versions}
                loading={loading}
                onRefresh={refresh}
                onDownload={downloadVersion}
                onDelete={deleteVersion}
            />
        </div>
    );
}

interface ActiveVersionCardProps {
    version: {
        id: string;
        name: string;
        progress_percent: number;
        processed_rows: number;
        total_rows: number;
        failed_rows: number;
    };
    onCancel: (versionId: string) => void;
}

function ActiveVersionCard({ version, onCancel }: ActiveVersionCardProps) {
    return (
        <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        Processing: {version.name}
                    </CardTitle>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onCancel(version.id)}
                        className="text-destructive hover:text-destructive"
                    >
                        <X className="mr-1 h-4 w-4" />
                        Cancel
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-2">
                <Progress value={version.progress_percent} className="h-2" />
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                        {version.processed_rows.toLocaleString()} /{" "}
                        {version.total_rows.toLocaleString()} rows
                    </span>
                    <span>{version.progress_percent.toFixed(1)}%</span>
                </div>
                {version.failed_rows > 0 && (
                    <p className="text-sm text-amber-600">
                        ⚠️ {version.failed_rows} rows failed
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
