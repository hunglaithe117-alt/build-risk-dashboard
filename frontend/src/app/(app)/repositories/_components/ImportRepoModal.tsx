"use client";

import {
    Building2,
    Globe,
    Loader2,
    Search,
    ArrowRight,
    ArrowLeft,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetFooter,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
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
    const INITIAL_SHOW = 15;

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
        <div className="rounded-lg border bg-blue-50/50 dark:bg-blue-900/10 p-3">
            <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">
                    Selected Features
                </span>
                <Badge className="bg-blue-600 text-xs">{selectedFeatures.length}</Badge>
            </div>
            <div className={`flex flex-wrap gap-1 ${isExpanded ? 'max-h-[200px]' : 'max-h-[80px]'} overflow-y-auto transition-all`}>
                {displayedFeatures.map(feat => (
                    <Badge
                        key={feat}
                        variant="secondary"
                        className="text-[10px] cursor-help"
                        title={featureDescriptions[feat] || feat}
                    >
                        {feat}
                    </Badge>
                ))}
                {hasMore && !isExpanded && (
                    <Badge
                        variant="outline"
                        className="text-[10px] cursor-pointer"
                        onClick={() => setIsExpanded(true)}
                    >
                        +{selectedFeatures.length - INITIAL_SHOW} more
                    </Badge>
                )}
            </div>
            {hasMore && isExpanded && (
                <button
                    onClick={() => setIsExpanded(false)}
                    className="mt-1 text-[10px] text-blue-600 hover:underline"
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

    const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);
    const loadSelectedTemplate = useCallback(async () => {
        if (templatesLoading) return;
        if (selectedFeatures.length > 0) return;
        setTemplatesLoading(true);
        try {
            const template = await datasetsApi.getTemplateByName("TravisTorrent Full");
            setSelectedFeatures(template.feature_names || []);
        } catch (err) {
            console.error("Failed to load selected template:", err);
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

    return (
        <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <SheetContent size="2xl" className="flex flex-col p-0 overflow-hidden">
                {/* Header */}
                <div className="px-6 py-4 border-b">
                    <SheetHeader>
                        <SheetTitle className="text-xl">Import Repositories</SheetTitle>
                        <SheetDescription>
                            Step {step} of 2: {step === 1 ? "Select repositories" : "Configure & Import"}
                        </SheetDescription>
                    </SheetHeader>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4">
                    {step === 1 ? (
                        <div className="space-y-4">
                            {/* Search */}
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <input
                                    type="text"
                                    className="w-full rounded-lg border bg-transparent pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                                    placeholder="Search repositories (e.g. owner/repo)..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                />
                            </div>

                            {/* Selected Repos */}
                            {selectedList.length > 0 && (
                                <div className="rounded-lg border bg-slate-50 dark:bg-slate-900/30 p-3">
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
                                                <span className="truncate max-w-[180px]">{repo.full_name}</span>
                                                <button
                                                    type="button"
                                                    className="text-xs hover:text-destructive"
                                                    onClick={() => toggleSelection(repo)}
                                                >
                                                    ×
                                                </button>
                                            </Badge>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Search Results */}
                            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-1">
                                {searchError && (
                                    <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                                        {searchError}
                                    </div>
                                )}

                                {/* Private Repos */}
                                <div>
                                    <h3 className="mb-2 text-xs font-medium text-muted-foreground flex items-center gap-2">
                                        <Building2 className="h-3 w-3" /> Organization Repositories
                                    </h3>
                                    <div className="space-y-1.5">
                                        {privateMatches.length === 0 && !isSearching ? (
                                            <div className="text-sm text-muted-foreground italic px-2 py-1">
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

                                {/* Public Repos */}
                                <div>
                                    <h3 className="mb-2 text-xs font-medium text-muted-foreground flex items-center gap-2">
                                        <Globe className="h-3 w-3" /> Public GitHub Repositories
                                    </h3>
                                    <div className="space-y-1.5">
                                        {publicMatches.length === 0 && !isSearching ? (
                                            <div className="text-sm text-muted-foreground italic px-2 py-1">
                                                {searchTerm.length >= 3
                                                    ? "No matching public repositories found."
                                                    : "Type at least 3 characters to search."}
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
                                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {/* Repo Tabs */}
                            <div className="flex gap-2 overflow-x-auto pb-2">
                                {selectedList.map((repo) => (
                                    <button
                                        key={repo.full_name}
                                        className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${activeRepo === repo.full_name
                                                ? "bg-primary text-primary-foreground"
                                                : "bg-muted hover:bg-muted/80"
                                            }`}
                                        onClick={() => setActiveRepo(repo.full_name)}
                                    >
                                        {repo.full_name.split("/")[1]}
                                    </button>
                                ))}
                            </div>

                            {activeRepo && (
                                <div className="space-y-4">
                                    {/* Base Config */}
                                    <div className="grid gap-3 sm:grid-cols-3 p-3 border rounded-lg bg-slate-50 dark:bg-slate-900/20">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium">CI Provider</label>
                                            <Select
                                                value={baseConfigs[activeRepo]?.ci_provider || CIProvider.GITHUB_ACTIONS}
                                                onValueChange={(val) => setBaseConfigs(prev => ({
                                                    ...prev,
                                                    [activeRepo]: { ...prev[activeRepo], ci_provider: val }
                                                }))}
                                            >
                                                <SelectTrigger className="h-9">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value={CIProvider.GITHUB_ACTIONS}>GitHub Actions</SelectItem>
                                                    <SelectItem value={CIProvider.TRAVIS_CI}>Travis CI</SelectItem>
                                                    <SelectItem value={CIProvider.CIRCLECI}>CircleCI</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium">Max Builds</label>
                                            <Input
                                                type="number"
                                                placeholder="Unlimited"
                                                min={1}
                                                className="h-9"
                                                value={baseConfigs[activeRepo]?.max_builds || ""}
                                                onChange={(e) => setBaseConfigs(prev => ({
                                                    ...prev,
                                                    [activeRepo]: { ...prev[activeRepo], max_builds: e.target.value ? parseInt(e.target.value) : null }
                                                }))}
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium">Since Days</label>
                                            <Input
                                                type="number"
                                                placeholder="Unlimited"
                                                min={1}
                                                className="h-9"
                                                value={baseConfigs[activeRepo]?.since_days || ""}
                                                onChange={(e) => setBaseConfigs(prev => ({
                                                    ...prev,
                                                    [activeRepo]: { ...prev[activeRepo], since_days: e.target.value ? parseInt(e.target.value) : null }
                                                }))}
                                            />
                                        </div>
                                    </div>

                                    {/* Feature Config */}
                                    <FeatureConfigForm
                                        selectedFeatures={featureFormFeatures}
                                        repos={featureFormRepos}
                                        onChange={setFeatureConfigs}
                                    />

                                    {/* DAG Preview */}
                                    {dagLoading || templatesLoading ? (
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            Loading feature extraction plan...
                                        </div>
                                    ) : dagData && selectedFeatures.length > 0 && (
                                        <div className="space-y-3 pt-3 border-t">
                                            <h4 className="text-sm font-semibold">Feature Extraction Plan</h4>

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

                                            <FeatureDAGVisualization
                                                dagData={dagData as FeatureDAGData}
                                                selectedFeatures={selectedFeatures}
                                                onFeaturesChange={() => { }}
                                                className="h-[250px]"
                                            />

                                            <SelectedFeaturesPanelWithTooltips
                                                selectedFeatures={selectedFeatures}
                                                featuresData={featuresData}
                                            />
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t bg-background">
                    {importError && (
                        <div className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                            {importError}
                        </div>
                    )}
                    <SheetFooter className="flex-row justify-between sm:justify-between">
                        <Button variant="ghost" onClick={onClose}>
                            Cancel
                        </Button>
                        <div className="flex gap-2">
                            {step > 1 && (
                                <Button
                                    variant="outline"
                                    onClick={() => setStep((prev) => (prev > 1 ? ((prev - 1) as 1 | 2) : prev))}
                                >
                                    <ArrowLeft className="h-4 w-4 mr-1" />
                                    Back
                                </Button>
                            )}
                            {step === 1 ? (
                                <Button
                                    onClick={() => setStep(2)}
                                    disabled={selectedList.length === 0}
                                >
                                    Next
                                    <ArrowRight className="h-4 w-4 ml-1" />
                                </Button>
                            ) : (
                                <Button
                                    onClick={handleImport}
                                    disabled={importing || selectedList.length === 0}
                                >
                                    {importing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Import {selectedList.length} Repositories
                                </Button>
                            )}
                        </div>
                    </SheetFooter>
                </div>
            </SheetContent>
        </Sheet>
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
        <label className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors ${isSelected ? 'bg-slate-50 border-primary/50 dark:bg-slate-900' : 'hover:bg-slate-50 dark:hover:bg-slate-900/50'}`}>
            <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                checked={isSelected}
                onChange={onToggle}
            />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm truncate">{repo.full_name}</span>
                    {repo.private && (
                        <Badge variant="secondary" className="text-[10px] h-4 px-1">Private</Badge>
                    )}
                </div>
                <p className="text-xs text-muted-foreground line-clamp-1">
                    {repo.description || "No description provided"}
                </p>
            </div>
        </label>
    );
}
