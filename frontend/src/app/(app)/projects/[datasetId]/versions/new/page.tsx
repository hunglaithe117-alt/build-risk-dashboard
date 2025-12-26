"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    ArrowLeft,
    ArrowRight,
    Loader2,
    Sparkles,
    Zap,
    Check,
    Settings2,
    Scan,
    FileCheck,
} from "lucide-react";
import { useFeatureSelector } from "@/components/features";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    ViewToggle,
    TemplateSelector,
} from "@/components/features/selection";
import {
    FeatureConfigForm,
    type FeatureConfigsData,
} from "@/components/features/config/FeatureConfigForm";
import {
    ScanConfigPanel,
    type ScanConfig,
    DEFAULT_SCAN_CONFIG,
} from "@/components/sonar/scan-config-panel";
import { datasetsApi } from "@/lib/api";
import { useDatasetVersions } from "../../_hooks/useDatasetVersions";

/** Scan metrics selection */
interface ScanMetricsData {
    sonarqube: string[];
    trivy: string[];
}

interface RepoInfo {
    id: string;
    full_name: string;
}

const STEPS = [
    { id: 1, name: "Features", icon: Sparkles, description: "Select features" },
    { id: 2, name: "Configure", icon: Settings2, description: "Feature settings" },
    { id: 3, name: "Scan", icon: Scan, description: "Scan configuration" },
    { id: 4, name: "Review", icon: FileCheck, description: "Review & create" },
];

export default function CreateVersionPage() {
    const router = useRouter();
    const params = useParams();
    const datasetId = params.datasetId as string;

    // Use the existing hook for version management
    const { activeVersion, createVersion, creating } = useDatasetVersions(datasetId);
    const hasActiveVersion = !!activeVersion;

    const [step, setStep] = useState(1);
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
    const [repos, setRepos] = useState<RepoInfo[]>([]);
    const [dataset, setDataset] = useState<{ name: string; rows: number } | null>(null);
    const [isCreating, setIsCreating] = useState(false);

    // Fetch dataset info
    useEffect(() => {
        async function fetchDataset() {
            try {
                const data = await datasetsApi.get(datasetId);
                setDataset({ name: data.name, rows: data.rows || 0 });
            } catch (err) {
                console.error("Failed to fetch dataset:", err);
            }
        }
        fetchDataset();
    }, [datasetId]);

    // Fetch repos for per-repo scan config
    useEffect(() => {
        async function fetchRepos() {
            try {
                const summary = await datasetsApi.getValidationSummary(datasetId);
                if (summary.repos) {
                    setRepos(
                        summary.repos.map((r) => ({
                            id: String(r.github_repo_id || r.id),
                            full_name: r.full_name,
                        }))
                    );
                }
            } catch (err) {
                console.error("Failed to fetch repos:", err);
            }
        }
        fetchRepos();
    }, [datasetId]);

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
        setSearchQuery,
        filteredNodes,
        applyTemplate,
    } = useFeatureSelector();

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
            // Flatten configs for API
            const flatConfigs: Record<string, unknown> = {
                ...featureConfigs.global,
                repo_configs: featureConfigs.repos,
            };

            const result = await createVersion({
                selected_features: Array.from(selectedFeatures),
                feature_configs: flatConfigs,
                scan_metrics: scanMetrics,
                scan_config: scanConfig as unknown as Record<string, unknown>,
                name: versionName || undefined,
            });

            if (result) {
                router.push(`/projects/${datasetId}`);
            }
        } catch (err) {
            console.error("Failed to create version:", err);
        } finally {
            setIsCreating(false);
        }
    };

    const canProceed = useMemo(() => {
        switch (step) {
            case 1:
                return selectedFeatures.size > 0;
            case 2:
            case 3:
                return true;
            case 4:
                return !isCreating && !creating && !hasActiveVersion && selectedFeatures.size > 0;
            default:
                return false;
        }
    }, [step, selectedFeatures.size, isCreating, creating, hasActiveVersion]);

    const handleNext = () => {
        if (step < 4) setStep(step + 1);
        else handleCreateVersion();
    };

    const handleBack = () => {
        if (step > 1) setStep(step - 1);
        else router.push(`/projects/${datasetId}`);
    };

    return (
        <div className="min-h-screen bg-background flex flex-col">
            {/* Header */}
            <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
                <div className="container mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => router.push(`/projects/${datasetId}`)}
                            >
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                Back to Project
                            </Button>
                            <div className="h-6 w-px bg-border" />
                            <div>
                                <h1 className="text-lg font-semibold flex items-center gap-2">
                                    <Sparkles className="h-5 w-5" />
                                    Create New Version
                                </h1>
                                {dataset && (
                                    <p className="text-sm text-muted-foreground">
                                        {dataset.name} • {dataset.rows.toLocaleString()} rows
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* Step Indicator */}
                        <div className="hidden md:flex items-center gap-2">
                            {STEPS.map((s, idx) => (
                                <div key={s.id} className="flex items-center">
                                    <button
                                        onClick={() => s.id < step && setStep(s.id)}
                                        disabled={s.id > step}
                                        className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors ${step === s.id
                                            ? "bg-primary text-primary-foreground"
                                            : step > s.id
                                                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                                : "bg-muted text-muted-foreground"
                                            }`}
                                    >
                                        {step > s.id ? (
                                            <Check className="h-4 w-4" />
                                        ) : (
                                            <s.icon className="h-4 w-4" />
                                        )}
                                        <span className="hidden lg:inline">{s.name}</span>
                                    </button>
                                    {idx < STEPS.length - 1 && (
                                        <div
                                            className={`w-8 h-px mx-1 ${step > s.id ? "bg-green-500" : "bg-border"
                                                }`}
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 container mx-auto px-6 py-8">
                {/* Step 1: Feature Selection */}
                {step === 1 && (
                    <div className="space-y-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-2xl font-bold">Select Features</h2>
                                <p className="text-muted-foreground">
                                    Choose which features to include in your enriched dataset
                                </p>
                            </div>
                            <div className="flex items-center gap-4">
                                <TemplateSelector
                                    onApplyTemplate={applyTemplate}
                                    disabled={isCreating || hasActiveVersion}
                                />
                                <ViewToggle value={viewMode} onChange={setViewMode} />
                            </div>
                        </div>

                        <div className="grid lg:grid-cols-3 gap-6">
                            <div className="lg:col-span-2">
                                <div className="border rounded-xl p-4 min-h-[500px]">
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
                            </div>
                            <div>
                                <SelectedFeaturesPanel
                                    selectedFeatures={selectedFeatures}
                                    allFeatures={allFeatures}
                                    nodes={extractorNodes}
                                    onRemoveFeature={toggleFeature}
                                    onClearAll={clearSelection}
                                    rowCount={dataset?.rows || 0}
                                />
                            </div>
                        </div>
                    </div>
                )}

                {/* Step 2: Feature Configuration */}
                {step === 2 && (
                    <div className="space-y-6 max-w-4xl">
                        <div>
                            <h2 className="text-2xl font-bold">Configure Features</h2>
                            <p className="text-muted-foreground">
                                Set parameters for feature extraction
                            </p>
                        </div>

                        <FeatureConfigForm
                            datasetId={datasetId}
                            selectedFeatures={selectedFeatures}
                            onChange={setFeatureConfigs}
                            disabled={isCreating}
                        />
                    </div>
                )}

                {/* Step 3: Scan Configuration */}
                {step === 3 && (
                    <div className="space-y-6 max-w-4xl">
                        <div>
                            <h2 className="text-2xl font-bold">Scan Configuration</h2>
                            <p className="text-muted-foreground">
                                Configure SonarQube and Trivy scans for additional metrics
                            </p>
                        </div>

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
                    </div>
                )}

                {/* Step 4: Review & Create */}
                {step === 4 && (
                    <div className="space-y-6 max-w-4xl">
                        <div>
                            <h2 className="text-2xl font-bold">Review & Create</h2>
                            <p className="text-muted-foreground">
                                Review your configuration and create the version
                            </p>
                        </div>

                        <div className="grid gap-6 md:grid-cols-2">
                            {/* Features Summary */}
                            <div className="border rounded-xl p-4 space-y-3">
                                <h3 className="font-semibold flex items-center gap-2">
                                    <Sparkles className="h-4 w-4" />
                                    Selected Features
                                </h3>
                                <Badge variant="secondary" className="text-lg">
                                    {selectedFeatures.size} features
                                </Badge>
                                <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
                                    {Array.from(selectedFeatures)
                                        .slice(0, 20)
                                        .map((f) => (
                                            <Badge key={f} variant="outline" className="text-xs">
                                                {f}
                                            </Badge>
                                        ))}
                                    {selectedFeatures.size > 20 && (
                                        <Badge variant="outline">
                                            +{selectedFeatures.size - 20} more
                                        </Badge>
                                    )}
                                </div>
                            </div>

                            {/* Scan Summary */}
                            <div className="border rounded-xl p-4 space-y-3">
                                <h3 className="font-semibold flex items-center gap-2">
                                    <Scan className="h-4 w-4" />
                                    Scan Metrics
                                </h3>
                                <div className="space-y-2 text-sm">
                                    <p>
                                        SonarQube:{" "}
                                        <span className="font-medium">
                                            {scanMetrics.sonarqube.length > 0
                                                ? `${scanMetrics.sonarqube.length} metrics`
                                                : "Disabled"}
                                        </span>
                                    </p>
                                    <p>
                                        Trivy:{" "}
                                        <span className="font-medium">
                                            {scanMetrics.trivy.length > 0
                                                ? `${scanMetrics.trivy.length} metrics`
                                                : "Disabled"}
                                        </span>
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Version Name */}
                        <div className="border rounded-xl p-4 space-y-3">
                            <h3 className="font-semibold">Version Name (optional)</h3>
                            <Input
                                placeholder="e.g., 'v3 - Git + Build Logs'"
                                value={versionName}
                                onChange={(e) => setVersionName(e.target.value)}
                                disabled={isCreating}
                                className="max-w-md"
                            />
                        </div>

                        {hasActiveVersion && (
                            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-4">
                                <p className="text-amber-700 dark:text-amber-400">
                                    ⏳ A version is currently processing. Wait for it to complete or
                                    cancel it before creating a new one.
                                </p>
                            </div>
                        )}
                    </div>
                )}
            </main>

            {/* Footer */}
            <footer className="sticky bottom-0 border-t bg-background/95 backdrop-blur">
                <div className="container mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                        <Button variant="outline" onClick={handleBack}>
                            <ArrowLeft className="h-4 w-4 mr-2" />
                            {step === 1 ? "Cancel" : "Back"}
                        </Button>

                        <Button onClick={handleNext} disabled={!canProceed}>
                            {step === 4 ? (
                                isCreating || creating ? (
                                    <>
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        Creating...
                                    </>
                                ) : (
                                    <>
                                        <Zap className="h-4 w-4 mr-2" />
                                        Create Version
                                    </>
                                )
                            ) : (
                                <>
                                    Next
                                    <ArrowRight className="h-4 w-4 ml-2" />
                                </>
                            )}
                        </Button>
                    </div>
                </div>
            </footer>
        </div>
    );
}
