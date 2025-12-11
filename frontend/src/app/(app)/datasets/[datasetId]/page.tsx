"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    Database,
    Loader2,
    Plug,
    Settings,
    Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { datasetsApi } from "@/lib/api";
import type { DatasetRecord } from "@/types";

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
    const [hasActiveEnrichment, setHasActiveEnrichment] = useState(false);

    const loadDataset = useCallback(async () => {
        try {
            const data = await datasetsApi.get(datasetId);

            // Redirect to datasets page if validation not completed
            if (data.validation_status !== "completed") {
                router.replace("/datasets");
                return;
            }

            setDataset(data);
            setError(null);
        } catch (err) {
            console.error(err);
            setError("Unable to load dataset details.");
        } finally {
            setLoading(false);
        }
    }, [datasetId, router]);

    useEffect(() => {
        loadDataset();
    }, [loadDataset]);

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
                            <TabsTrigger value="enrichment" className="gap-2">
                                <Zap className="h-4 w-4" />
                                Enrichment
                                {hasActiveEnrichment && (
                                    <Badge variant="secondary" className="ml-1 text-xs animate-pulse">
                                        Active
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="configuration" className="gap-2">
                                <Settings className="h-4 w-4" />
                                Configuration
                            </TabsTrigger>
                            <TabsTrigger value="integrations" className="gap-2">
                                <Plug className="h-4 w-4" />
                                Integrations
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="overview" className="mt-6">
                            <OverviewTab dataset={dataset} onRefresh={loadDataset} />
                        </TabsContent>

                        <TabsContent value="enrichment" className="mt-6">
                            <EnrichmentTab
                                datasetId={datasetId}
                                dataset={dataset}
                                onEnrichmentStatusChange={setHasActiveEnrichment}
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
                                sonarFeatures={[]}
                                trivyFeatures={[]}
                            />
                        </TabsContent>
                    </Tabs>
                </div>

                {/* Sidebar */}
                <DatasetSidebar
                    dataset={dataset}
                    onEditConfig={() => setActiveTab("enrichment")}
                    onDelete={handleDelete}
                    onRefresh={loadDataset}
                />
            </div>
        </div>
    );
}
