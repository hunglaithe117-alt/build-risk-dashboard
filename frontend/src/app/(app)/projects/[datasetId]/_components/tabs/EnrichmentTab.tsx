"use client";

import { useCallback, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2, Sparkles } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useWebSocket } from "@/contexts/websocket-context";
import type { DatasetRecord } from "@/types";

import { VersionHistoryTable } from "../VersionHistoryTable";
import { useDatasetVersions } from "../../_hooks/useDatasetVersions";

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
        deleteVersion,
    } = useDatasetVersions(datasetId);

    // WebSocket subscription for real-time updates
    useEffect(() => {
        const unsubscribe = subscribe("ENRICHMENT_UPDATE", (data: {
            version_id: string;
        }) => {
            const isOurVersion = versions.some((v) => v.id === data.version_id);
            if (isOurVersion) {
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

    useEffect(() => {
        notifyParent();
    }, [notifyParent]);

    const handleCreateVersion = () => {
        router.push(`/projects/${datasetId}/versions/new`);
    };

    const isValidated = dataset.validation_status === "completed";
    const mappingReady = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

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

            {error && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            <VersionHistoryTable
                datasetId={datasetId}
                versions={versions}
                loading={loading}
                onRefresh={refresh}
                onDelete={deleteVersion}
            />
        </div>
    );
}
