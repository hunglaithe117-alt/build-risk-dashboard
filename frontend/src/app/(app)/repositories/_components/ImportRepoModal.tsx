"use client";

import {
    Building2,
    Globe,
    Loader2,
    Search,
    X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FeatureDAGVisualization, type FeatureDAGData } from "@/components/features";
import { FeatureConfigForm, type FeatureConfigsData } from "@/components/features/config/FeatureConfigForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useDebounce } from "@/hooks/use-debounce";
import { datasetsApi, featuresApi, reposApi } from "@/lib/api";
import {
    CIProvider,
    DatasetTemplateRecord,
    FeatureDefinitionSummary,
    RepoImportPayload,
    RepoSuggestion,
} from "@/types";
import { ExtractionPlanTimeline } from "./ExtractionPlanTimeline";

const Portal = ({ children }: { children: React.ReactNode }) => {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) return null;
    return createPortal(children, document.body);
};

type FeatureCategoryGroup = {
    category: string;
    display_name: string;
    features: FeatureDefinitionSummary[];
};

// Panel to display selected features with tooltips and expand/collapse
function SelectedFeaturesPanelWithTooltips({
    selectedFeatures,
    featuresData,
}: {
    selectedFeatures: string[];
    featuresData: FeatureCategoryGroup[] | null;
}) {
    const [isExpanded, setIsExpanded] = useState(false);
    const INITIAL_SHOW = 20;

    // Build a map of feature name -> description from featuresData
    const featureDescriptions = useMemo(() => {
        const map: Record<string, string> = {};
        if (featuresData) {
            for (const group of featuresData) {
                for (const feature of group.features) {
                    map[feature.name] = feature.description || feature.display_name || feature.name;
                }
            }
        }
        return map;
    }, [featuresData]);

    const displayedFeatures = isExpanded ? selectedFeatures : selectedFeatures.slice(0, INITIAL_SHOW);
    const hasMore = selectedFeatures.length > INITIAL_SHOW;

    return (
        <div className="rounded-xl border bg-blue-50/50 dark:bg-blue-900/10 p-4">
            <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-blue-900 dark:text-blue-200">
                    Selected Feature Set
                </span>
                <Badge className="bg-blue-600">{selectedFeatures.length} features</Badge>
            </div>
            <p className="text-xs text-blue-700 dark:text-blue-300 mb-3">
                All repositories will automatically extract these features for Bayesian risk prediction.
                <span className="ml-1 text-blue-500">(Hover for description)</span>
            </p>
            <div className={`flex flex-wrap gap-1.5 ${isExpanded ? 'max-h-[300px]' : 'max-h-[120px]'} overflow-y-auto transition-all`}>
                {displayedFeatures.map(feat => (
                    <Badge
                        key={feat}
                        variant="secondary"
                        className="text-xs cursor-help hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors"
                        title={featureDescriptions[feat] || feat}
                    >
                        {feat}
                    </Badge>
                ))}
                {hasMore && !isExpanded && (
                    <Badge
                        variant="outline"
                        className="text-xs cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900"
                        onClick={() => setIsExpanded(true)}
                    >
                        +{selectedFeatures.length - INITIAL_SHOW} more
                    </Badge>
                )}
            </div>
            {hasMore && isExpanded && (
                <button
                    onClick={() => setIsExpanded(false)}
                    className="mt-2 text-xs text-blue-600 hover:underline"
                >
                    Show less
                </button>
            )}
        </div>
    );

}

interface ImportRepoModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImport: () => void;
}

export function ImportRepoModal({ isOpen, onClose, onImport }: ImportRepoModalProps) {
    // Simplified to 2 steps: Select repos -> Configure (features auto-applied)
    const [step, setStep] = useState<1 | 2>(1);
    const [searchTerm, setSearchTerm] = useState("");
    const [isSearching, setIsSearching] = useState(false);
    const debouncedSearchTerm = useDebounce(searchTerm, 500);
    const lastSearchedTerm = useRef<string | null>(null);

    // Search results
    const [privateMatches, setPrivateMatches] = useState<RepoSuggestion[]>([]);
    const [publicMatches, setPublicMatches] = useState<RepoSuggestion[]>([]);
    const [searchError, setSearchError] = useState<string | null>(null);

    // Selection & Config
    const [selectedRepos, setSelectedRepos] = useState<Record<string, RepoSuggestion>>({});
    const [featureConfigs, setFeatureConfigs] = useState<FeatureConfigsData>({
        global: {},
        repos: {},
    });
    const [baseConfigs, setBaseConfigs] = useState<
        Record<string, {
            ci_provider: string;
            max_builds?: number | null;
            since_days?: number | null;
        }>
    >({});

    // Features data (for tooltips in SelectedFeaturesPanel)
    const [featuresData, setFeaturesData] = useState<FeatureCategoryGroup[] | null>(null);
    const [featuresLoading, setFeaturesLoading] = useState(false);

    const [importing, setImporting] = useState(false);
    const [importError, setImportError] = useState<string | null>(null);
    const [activeRepo, setActiveRepo] = useState<string | null>(null);

    // Templates state
    const [templates, setTemplates] = useState<DatasetTemplateRecord[]>([]);
    const [templatesLoading, setTemplatesLoading] = useState(false);

    // DAG state
    const [dagData, setDagData] = useState<FeatureDAGData | null>(null);
    const [dagLoading, setDagLoading] = useState(false);

    const performSearch = useCallback(async (query: string, force = false) => {
        if (!force && query === lastSearchedTerm.current) return;
        lastSearchedTerm.current = query;

        setIsSearching(true);
        setSearchError(null);
        try {
            const data = await reposApi.search(query.trim() || undefined);
            setPrivateMatches(data.private_matches.map(r => ({ ...r })));
            setPublicMatches(data.public_matches.map(r => ({ ...r })));
        } catch (err) {
            console.error(err);
            setSearchError("Failed to search repositories.");
        } finally {
            setIsSearching(false);
        }
    }, []);

    const loadFeatures = useCallback(async () => {
        if (featuresLoading || featuresData) return;
        setFeaturesLoading(true);
        try {
            const data = await featuresApi.list({ is_active: true });
            const grouped: Record<string, FeatureCategoryGroup> = {};
            data.items.forEach((feat: FeatureDefinitionSummary) => {
                const key = feat.category || "uncategorized";
                if (!grouped[key]) {
                    grouped[key] = {
                        category: key,
                        display_name: key,
                        features: [],
                    };
                }
                grouped[key].features.push(feat);
            });

            const categories = Object.values(grouped).sort((a, b) =>
                a.display_name.localeCompare(b.display_name)
            );
            setFeaturesData(categories);
        } finally {
            setFeaturesLoading(false);
        }
    }, [featuresData, featuresLoading]);

    const loadDAG = useCallback(async () => {
        if (dagLoading || dagData) return;
        setDagLoading(true);
        try {
            const data = await featuresApi.getDAG();
            setDagData(data);
        } catch (err) {
            console.error("Failed to load DAG:", err);
        } finally {
            setDagLoading(false);
        }
    }, [dagData, dagLoading]);

    const [selectedFeatures, setselectedFeatures] = useState<string[]>([]);
    const loadSelectedTemplate = useCallback(async () => {
        if (templatesLoading) return;
        if (selectedFeatures.length > 0) return;
        setTemplatesLoading(true);
        try {
            const template = await datasetsApi.getTemplateByName("TravisTorrent Full");
            setTemplates([template]);
            setselectedFeatures(template.feature_names || []);
        } catch (err) {
            console.error("Failed to load selected template:", err);
            // Fallback: leave empty, showing all features
        } finally {
            setTemplatesLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [templatesLoading]);

    useEffect(() => {
        if (isOpen && debouncedSearchTerm === searchTerm) {
            performSearch(debouncedSearchTerm);
        }
    }, [debouncedSearchTerm, isOpen, searchTerm, performSearch]);

    useEffect(() => {
        if (isOpen) {
            // Reset all state when modal opens
            setStep(1);
            setSearchTerm("");
            setSelectedRepos({});
            setBaseConfigs({});
            setFeatureConfigs({ global: {}, repos: {} });
            setPrivateMatches([]);
            setPublicMatches([]);
            setSearchError(null);
            setImportError(null);
            setFeaturesData(null);
            setDagData(null);
            setActiveRepo(null);
            performSearch("", true);
        }
    }, [isOpen, performSearch]);

    const toggleSelection = (repo: RepoSuggestion) => {
        setSelectedRepos((prev) => {
            const next = { ...prev };
            if (next[repo.full_name]) {
                delete next[repo.full_name];
                // Remove base config when repo is deselected
                setBaseConfigs((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
            } else {
                next[repo.full_name] = repo;
                // Initialize base config
                setBaseConfigs((current) => ({
                    ...current,
                    [repo.full_name]: {
                        ci_provider: CIProvider.GITHUB_ACTIONS,
                        max_builds: null,
                        since_days: null,
                    },
                }));
            }
            return next;
        });
    };

    const selectedList = useMemo(() => Object.values(selectedRepos), [selectedRepos]);

    useEffect(() => {
        if (selectedList.length === 0) {
            setActiveRepo(null);
            return;
        }
        if (!activeRepo || !selectedRepos[activeRepo]) {
            setActiveRepo(selectedList[0].full_name);
        }
    }, [selectedList, activeRepo, selectedRepos]);

    // Load features and DAG when entering step 2
    useEffect(() => {
        if (step < 2) return;
        void loadFeatures();
        if (step === 2) {
            void loadDAG();
            void loadSelectedTemplate();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, selectedList.length]);

    const handleImport = async () => {
        if (!selectedList.length) return;
        setImporting(true);
        setImportError(null);

        try {
            const payloads: RepoImportPayload[] = selectedList.map((repo) => {
                const baseConfig = baseConfigs[repo.full_name];
                const dynamicRepoConfig = featureConfigs.repos[repo.full_name] || {};

                return {
                    full_name: repo.full_name,
                    provider: "github",
                    ci_provider: baseConfig.ci_provider,
                    max_builds: baseConfig.max_builds ?? null,
                    since_days: baseConfig.since_days ?? null,
                    feature_configs: {
                        global: featureConfigs.global,
                        repos: {
                            [repo.full_name]: dynamicRepoConfig,
                        },
                    },
                };
            });

            await reposApi.importBulk(payloads);
            onImport(); // Trigger refresh in parent
            onClose();
        } catch (err) {
            console.error(err);
            setImportError("Failed to import repositories. Please try again.");
        } finally {
            setImporting(false);
        }
    };

    const featureFormFeatures = useMemo(() => new Set(selectedFeatures), [selectedFeatures]);

    const featureFormRepos = useMemo(() => selectedList.map(r => ({
        id: r.full_name,
        full_name: r.full_name,
        validation_status: "unknown"
    })), [selectedList]);

    if (!isOpen) return null;

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
                <div className="w-full max-w-7xl h-[90vh] rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-950 border dark:border-slate-800 flex flex-col overflow-hidden">
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold">Import Repositories</h2>
                            <p className="text-sm text-muted-foreground">
                                Step {step} of 2:{" "}
                                {step === 1
                                    ? "Select repositories"
                                    : "Configure & Import"}
                            </p>
                        </div>
                        <button
                            type="button"
                            className="rounded-full p-2 text-muted-foreground hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                            onClick={onClose}
                        >
                            <X className="h-5 w-5" />
                        </button>
                    </div>


                    {/* GitHub App status banner removed - app is managed at organization level */}

                    <div className="flex-1 overflow-y-auto">
                        {step === 1 ? (
                            <div className="space-y-6">
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                    <input
                                        type="text"
                                        className="w-full rounded-lg border border-slate-200 bg-transparent pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-0 focus:border-primary"
                                        placeholder="Search repositories (e.g. owner/repo)..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                    />
                                </div>
                                {selectedList.length > 0 && (
                                    <div className="rounded-lg border bg-slate-50 dark:bg-slate-900/30 px-3 py-2">
                                        <div className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                                            Selected ({selectedList.length})
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {selectedList.map((repo) => (
                                                <Badge
                                                    key={repo.full_name}
                                                    variant="secondary"
                                                    className="flex items-center gap-2"
                                                >
                                                    <span className="truncate max-w-[200px]">{repo.full_name}</span>
                                                    <button
                                                        type="button"
                                                        className="text-xs"
                                                        onClick={() => toggleSelection(repo)}
                                                    >
                                                        ×
                                                    </button>
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                <div className="h-[400px] overflow-y-auto pr-2 space-y-6">
                                    {searchError && (
                                        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                                            {searchError}
                                        </div>
                                    )}

                                    {/* Private Repos Section */}
                                    <div>
                                        <h3 className="mb-3 text-sm font-medium text-muted-foreground flex items-center gap-2">
                                            <Building2 className="h-3 w-3" /> Organization Repositories
                                        </h3>
                                        <div className="space-y-2">
                                            {privateMatches.length === 0 && !isSearching ? (
                                                <div className="text-sm text-muted-foreground italic px-2">
                                                    No matching organization repositories found.
                                                </div>
                                            ) : (
                                                privateMatches.map((repo) => (
                                                    <RepoItem
                                                        key={repo.full_name}
                                                        repo={repo}
                                                        isSelected={!!selectedRepos[repo.full_name]}
                                                        onToggle={() => toggleSelection(repo)}
                                                    />
                                                ))
                                            )}
                                        </div>
                                    </div>

                                    {/* Public Repos Section */}
                                    <div>
                                        <h3 className="mb-3 text-sm font-medium text-muted-foreground flex items-center gap-2">
                                            <Globe className="h-3 w-3" /> Public GitHub Repositories
                                        </h3>
                                        <div className="space-y-2">
                                            {publicMatches.length === 0 && !isSearching ? (
                                                <div className="text-sm text-muted-foreground italic px-2">
                                                    {searchTerm.length >= 3
                                                        ? "No matching public repositories found."
                                                        : "Type at least 3 characters to search public repositories."}
                                                </div>
                                            ) : (
                                                publicMatches.map((repo) => (
                                                    <RepoItem
                                                        key={repo.full_name}
                                                        repo={repo}
                                                        isSelected={!!selectedRepos[repo.full_name]}
                                                        onToggle={() => toggleSelection(repo)}
                                                    />
                                                ))
                                            )}
                                        </div>
                                    </div>

                                    {isSearching && (
                                        <div className="flex justify-center py-4">
                                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="flex h-full gap-4">
                                <div className="w-60 flex-shrink-0 rounded-xl border bg-slate-50 dark:bg-slate-900/40 overflow-hidden">
                                    <div className="px-3 py-2 text-xs font-semibold uppercase text-muted-foreground">
                                        Selected Repos
                                    </div>
                                    <div className="divide-y divide-slate-200 dark:divide-slate-800 max-h-[480px] overflow-y-auto">
                                        {selectedList.map((repo) => (
                                            <button
                                                key={repo.full_name}
                                                className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between gap-2 transition-colors ${activeRepo === repo.full_name
                                                    ? "bg-white dark:bg-slate-800 font-semibold border-l-2 border-primary"
                                                    : "hover:bg-white/70 dark:hover:bg-slate-800/70"
                                                    }`}
                                                onClick={() => setActiveRepo(repo.full_name)}
                                            >
                                                <span className="truncate">{repo.full_name}</span>
                                                <Badge variant="secondary" className="text-[10px] h-5">
                                                    {repo.private ? "Private" : "Public"}
                                                </Badge>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex-1 overflow-y-auto pr-0">
                                    {!activeRepo ? (
                                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                                            Select a repository to configure
                                        </div>
                                    ) : (
                                        <div className="space-y-4">

                                            {/* Base Config (CI, Limits) */}
                                            <div className="grid gap-4 md:grid-cols-3 mb-6 p-4 border rounded-lg bg-slate-50 dark:bg-slate-900/20">
                                                <div className="space-y-2">
                                                    <label className="text-sm font-medium">CI Provider</label>
                                                    <Select
                                                        value={baseConfigs[activeRepo]?.ci_provider || CIProvider.GITHUB_ACTIONS}
                                                        onValueChange={(val) => setBaseConfigs(prev => ({
                                                            ...prev,
                                                            [activeRepo]: { ...prev[activeRepo], ci_provider: val }
                                                        }))}
                                                    >
                                                        <SelectTrigger>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value={CIProvider.GITHUB_ACTIONS}>GitHub Actions</SelectItem>
                                                            <SelectItem value={CIProvider.TRAVIS_CI}>Travis CI</SelectItem>
                                                            <SelectItem value={CIProvider.CIRCLECI}>CircleCI</SelectItem>
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <div className="space-y-2">
                                                    <label className="text-sm font-medium">Max Builds</label>
                                                    <Input
                                                        type="number"
                                                        placeholder="Unlimited"
                                                        min={1}
                                                        value={baseConfigs[activeRepo]?.max_builds || ""}
                                                        onChange={(e) => setBaseConfigs(prev => ({
                                                            ...prev,
                                                            [activeRepo]: { ...prev[activeRepo], max_builds: e.target.value ? parseInt(e.target.value) : null }
                                                        }))}
                                                    />
                                                </div>
                                                <div className="space-y-2">
                                                    <label className="text-sm font-medium">Since Days</label>
                                                    <Input
                                                        type="number"
                                                        placeholder="Unlimited"
                                                        min={1}
                                                        value={baseConfigs[activeRepo]?.since_days || ""}
                                                        onChange={(e) => setBaseConfigs(prev => ({
                                                            ...prev,
                                                            [activeRepo]: { ...prev[activeRepo], since_days: e.target.value ? parseInt(e.target.value) : null }
                                                        }))}
                                                    />
                                                </div>
                                            </div>

                                            {/* Dynamic Feature Config */}
                                            <FeatureConfigForm
                                                selectedFeatures={featureFormFeatures}
                                                repos={featureFormRepos}
                                                onChange={setFeatureConfigs}
                                            />

                                            {/* DAG Visualization - Selected Features */}
                                            {dagLoading || templatesLoading ? (
                                                <div className="mt-6 pt-4 border-t flex items-center gap-2 text-sm text-muted-foreground">
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                    Loading feature extraction plan...
                                                </div>
                                            ) : dagData && selectedFeatures.length > 0 && (
                                                <div className="mt-6 pt-4 border-t space-y-4">
                                                    <h4 className="text-sm font-semibold flex items-center gap-2">
                                                        <span>Features Extraction Plan</span>
                                                        <Badge variant="secondary" className="text-xs">
                                                            {selectedFeatures.length} features
                                                        </Badge>
                                                    </h4>

                                                    {/* 1. Extraction Plan Timeline - filter nodes with selected features */}
                                                    <ExtractionPlanTimeline
                                                        executionLevels={dagData.execution_levels.map(level => ({
                                                            ...level,
                                                            nodes: level.nodes.filter(nodeId => {
                                                                const node = dagData.nodes.find(n => n.id === nodeId);
                                                                return node?.features.some(f => selectedFeatures.includes(f));
                                                            })
                                                        })).filter(level => level.nodes.length > 0)}
                                                        nodeLabels={Object.fromEntries(
                                                            dagData.nodes?.map((n: { id: string; label?: string }) => [n.id, n.label || n.id]) || []
                                                        )}
                                                        activeNodes={new Set(
                                                            dagData.nodes
                                                                ?.filter(n => n.features.some(f => selectedFeatures.includes(f)))
                                                                .map(n => n.id) || []
                                                        )}
                                                    />

                                                    {/* 2. Visual DAG Graph - show ALL nodes, highlight selected features */}
                                                    <FeatureDAGVisualization
                                                        dagData={dagData as FeatureDAGData}
                                                        selectedFeatures={selectedFeatures}
                                                        onFeaturesChange={() => { }}
                                                        className="h-[350px]"
                                                    />

                                                    {/* 3. Selected Features Panel */}
                                                    <SelectedFeaturesPanelWithTooltips
                                                        selectedFeatures={selectedFeatures}
                                                        featuresData={featuresData}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="mt-6 flex items-center justify-between border-t pt-4">
                        <Button variant="ghost" onClick={onClose}>
                            Cancel
                        </Button>
                        <div className="flex gap-2">
                            {step > 1 && (
                                <Button
                                    variant="outline"
                                    onClick={() =>
                                        setStep((prev) => (prev > 1 ? ((prev - 1) as 1 | 2) : prev))
                                    }
                                >
                                    Back
                                </Button>
                            )}
                            {step === 1 ? (
                                <Button
                                    onClick={() => setStep(2)}
                                    disabled={selectedList.length === 0}
                                >
                                    Next
                                </Button>
                            ) : (
                                // Step 2 is now final - Import button directly
                                <Button
                                    onClick={handleImport}
                                    disabled={importing || selectedList.length === 0}
                                >
                                    {importing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Import {selectedList.length} Repositories
                                </Button>
                            )}
                        </div>
                    </div>

                    {importError && (
                        <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                            {importError}
                        </div>
                    )}
                </div>
            </div>
        </Portal>
    );
}

function RepoItem({
    repo,
    isSelected,
    onToggle,
}: {
    repo: RepoSuggestion;
    isSelected: boolean;
    onToggle: () => void;
}) {
    return (
        <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${isSelected ? 'bg-slate-50 border-primary/50 dark:bg-slate-900' : 'hover:bg-slate-50 dark:hover:bg-slate-900/50'}`}>
            <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                checked={isSelected}
                onChange={onToggle}
            />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{repo.full_name}</span>
                    {repo.private && (
                        <Badge variant="secondary" className="text-[10px] h-5 px-1.5">Private</Badge>
                    )}
                </div>
                <p className="text-sm text-muted-foreground line-clamp-1">
                    {repo.description || "No description provided"}
                </p>
            </div>
        </label>
    );
}


