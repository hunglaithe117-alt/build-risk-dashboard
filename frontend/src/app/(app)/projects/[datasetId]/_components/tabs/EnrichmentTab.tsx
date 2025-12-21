"use client";

import { useCallback, useState } from "react";
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
import { CreateVersionModal } from "../FeatureSelection/CreateVersionModal";
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
    const [isModalOpen, setIsModalOpen] = useState(false);

    const {
        versions,
        activeVersion,
        loading,
        creating,
        error,
        refresh,
        createVersion,
        cancelVersion,
        deleteVersion,
        downloadVersion,
    } = useDatasetVersions(datasetId);

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

    // Handle create version
    const handleCreateVersion = async (
        features: string[],
        featureConfigs: {
            global: Record<string, unknown>;
            repos: Record<string, Record<string, string[]>>;
        },
        scanData: {
            metrics: { sonarqube: string[]; trivy: string[] };
            config: {
                sonarqube: { projectKey?: string; sonarToken?: string; sonarUrl?: string; extraProperties?: string };
                trivy: { severity?: string; scanners?: string; extraArgs?: string };
            };
        },
        name?: string
    ) => {
        const flatConfigs: Record<string, unknown> = {
            ...featureConfigs.global,
            repo_configs: featureConfigs.repos,
        };
        const version = await createVersion({
            selected_features: features,
            feature_configs: flatConfigs,
            scan_metrics: scanData.metrics,
            scan_config: scanData.config,
            name,
        });
        if (version) {
            notifyParent();
        }
    };

    // Handle cancel
    const handleCancel = async (versionId: string) => {
        await cancelVersion(versionId);
        notifyParent();
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
                    onClick={() => setIsModalOpen(true)}
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

            {/* Create Version Modal */}
            <CreateVersionModal
                datasetId={datasetId}
                rowCount={dataset.rows || 0}
                open={isModalOpen}
                onOpenChange={setIsModalOpen}
                onCreateVersion={handleCreateVersion}
                isCreating={creating}
                hasActiveVersion={hasActiveVersion}
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
