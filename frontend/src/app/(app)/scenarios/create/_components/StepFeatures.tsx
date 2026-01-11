"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    ArrowRight,
    ArrowLeft,
    Check,
    Loader2,
    Settings2,
    LayoutDashboard,
    Box,
    CheckSquare,
    AlertTriangle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { useToast } from "@/components/ui/use-toast";

import { useFeatureSelector } from "@/components/features";
import { FeatureConfigForm, type FeatureConfigsData } from "@/components/features/config/FeatureConfigForm";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    TemplateSelector,
    ViewToggle,
} from "@/components/features/selection";

import { ScanSelectionPanel, type EnabledTools } from "@/components/sonar/scan-selection-panel";
import { ScanPropertiesPanel } from "@/components/sonar/scan-properties-panel";
import { DEFAULT_SCAN_CONFIG, type ScanConfig } from "@/components/sonar/scan-config-panel";

import { useWizard } from "./WizardContext";

const DEFAULT_ENABLED_TOOLS: EnabledTools = {
    sonarqube: false,
    trivy: false,
};

// Hook to detect languages for repos
function useRepoLanguages(repos: Array<{ id: string; full_name: string }>) {
    const [repoLanguages, setRepoLanguages] = useState<Record<string, string[]>>({});
    const [loading, setLoading] = useState<Record<string, boolean>>({});

    useEffect(() => {
        if (repos.length === 0) return;

        const detectLanguagesForRepos = async () => {
            for (const repo of repos) {
                // Skip if already loaded or loading
                if (repoLanguages[repo.id] !== undefined || loading[repo.id]) {
                    continue;
                }

                setLoading(prev => ({ ...prev, [repo.id]: true }));
                try {
                    // Import dynamically to avoid circular deps
                    const { reposApi } = await import("@/lib/api");
                    const result = await reposApi.detectLanguages(repo.full_name);
                    setRepoLanguages(prev => ({
                        ...prev,
                        [repo.id]: result.languages.map((l: string) => l.toLowerCase()),
                    }));
                } catch (err) {
                    console.error(`Failed to detect languages for ${repo.full_name}:`, err);
                    setRepoLanguages(prev => ({ ...prev, [repo.id]: [] }));
                } finally {
                    setLoading(prev => ({ ...prev, [repo.id]: false }));
                }
            }
        };

        detectLanguagesForRepos();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [repos]);

    return { repoLanguages, loading };
}

export function StepFeatures() {
    const {
        state,
        updateFeatures,
        setStep,
        setFeatureConfigs: setFeatureConfigsContext,
        setScanConfigs: setScanConfigsContext
    } = useWizard();
    const { features, previewStats, previewRepos } = state;
    const { toast } = useToast();

    // Local state for UI
    const [activeTab, setActiveTab] = useState<"selection" | "configuration">("selection");
    const [viewMode, setViewMode] = useState<"graph" | "list">("graph");

    // Scan state
    const [enabledTools, setEnabledTools] = useState<EnabledTools>(DEFAULT_ENABLED_TOOLS);
    // Initialize scan config from context or default
    const [scanConfig, setScanConfig] = useState<ScanConfig>(
        Object.keys(state.scanConfigs).length > 0
            ? state.scanConfigs as ScanConfig
            : DEFAULT_SCAN_CONFIG
    );

    // Initialize feature selector with state from wizard context
    const {
        extractorNodes,
        dagData,
        allFeatures,
        loading,
        selectedFeatures,
        expandedNodes,
        searchQuery,
        toggleFeature,
        toggleNodeExpand,
        clearSelection,
        selectAllAvailable,
        setSearchQuery,
        filteredNodes,
        applyTemplate,
    } = useFeatureSelector(new Set(state.features.dag_features));

    // Handle features change from graph view
    const handleGraphFeaturesChange = useCallback(
        (featuresList: string[]) => {
            const currentSet = selectedFeatures;
            const newSet = new Set(featuresList);
            newSet.forEach((f) => {
                if (!currentSet.has(f)) toggleFeature(f);
            });
            currentSet.forEach((f) => {
                if (!newSet.has(f)) toggleFeature(f);
            });
        },
        [selectedFeatures, toggleFeature]
    );

    // Scan metrics state
    const [scanMetrics, setScanMetrics] = useState({
        sonarqube: state.features.scan_metrics.sonarqube,
        trivy: state.features.scan_metrics.trivy,
    });

    // Feature configs local state
    const [featureConfigs, setFeatureConfigs] = useState<FeatureConfigsData>(
        Object.keys(state.featureConfigs).length > 0
            ? state.featureConfigs as FeatureConfigsData
            : { global: {}, repos: {} }
    );

    // Fetch repo languages for feature config
    const repoLangInput = useMemo(() => previewRepos?.map(r => ({
        id: r.id,
        full_name: r.full_name,
    })) || [], [previewRepos]);
    const { repoLanguages } = useRepoLanguages(repoLangInput);

    const handleNext = () => {
        if (selectedFeatures.size === 0 && !enabledTools.sonarqube && !enabledTools.trivy) {
            toast({
                title: "No selection",
                description: "Please select at least one feature or enable a scanner.",
                variant: "destructive",
            });
            return;
        }

        // Update context
        updateFeatures({
            dag_features: Array.from(selectedFeatures),
            scan_metrics: scanMetrics,
        });

        // Save detailed configs
        setFeatureConfigsContext(featureConfigs);
        setScanConfigsContext(scanConfig);

        setStep(3);
    };

    const handleClearScanMetrics = () => {
        setScanMetrics({ sonarqube: [], trivy: [] });
    };

    const hasSelection =
        selectedFeatures.size > 0 ||
        enabledTools.sonarqube ||
        scanMetrics.sonarqube.length > 0 ||
        enabledTools.trivy ||
        scanMetrics.trivy.length > 0;

    return (
        <div className="space-y-6 h-[calc(100vh-250px)] min-h-[600px] flex flex-col">
            {/* Toolbar / Tabs */}
            <div className="flex items-center justify-between gap-4 flex-shrink-0">
                <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-[400px]">
                    <TabsList>
                        <TabsTrigger value="selection" className="flex-1">
                            <LayoutDashboard className="h-4 w-4 mr-2" />
                            Selection
                        </TabsTrigger>
                        <TabsTrigger value="configuration" className="flex-1" disabled={!hasSelection}>
                            <Settings2 className="h-4 w-4 mr-2" />
                            Configuration
                        </TabsTrigger>
                    </TabsList>
                </Tabs>

                <div className="flex items-center gap-2">
                    <Button variant="outline" onClick={() => setStep(1)}>
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back
                    </Button>
                    <Button onClick={handleNext} disabled={!hasSelection}>
                        Next: Splitting
                        <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 border rounded-lg overflow-hidden bg-background shadow-sm">
                {activeTab === "selection" ? (
                    <ResizablePanelGroup direction="vertical" className="h-full w-full">
                        {/* Top: Visualization (60%) */}
                        <ResizablePanel defaultSize={60} minSize={30}>
                            <div className="flex flex-col h-full relative bg-slate-50/50 dark:bg-slate-950/50">
                                {/* Vis Toolbar */}
                                <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
                                    <div className="pointer-events-auto">
                                        <TemplateSelector onApplyTemplate={applyTemplate} />
                                    </div>
                                    <div className="pointer-events-auto flex items-center gap-2 bg-background/80 backdrop-blur-sm p-1 rounded-lg shadow-sm">
                                        <ViewToggle value={viewMode} onChange={setViewMode} />
                                    </div>
                                </div>

                                {/* Vis Content */}
                                <div className="flex-1 overflow-hidden pt-16">
                                    {loading ? (
                                        <div className="flex h-full items-center justify-center">
                                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                        </div>
                                    ) : viewMode === "graph" ? (
                                        <GraphView
                                            dagData={dagData}
                                            selectedFeatures={selectedFeatures}
                                            onFeaturesChange={handleGraphFeaturesChange}
                                            isLoading={loading}
                                        />
                                    ) : (
                                        <div className="h-full overflow-y-auto p-4 md:p-6">
                                            <div className="max-w-4xl mx-auto bg-background rounded-lg border shadow-sm">
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
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </ResizablePanel>

                        <ResizableHandle withHandle />

                        {/* Bottom: Panels (40%) */}
                        <ResizablePanel defaultSize={40} minSize={20}>
                            <ResizablePanelGroup direction="horizontal">
                                {/* Selected Features */}
                                <ResizablePanel defaultSize={50} minSize={30}>
                                    <div className="h-full flex flex-col bg-background">
                                        <div className="px-4 py-2 border-b bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-between flex-shrink-0">
                                            <div className="flex items-center gap-2 font-medium text-sm">
                                                Features
                                                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
                                                    {selectedFeatures.size}
                                                </Badge>
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={selectAllAvailable}
                                                    className="h-7 text-xs text-muted-foreground hover:text-foreground px-2"
                                                >
                                                    Select All
                                                </Button>
                                                <div className="w-px h-3 bg-border mx-1" />
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={clearSelection}
                                                    className="h-7 text-xs text-muted-foreground hover:text-destructive px-2"
                                                >
                                                    Clear All
                                                </Button>
                                            </div>
                                        </div>
                                        <div className="flex-1 overflow-y-auto">
                                            <SelectedFeaturesPanel
                                                selectedFeatures={selectedFeatures}
                                                allFeatures={allFeatures}
                                                nodes={extractorNodes}
                                                onRemoveFeature={toggleFeature}
                                                onClearAll={clearSelection}
                                                rowCount={0}
                                                className="border-none shadow-none h-full rounded-none"
                                                hideHeader={true}
                                            />
                                        </div>
                                    </div>
                                </ResizablePanel>

                                <ResizableHandle withHandle />

                                {/* Scan Metrics */}
                                <ResizablePanel defaultSize={50} minSize={30}>
                                    <div className="h-full flex flex-col bg-background">
                                        <div className="px-4 py-2 border-b bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-between flex-shrink-0">
                                            <div className="flex items-center gap-2 font-medium text-sm">
                                                Scans
                                                {(scanMetrics.sonarqube.length > 0 || scanMetrics.trivy.length > 0) && (
                                                    <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
                                                        {scanMetrics.sonarqube.length + scanMetrics.trivy.length}
                                                    </Badge>
                                                )}
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={handleClearScanMetrics}
                                                className="h-7 text-xs text-muted-foreground hover:text-destructive px-2"
                                            >
                                                Clear All
                                            </Button>
                                        </div>
                                        <div className="flex-1 overflow-y-auto p-4">
                                            <ScanSelectionPanel
                                                selectedSonarMetrics={scanMetrics.sonarqube}
                                                selectedTrivyMetrics={scanMetrics.trivy}
                                                onSonarMetricsChange={(metrics) =>
                                                    setScanMetrics((prev) => ({ ...prev, sonarqube: metrics }))
                                                }
                                                onTrivyMetricsChange={(metrics) =>
                                                    setScanMetrics((prev) => ({ ...prev, trivy: metrics }))
                                                }
                                                enabledTools={enabledTools}
                                                onEnabledToolsChange={setEnabledTools}
                                            />
                                        </div>
                                    </div>
                                </ResizablePanel>
                            </ResizablePanelGroup>
                        </ResizablePanel>
                    </ResizablePanelGroup>
                ) : (
                    <div className="flex h-full overflow-hidden">
                        {/* Config Sidebar/Tabs */}
                        <Tabs defaultValue="features" className="flex-1 flex flex-col overflow-hidden">
                            <div className="flex-shrink-0 px-6 pt-4 border-b bg-slate-50/50 dark:bg-slate-900/50">
                                <TabsList className="bg-transparent p-0 h-auto gap-6 -mb-px">
                                    <TabsTrigger
                                        value="features"
                                        disabled={selectedFeatures.size === 0}
                                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-purple-600 data-[state=active]:bg-transparent pb-3"
                                    >
                                        Feature Config
                                    </TabsTrigger>
                                    <TabsTrigger
                                        value="scans"
                                        disabled={!enabledTools.sonarqube && !enabledTools.trivy}
                                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:bg-transparent pb-3"
                                    >
                                        Scan Config
                                    </TabsTrigger>
                                </TabsList>
                            </div>

                            <div className="flex-1 overflow-y-auto p-6 bg-slate-50/30 dark:bg-slate-950/30">
                                <div className="max-w-4xl mx-auto space-y-6">
                                    <TabsContent value="features" className="m-0">
                                        <FeatureConfigForm
                                            selectedFeatures={selectedFeatures}
                                            value={featureConfigs}
                                            onChange={setFeatureConfigs}
                                            repos={previewRepos}
                                            repoLanguages={repoLanguages}
                                            showValidationStatusColumn={false}
                                        />
                                    </TabsContent>

                                    <TabsContent value="scans" className="m-0">
                                        <ScanPropertiesPanel
                                            scanConfig={scanConfig}
                                            onScanConfigChange={setScanConfig}
                                            enabledTools={enabledTools}
                                            repos={previewRepos}
                                        />
                                    </TabsContent>
                                </div>
                            </div>
                        </Tabs>
                    </div>
                )}
            </div>
        </div>
    );
}
