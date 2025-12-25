"use client";

import { useState, useCallback, useEffect } from "react";
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
import { Loader2, Sparkles, Zap, X } from "lucide-react";
import { useFeatureSelector } from "@/components/features";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    ViewToggle,
    TemplateSelector,
} from "@/components/features/selection";
import { FeatureConfigForm, type FeatureConfigsData } from "@/components/features/config/FeatureConfigForm";
import { ScanConfigPanel, type ScanConfig } from "@/components/sonar/scan-config-panel";
import { useScanConfig } from "./useScanConfig";
import { datasetsApi } from "@/lib/api";


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

interface RepoInfo {
    id: string;
    full_name: string;
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
    const [repos, setRepos] = useState<RepoInfo[]>([]);

    // Fetch repos for per-repo scan config
    useEffect(() => {
        if (!open || !datasetId) return;

        async function fetchRepos() {
            try {
                const summary = await datasetsApi.getValidationSummary(datasetId);
                if (summary.repos) {
                    setRepos(summary.repos.map(r => ({
                        // Use github_repo_id for scan config (backend uses this as key)
                        id: String(r.github_repo_id || r.id),
                        full_name: r.full_name,
                    })));
                }
            } catch (err) {
                console.error("Failed to fetch repos:", err);
            }
        }
        fetchRepos();
    }, [open, datasetId]);

    // Use custom hook to fetch and manage scan config with backend defaults
    // Fetch only when modal is open
    const { scanConfig, setScanConfig, resetToDefaults } = useScanConfig({
        fetchOnEnable: true,
        enabled: open,
    });

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
            // Convert array to toggle operations
            const currentSet = selectedFeatures;
            const newSet = new Set(features);

            // Add new features
            newSet.forEach((f) => {
                if (!currentSet.has(f)) toggleFeature(f);
            });

            // Remove deselected features
            currentSet.forEach((f) => {
                if (!newSet.has(f)) toggleFeature(f);
            });
        },
        [selectedFeatures, toggleFeature]
    );

    const handleCreateVersion = async () => {
        await onCreateVersion(
            Array.from(selectedFeatures),
            featureConfigs,
            { metrics: scanMetrics, config: scanConfig },
            versionName || undefined
        );
        // Reset after creation
        resetToDefaults(); // Reset to backend defaults instead of hardcoded
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
            <DialogContent className="max-h-[90vh] max-w-5xl flex flex-col p-0 gap-0">
                {/* Sticky Header */}
                <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
                    {/* Close button */}
                    <button
                        onClick={() => onOpenChange(false)}
                        className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    >
                        <X className="h-4 w-4" />
                        <span className="sr-only">Close</span>
                    </button>

                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Sparkles className="h-5 w-5" />
                            Create New Version
                        </DialogTitle>
                        <DialogDescription>
                            Select features to include in the enriched dataset
                        </DialogDescription>
                    </DialogHeader>

                    {/* View Toggle - part of sticky header */}
                    <div className="flex items-center justify-between gap-4 mt-4">
                        <div className="flex-1 min-w-0">
                            <TemplateSelector
                                onApplyTemplate={applyTemplate}
                                disabled={isCreating || hasActiveVersion}
                            />
                        </div>
                        <ViewToggle value={viewMode} onChange={setViewMode} />
                    </div>
                </div>

                {/* Scrollable Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
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
                                onToggleNode={toggleNodeExpand}
                                onToggleNodeExpand={toggleNodeExpand}
                                searchQuery={searchQuery}
                                onSearchChange={setSearchQuery}
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
                        repos={repos}
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

                {/* Sticky Footer */}
                <div className="sticky bottom-0 z-10 bg-background border-t px-6 py-4">
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
                </div>
            </DialogContent>
        </Dialog>
    );
}
