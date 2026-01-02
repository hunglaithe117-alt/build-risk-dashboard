"use client";

import {
    AlertTriangle,
    ArrowLeft,
    ArrowRight,
    Box,
    CheckSquare,
    LayoutDashboard,
    Loader2,
    Settings,
    Sparkles,
    Zap
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useFeatureSelector } from "@/components/features";
import { FeatureConfigForm, type FeatureConfigsData } from "@/components/features/config/FeatureConfigForm";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    TemplateSelector,
    ViewToggle,
} from "@/components/features/selection";
import { DEFAULT_ENABLED_TOOLS } from "@/components/sonar/scan-config-panel";
import { ScanPropertiesPanel } from "@/components/sonar/scan-properties-panel";
import { ScanSelectionPanel, type EnabledTools } from "@/components/sonar/scan-selection-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/components/ui/use-toast";
import { datasetsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useScanConfig } from "../../_components/FeatureSelection/useScanConfig";

interface PageProps {
    params: {
        datasetId: string;
    };
}

interface ScanMetricsData {
    sonarqube: string[];
    trivy: string[];
}

interface RepoInfo {
    id: string;
    full_name: string;
}

export default function CreateVersionPage({ params }: PageProps) {
    const { datasetId } = params;
    const router = useRouter();

    // State
    const [step, setStep] = useState<1 | 2>(1);
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
    const [enabledTools, setEnabledTools] = useState<EnabledTools>(DEFAULT_ENABLED_TOOLS);
    const [repos, setRepos] = useState<RepoInfo[]>([]);
    const [isCreating, setIsCreating] = useState(false);
    const [hasActiveVersion, setHasActiveVersion] = useState(false);

    // Check for active versions
    useEffect(() => {
        async function checkActiveVersions() {
            try {
                const dataset = await datasetsApi.get(datasetId);
                const response = await datasetsApi.listVersions(datasetId, { limit: 100 });
                const active = response.versions.some((v: any) =>
                    ["queued", "ingesting", "processing"].includes(v.status)
                );
                setHasActiveVersion(active);
            } catch (err) {
                console.error("Failed to check active versions:", err);
            }
        }
        checkActiveVersions();
    }, [datasetId]);

    // Fetch repos for per-repo scan config
    useEffect(() => {
        async function fetchRepos() {
            try {
                const summary = await datasetsApi.getValidationSummary(datasetId);
                if (summary.repos) {
                    setRepos(summary.repos.map(r => ({
                        id: String(r.github_repo_id || r.id),
                        full_name: r.full_name,
                    })));
                }
            } catch (err) {
                console.error("Failed to fetch repos:", err);
            }
        }
        fetchRepos();
    }, [datasetId]);

    // Scan config hook
    const { scanConfig, setScanConfig } = useScanConfig({
        fetchOnEnable: true,
        enabled: true,
    });

    // Feature selection hook
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
    } = useFeatureSelector();

    // Clear all scan metrics
    const handleClearScanMetrics = () => {
        setScanMetrics({
            sonarqube: [],
            trivy: [],
        });
    };

    // Handle features change from graph view
    const handleGraphFeaturesChange = useCallback(
        (features: string[]) => {
            const currentSet = selectedFeatures;
            const newSet = new Set(features);
            newSet.forEach((f) => {
                if (!currentSet.has(f)) toggleFeature(f);
            });
            currentSet.forEach((f) => {
                if (!newSet.has(f)) toggleFeature(f);
            });
        },
        [selectedFeatures, toggleFeature]
    );

    const handleCreateVersion = async () => {
        setIsCreating(true);
        try {
            await datasetsApi.createVersion(datasetId, {
                selected_features: Array.from(selectedFeatures),
                feature_configs: featureConfigs as unknown as Record<string, unknown>,
                scan_config: { metrics: scanMetrics, config: scanConfig },
                name: versionName || undefined,
            });

            toast({
                title: "Version creation started",
                description: "Data collection has started for your new dataset version.",
            });

            router.push(`/projects/${datasetId}?tab=enrichment`);
        } catch (err) {
            console.error("Failed to create version:", err);
            toast({
                title: "Failed to create version",
                description: err instanceof Error ? err.message : "Unknown error",
                variant: "destructive",
            });
        } finally {
            setIsCreating(false);
        }
    };

    const hasSelection = selectedFeatures.size > 0 || enabledTools.sonarqube || scanMetrics.sonarqube.length > 0 || enabledTools.trivy || scanMetrics.trivy.length > 0;
    // canProceedToStep2 logic: allow proceeding if something is selected
    const canProceedToStep2 = hasSelection && !hasActiveVersion;
    const isDisabled = isCreating || hasActiveVersion;

    return (
        <div className="flex h-[calc(100vh-theme(spacing.16))] overflow-hidden -m-6 rounded-none flex-col">
            {/* Steps Header */}
            <div className="flex-shrink-0 bg-background border-b px-6 py-4 flex items-center justify-between z-20 shadow-sm">
                <div className="flex items-center gap-3">
                    <Button variant="ghost" size="icon" className="-ml-2" onClick={() => router.push(`/projects/${datasetId}`)}>
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-lg font-semibold leading-none flex items-center gap-2">
                            Create Version
                        </h1>
                        <nav className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground" aria-label="Breadcrumb">
                            <span className={cn("flex items-center gap-1", step === 1 ? "font-medium text-foreground" : "")}>
                                <div className={cn("w-4 h-4 rounded-full flex items-center justify-center border text-[10px]", step === 1 ? "bg-black border-black text-white" : "border-muted-foreground/30")}>1</div>
                                Selection
                            </span>
                            <span className="text-muted-foreground/30">/</span>
                            <span className={cn("flex items-center gap-1", step === 2 ? "font-medium text-foreground" : "")}>
                                <div className={cn("w-4 h-4 rounded-full flex items-center justify-center border text-[10px]", step === 2 ? "bg-black border-black text-white" : "border-muted-foreground/30")}>2</div>
                                Configuration
                            </span>
                        </nav>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {step === 1 ? (
                        <Button
                            onClick={() => setStep(2)}
                            disabled={!canProceedToStep2}
                            className="bg-black hover:bg-slate-800 text-white transition-colors"
                        >
                            Next: Configure
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    ) : (
                        <>
                            <Button variant="outline" onClick={() => setStep(1)} disabled={isCreating}>
                                Back
                            </Button>
                            <Button
                                onClick={handleCreateVersion}
                                disabled={isDisabled}
                                className="bg-black hover:bg-slate-800 min-w-[140px]"
                            >
                                {isCreating ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Creating...
                                    </>
                                ) : (
                                    <>
                                        <Zap className="mr-2 h-4 w-4" />
                                        Launch Version
                                    </>
                                )}
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {hasActiveVersion && (
                <div className="bg-amber-50 border-b border-amber-200 text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300 py-2 px-6 flex items-center gap-2 text-sm justify-center">
                    <AlertTriangle className="h-4 w-4" />
                    A version is currently running. Wait for data collection or feature extraction to finish.
                </div>
            )}

            {/* STEP 1: SELECTION (Full Screen Graph + Split Bottom) */}
            {step === 1 && (
                <div className="flex-1 flex overflow-hidden">
                    <ResizablePanelGroup direction="vertical" className="h-full w-full">
                        {/* Top: Graph Area (Default 65%) */}
                        <ResizablePanel defaultSize={65} minSize={30}>
                            <div className="flex flex-col h-full relative bg-slate-50/50 dark:bg-slate-950/50">
                                {/* Toolbar Area */}
                                <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between pointer-events-none">
                                    {/* Left: Template Selector */}
                                    <div className="pointer-events-auto">
                                        <TemplateSelector
                                            onApplyTemplate={applyTemplate}
                                            disabled={hasActiveVersion}
                                        />
                                    </div>

                                    {/* Right: View Toggle */}
                                    <div className="pointer-events-auto flex items-center gap-2 bg-background/80 backdrop-blur-sm p-1 rounded-lg shadow-sm">
                                        <ViewToggle value={viewMode} onChange={setViewMode} />
                                    </div>
                                </div>

                                {/* Visualization */}
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

                        {/* Bottom: Selection Area (Split Features / Scans) */}
                        <ResizablePanel defaultSize={35} minSize={20}>
                            <ResizablePanelGroup direction="horizontal">
                                {/* Left: Selected Features */}
                                <ResizablePanel defaultSize={50} minSize={30}>
                                    <div className="h-full flex flex-col bg-background">
                                        <div className="px-4 py-2 border-b bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-between flex-shrink-0">
                                            <div className="flex items-center gap-2 font-medium text-sm">
                                                Selected Features
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
                                        {/* Default features info note */}
                                        <div className="px-4 py-2 bg-blue-50 dark:bg-blue-900/20 border-b text-xs text-blue-700 dark:text-blue-300">
                                            <span className="font-medium">Note:</span> 3 default features are always included: <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">tr_build_id</code>, <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">gh_project_name</code>, <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">ci_provider</code>
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

                                {/* Right: Scan Metrics */}
                                <ResizablePanel defaultSize={50} minSize={30}>
                                    <div className="h-full flex flex-col bg-background">
                                        <div className="px-4 py-2 border-b bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-between flex-shrink-0">
                                            <div className="flex items-center gap-2 font-medium text-sm">
                                                Selected Scan Metrics
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
                                                disabled={hasActiveVersion}
                                            />
                                        </div>
                                    </div>
                                </ResizablePanel>
                            </ResizablePanelGroup>
                        </ResizablePanel>
                    </ResizablePanelGroup>
                </div>
            )}

            {/* STEP 2: CONFIGURATION */}
            {step === 2 && (
                <div className="flex-1 flex overflow-hidden">
                    {/* Left: Configuration Forms */}
                    {/* Left: Configuration Forms (Tabbed) */}
                    <Tabs defaultValue="features" className="flex-1 flex flex-col overflow-hidden bg-slate-50/50 dark:bg-slate-950/50">
                        <div className="flex-shrink-0 px-8 pt-6 pb-0 bg-background border-b z-10">
                            <TabsList className="w-full justify-start gap-6 bg-transparent p-0 h-auto rounded-none border-b-0">
                                <TabsTrigger
                                    value="features"
                                    disabled={selectedFeatures.size === 0}
                                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-purple-600 data-[state=active]:shadow-none data-[state=active]:bg-transparent px-4 py-3 font-medium text-muted-foreground data-[state=active]:text-foreground data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed"
                                >
                                    Feature Configuration
                                </TabsTrigger>
                                <TabsTrigger
                                    value="scanner"
                                    disabled={!enabledTools.sonarqube && scanMetrics.sonarqube.length === 0 && !enabledTools.trivy && scanMetrics.trivy.length === 0}
                                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-600 data-[state=active]:shadow-none data-[state=active]:bg-transparent px-4 py-3 font-medium text-muted-foreground data-[state=active]:text-foreground data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed"
                                >
                                    Scan Configuration
                                </TabsTrigger>
                            </TabsList>
                        </div>

                        <div className="flex-1 overflow-y-auto p-8">
                            <div className="max-w-3xl mx-auto">
                                <TabsContent value="features" className="m-0 space-y-6">
                                    <div className="flex items-center gap-2 mb-4">
                                        <div>
                                            <h3 className="text-lg font-semibold">Feature Configuration</h3>
                                            <p className="text-sm text-muted-foreground">
                                                Configure parameters for the {selectedFeatures.size} selected features
                                            </p>
                                        </div>
                                    </div>
                                    <Card>
                                        <CardContent className="pt-6">
                                            <FeatureConfigForm
                                                datasetId={datasetId}
                                                selectedFeatures={selectedFeatures}
                                                value={featureConfigs}
                                                onChange={setFeatureConfigs}
                                                disabled={isDisabled}
                                            />
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="scanner" className="m-0 space-y-6">
                                    <div className="flex items-center gap-2 mb-4">
                                        <div>
                                            <h3 className="text-lg font-semibold">Scan Configuration</h3>
                                            <p className="text-sm text-muted-foreground">
                                                Configure credentials and options for enabled scanners
                                            </p>
                                        </div>
                                    </div>
                                    <Card>
                                        <CardContent className="pt-6">
                                            <ScanPropertiesPanel
                                                scanConfig={scanConfig}
                                                onScanConfigChange={setScanConfig}
                                                enabledTools={enabledTools}
                                                repos={repos}
                                                disabled={isDisabled}
                                            />
                                        </CardContent>
                                    </Card>
                                </TabsContent>
                            </div>
                        </div>
                    </Tabs>

                    {/* Right: Summary & Finalize */}
                    <div className="w-[350px] bg-background border-l p-6 space-y-8 z-10">
                        <div>
                            <h3 className="text-sm font-medium uppercase text-muted-foreground tracking-wider mb-4">Summary</h3>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center p-3 border rounded-lg bg-slate-50 dark:bg-slate-900">
                                    <div className="flex items-center gap-2">
                                        <Box className="h-4 w-4 text-muted-foreground" />
                                        <span className="text-sm font-medium">Selected Features</span>
                                    </div>
                                    <Badge variant="secondary">{selectedFeatures.size}</Badge>
                                </div>
                                <div className="flex justify-between items-center p-3 border rounded-lg bg-slate-50 dark:bg-slate-900">
                                    <div className="flex items-center gap-2">
                                        <CheckSquare className="h-4 w-4 text-muted-foreground" />
                                        <span className="text-sm font-medium">Selected Scan Metrics</span>
                                    </div>
                                    <div className="flex gap-1">
                                        {!enabledTools.sonarqube && scanMetrics.sonarqube.length === 0 && !enabledTools.trivy && scanMetrics.trivy.length === 0 && <span className="text-xs text-muted-foreground">None</span>}
                                        {enabledTools.sonarqube && scanMetrics.sonarqube.length > 0 && <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">Sonar</Badge>}
                                        {enabledTools.trivy && scanMetrics.trivy.length > 0 && <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Trivy</Badge>}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="h-px bg-border" />

                        <div>
                            <h3 className="text-sm font-medium uppercase text-muted-foreground tracking-wider mb-4">Finalize</h3>
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Version Name <span className="text-muted-foreground font-normal">(optional)</span></label>
                                <Input
                                    placeholder="e.g., 'v3 - With Build Logs'"
                                    value={versionName}
                                    onChange={(e) => setVersionName(e.target.value)}
                                    disabled={isDisabled}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Give this version a meaningful name to easily identify it later.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
