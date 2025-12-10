"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    Database,
    FileSpreadsheet,
    Loader2,
    Plug,
    Settings,
    Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { datasetsApi, enrichmentApi } from "@/lib/api";
import type { DatasetRecord, EnrichmentJob } from "@/types";

import { DatasetHeader } from "./_components/DatasetHeader";
import { DatasetSidebar } from "./_components/DatasetSidebar";
import { OverviewTab, EnrichmentTab, ConfigurationTab, IntegrationsTab } from "./_components/tabs";
import {
    Card,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

export default function DatasetDetailPage() {
    const params = useParams();
    const router = useRouter();
    const datasetId = params.datasetId as string;

    const [dataset, setDataset] = useState<DatasetRecord | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState("overview");
    const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentJob | null>(null);
    const [enrichmentLoading, setEnrichmentLoading] = useState(false);

    const loadDataset = useCallback(async () => {
        try {
            const data = await datasetsApi.get(datasetId);
            setDataset(data);
            setError(null);
        } catch (err) {
            console.error(err);
            setError("Unable to load dataset details.");
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    useEffect(() => {
        loadDataset();
    }, [loadDataset]);

    const handleDownload = async () => {
        try {
            const blob = await enrichmentApi.download(datasetId);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `enriched_${dataset?.file_name || "dataset"}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (err) {
            console.error("Download failed:", err);
        }
    };

    const handleStartEnrichment = async () => {
        try {
            setEnrichmentLoading(true);
            await enrichmentApi.start(datasetId, {
                selected_features: dataset?.selected_features || [],
                auto_import_repos: true,
            });
            // Refresh to get latest status
            loadDataset();
        } catch (err) {
            console.error("Failed to start enrichment:", err);
        } finally {
            setEnrichmentLoading(false);
        }
    };

    const handleDelete = async () => {
        if (!confirm(`Delete dataset "${dataset?.name}"? This cannot be undone.`)) {
            return;
        }
        try {
            await datasetsApi.delete(datasetId);
            router.push("/datasets");
        } catch (err) {
            console.error("Failed to delete dataset:", err);
        }
    };

    // Configuration status
    const hasMapping = Boolean(dataset?.mapped_fields?.build_id && dataset?.mapped_fields?.repo_name);
    const hasFeatures = (dataset?.selected_features?.length || 0) > 0;
    const isFullyConfigured = hasMapping && hasFeatures;

    // Count features by category
    const sonarFeatures = dataset?.selected_features?.filter(f => f.startsWith("sonar_")) || [];
    const trivyFeatures = dataset?.selected_features?.filter(f => f.startsWith("trivy_")) || [];
    const regularFeatures = dataset?.selected_features?.filter(f => !f.startsWith("sonar_") && !f.startsWith("trivy_")) || [];

    if (loading) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !dataset) {
        return (
            <div className="space-y-4">
                <Button variant="ghost" onClick={() => router.back()} className="gap-2">
                    <ArrowLeft className="h-4 w-4" /> Back
                </Button>
                <Card className="border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
                    <CardHeader>
                        <CardTitle className="text-red-700 dark:text-red-300">Error</CardTitle>
                        <CardDescription>{error || "Dataset not found"}</CardDescription>
                    </CardHeader>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <DatasetHeader
                dataset={dataset}
                onRefresh={loadDataset}
                onDownload={handleDownload}
            />

            {/* Main Content with Sidebar */}
            <div className="flex gap-6">
                {/* Main Content Area */}
                <div className="flex-1 min-w-0">
                    <Tabs value={activeTab} onValueChange={setActiveTab}>
                        <TabsList className="grid w-full grid-cols-4">
                            <TabsTrigger value="overview" className="gap-2">
                                <Database className="h-4 w-4" />
                                Overview
                            </TabsTrigger>
                            <TabsTrigger
                                value="enrichment"
                                className="gap-2"
                                disabled={!isFullyConfigured}
                            >
                                <Zap className="h-4 w-4" />
                                Enrichment
                                {regularFeatures.length > 0 && (
                                    <Badge variant="secondary" className="ml-1 text-xs">
                                        {regularFeatures.length}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="configuration" className="gap-2">
                                <Settings className="h-4 w-4" />
                                Configuration
                            </TabsTrigger>
                            <TabsTrigger
                                value="integrations"
                                className="gap-2"
                                disabled={!isFullyConfigured}
                            >
                                <Plug className="h-4 w-4" />
                                Integrations
                                {sonarFeatures.length > 0 && (
                                    <Badge variant="secondary" className="ml-1 text-xs">
                                        {sonarFeatures.length}
                                    </Badge>
                                )}
                            </TabsTrigger>
                        </TabsList>

                        {/* Configuration Warning Banner */}
                        {!isFullyConfigured && activeTab === "overview" && (
                            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
                                <div className="flex items-center gap-3">
                                    <div className="flex-shrink-0">
                                        <FileSpreadsheet className="h-5 w-5 text-amber-600" />
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                                            Configuration Required
                                        </p>
                                        <p className="text-sm text-amber-700 dark:text-amber-400">
                                            {!hasMapping && "Please complete column mapping. "}
                                            {!hasFeatures && "Please select features to extract."}
                                        </p>
                                    </div>
                                    <Button
                                        size="sm"
                                        className="bg-amber-600 hover:bg-amber-700 text-white"
                                        onClick={() => setActiveTab("configuration")}
                                    >
                                        Configure
                                    </Button>
                                </div>
                            </div>
                        )}

                        <TabsContent value="overview" className="mt-6">
                            <OverviewTab dataset={dataset} onRefresh={loadDataset} />
                        </TabsContent>

                        <TabsContent value="enrichment" className="mt-6">
                            <EnrichmentTab
                                datasetId={datasetId}
                                dataset={dataset}
                                onEnrichmentStatusChange={setEnrichmentStatus}
                            />
                        </TabsContent>

                        <TabsContent value="configuration" className="mt-6">
                            <ConfigurationTab
                                dataset={dataset}
                                onEditMapping={() => router.push(`/datasets?configure=${datasetId}`)}
                                onEditFeatures={() => router.push(`/datasets?configure=${datasetId}`)}
                                onEditSources={() => router.push(`/datasets?configure=${datasetId}`)}
                            />
                        </TabsContent>

                        <TabsContent value="integrations" className="mt-6">
                            <IntegrationsTab
                                datasetId={datasetId}
                                sonarFeatures={sonarFeatures}
                                trivyFeatures={trivyFeatures}
                            />
                        </TabsContent>
                    </Tabs>
                </div>

                {/* Sidebar */}
                <DatasetSidebar
                    dataset={dataset}
                    enrichmentStatus={enrichmentStatus}
                    onStartEnrichment={handleStartEnrichment}
                    onDownload={handleDownload}
                    onEditConfig={() => setActiveTab("configuration")}
                    onDelete={handleDelete}
                    isEnrichmentLoading={enrichmentLoading}
                />
            </div>
        </div>
    );
}
