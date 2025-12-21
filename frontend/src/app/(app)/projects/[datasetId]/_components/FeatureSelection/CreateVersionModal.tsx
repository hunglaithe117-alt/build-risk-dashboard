"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Loader2, Sparkles, Zap } from "lucide-react";
import { useFeatureSelector } from "@/components/features";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    ViewToggle,
    TemplateSelector,
} from "@/components/features/FeatureSelection";
import { FeatureConfigForm } from "./FeatureConfigForm";
import {
    ScanConfigPanel,
    DEFAULT_SCAN_CONFIG,
    type ScanConfig,
} from "@/components/sonar/scan-config-panel";

/** Structure for configs from FeatureConfigForm */
interface FeatureConfigsData {
    global: Record<string, unknown>;
    repos: Record<string, Record<string, string[]>>;
}

/** Scan metrics selection */
interface ScanMetricsData {
    sonarqube: string[];
    trivy: string[];
}

/** Full scan data including metrics and config */
interface ScanData {
    metrics: ScanMetricsData;
    config: ScanConfig;
}

interface CreateVersionModalProps {
    datasetId: string;
    rowCount: number;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onCreateVersion: (
        features: string[],
        featureConfigs: FeatureConfigsData,
        scanData: ScanData,
        name?: string
    ) => Promise<void>;
    isCreating: boolean;
    hasActiveVersion: boolean;
}

export function CreateVersionModal({
    datasetId,
    rowCount,
    open,
    onOpenChange,
    onCreateVersion,
    isCreating,
    hasActiveVersion,
}: CreateVersionModalProps) {
    const [viewMode, setViewMode] = useState<"graph" | "list">("graph");
    const [versionName, setVersionName] = useState("");
    const [featureConfigs, setFeatureConfigs] = useState<FeatureConfigsData>({
        global: {},
        repos: {},
    });
    const [scanMetrics, setScanMetrics] = useState<ScanMetricsData>({
        sonarqube: [],
        trivy: [],
    });
    const [scanConfig, setScanConfig] = useState<ScanConfig>(DEFAULT_SCAN_CONFIG);

    const {
        extractorNodes,
        dagData,
        allFeatures,
        loading,
        selectedFeatures,
        expandedNodes,
        searchQuery,
        toggleFeature,
        toggleNode,
        toggleNodeExpand,
        clearSelection,
        setSearchQuery,
        filteredNodes,
        applyTemplate,
    } = useFeatureSelector();

    // Handle features change from graph view
    const handleGraphFeaturesChange = useCallback(
        (features: string[]) => {
            const newSet = new Set(features);
            const currentSet = selectedFeatures;

            features.forEach((feature) => {
                if (!currentSet.has(feature)) toggleFeature(feature);
            });
            currentSet.forEach((feature) => {
                if (!newSet.has(feature)) toggleFeature(feature);
            });
        },
        [selectedFeatures, toggleFeature]
    );

    // Handle create version
    const handleCreateVersion = async () => {
        if (selectedFeatures.size === 0) return;

        await onCreateVersion(
            Array.from(selectedFeatures),
            featureConfigs,
            { metrics: scanMetrics, config: scanConfig },
            versionName || undefined
        );

        // Reset form
        setVersionName("");
        setFeatureConfigs({ global: {}, repos: {} });
        setScanMetrics({ sonarqube: [], trivy: [] });
        setScanConfig(DEFAULT_SCAN_CONFIG);
        clearSelection();
        onOpenChange(false);
    };

    const handleCancel = () => {
        clearSelection();
        setVersionName("");
        onOpenChange(false);
    };

    const isDisabled = isCreating || hasActiveVersion || selectedFeatures.size === 0;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5" />
                        Create New Version
                    </DialogTitle>
                    <DialogDescription>
                        Select features to include in the enriched dataset
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* View Toggle */}
                    <div className="flex items-center justify-between">
                        <TemplateSelector
                            onApplyTemplate={applyTemplate}
                            disabled={isCreating || hasActiveVersion}
                        />
                        <ViewToggle value={viewMode} onChange={setViewMode} />
                    </div>

                    {/* Graph or List View */}
                    <div className="min-h-[300px]">
                        {viewMode === "graph" ? (
                            <GraphView
                                dagData={dagData}
                                selectedFeatures={selectedFeatures}
                                onFeaturesChange={handleGraphFeaturesChange}
                                isLoading={loading}
                            />
                        ) : (
                            <ListView
                                nodes={filteredNodes}
                                selectedFeatures={selectedFeatures}
                                expandedNodes={expandedNodes}
                                onToggleFeature={toggleFeature}
                                onToggleNode={toggleNode}
                                onToggleNodeExpand={toggleNodeExpand}
                                searchQuery={searchQuery}
                                onSearchChange={setSearchQuery}
                                isLoading={loading}
                            />
                        )}
                    </div>

                    {/* Selected Features Panel */}
                    <SelectedFeaturesPanel
                        selectedFeatures={selectedFeatures}
                        allFeatures={allFeatures}
                        nodes={extractorNodes}
                        onRemoveFeature={toggleFeature}
                        onClearAll={clearSelection}
                        rowCount={rowCount}
                    />

                    {/* Feature Configuration Form */}
                    <FeatureConfigForm
                        datasetId={datasetId}
                        selectedFeatures={selectedFeatures}
                        onChange={setFeatureConfigs}
                        disabled={isDisabled}
                    />

                    {/* Scan Configuration & Metrics Selection */}
                    <ScanConfigPanel
                        selectedSonarMetrics={scanMetrics.sonarqube}
                        selectedTrivyMetrics={scanMetrics.trivy}
                        onSonarMetricsChange={(metrics) =>
                            setScanMetrics((prev) => ({ ...prev, sonarqube: metrics }))
                        }
                        onTrivyMetricsChange={(metrics) =>
                            setScanMetrics((prev) => ({ ...prev, trivy: metrics }))
                        }
                        scanConfig={scanConfig}
                        onScanConfigChange={setScanConfig}
                        disabled={isDisabled}
                    />

                    {/* Version Name Input */}
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Version Name (optional)</label>
                        <Input
                            placeholder="e.g., 'v3 - Git + Build Logs'"
                            value={versionName}
                            onChange={(e) => setVersionName(e.target.value)}
                            disabled={isDisabled}
                        />
                    </div>

                    {hasActiveVersion && (
                        <p className="text-center text-sm text-amber-600 dark:text-amber-400">
                            ⏳ A version is currently processing. Wait for it to complete or cancel it.
                        </p>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleCancel} disabled={isCreating}>
                        Cancel
                    </Button>
                    <Button onClick={handleCreateVersion} disabled={isDisabled} className="gap-2">
                        {isCreating ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Creating...
                            </>
                        ) : (
                            <>
                                <Zap className="h-4 w-4" />
                                Create Version
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
