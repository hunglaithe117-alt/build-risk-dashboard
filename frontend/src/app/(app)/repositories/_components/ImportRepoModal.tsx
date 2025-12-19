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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
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
import { SelectedFeaturesPanel } from "./SelectedFeaturesPanel";

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
    const [repoConfigs, setRepoConfigs] = useState<
        Record<string, {
            test_frameworks: string[];
            source_languages: string[];
            ci_provider: string;
            max_builds?: number | null;
            since_days?: number | null;
        }>
    >({});
    const [languageLoading, setLanguageLoading] = useState<Record<string, boolean>>({});
    const [languageError, setLanguageError] = useState<Record<string, string | null>>({});
    const [availableLanguages, setAvailableLanguages] = useState<Record<string, string[]>>({});
    const [featuresData, setFeaturesData] = useState<FeatureCategoryGroup[] | null>(null);
    const [featuresLoading, setFeaturesLoading] = useState(false);
    const [featuresError, setFeaturesError] = useState<string | null>(null);
    const [featureSearch, setFeatureSearch] = useState<Record<string, string>>({});
    const [frameworks, setFrameworks] = useState<string[]>([]);
    const [frameworksByLang, setFrameworksByLang] = useState<Record<string, string[]>>({});
    const [frameworksLoading, setFrameworksLoading] = useState(false);
    const [frameworksError, setFrameworksError] = useState<string | null>(null);
    const [frameworksLoaded, setFrameworksLoaded] = useState(false);

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
        // ... (rest of loadFeatures is unchanged, just need to match surrounding code)

        setFeaturesError(null);
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
        } catch (err) {
            console.error(err);
            setFeaturesError("Failed to load available features.");
        } finally {
            setFeaturesLoading(false);
        }
    }, [featuresData, featuresLoading, selectedRepos]);

    const loadFrameworks = useCallback(async () => {
        if (frameworksLoading || frameworksLoaded) return;
        setFrameworksLoading(true);
        setFrameworksError(null);
        try {
            const config = await featuresApi.getConfig();
            setFrameworks(config.frameworks || []);
            setFrameworksByLang(config.frameworks_by_language || {});
            setSupportedLanguages(config.languages || []);
        } catch (err) {
            console.error(err);
            setFrameworksError("Failed to load test frameworks.");
        } finally {
            setFrameworksLoaded(true);
            setFrameworksLoading(false);
        }
    }, [frameworksLoading, frameworksLoaded]);

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
            setStep(1);
            setSearchTerm("");
            setSelectedRepos({});
            setRepoConfigs({});
            setFeatureSearch({});
            setAvailableLanguages({});
            setLanguageLoading({});
            setLanguageError({});
            setPrivateMatches([]);
            setPublicMatches([]);
            setSearchError(null);
            setImportError(null);
            setFeaturesData(null);
            setDagData(null);
            loadFrameworks();
            performSearch("", true);
            setActiveRepo(null);
        }
    }, [isOpen, performSearch, loadFrameworks]);

    const [supportedLanguages, setSupportedLanguages] = useState<string[]>([]);

    const fetchLanguages = useCallback(
        async (repo: RepoSuggestion) => {
            setLanguageLoading((prev) => ({ ...prev, [repo.full_name]: true }));
            setLanguageError((prev) => ({ ...prev, [repo.full_name]: null }));
            try {
                const res = await reposApi.detectLanguages(repo.full_name);
                const detected = res.languages || [];

                const validLangs = supportedLanguages.length > 0
                    ? detected.filter(l => supportedLanguages.some(sl => sl.toLowerCase() === l.toLowerCase()))
                    : detected;

                setAvailableLanguages((prev) => ({ ...prev, [repo.full_name]: validLangs }));

                setRepoConfigs((current) => {
                    const existing = current[repo.full_name];
                    return {
                        ...current,
                        [repo.full_name]: {
                            test_frameworks: existing?.test_frameworks || [],
                            source_languages: existing?.source_languages || [],
                            ci_provider: existing?.ci_provider || CIProvider.GITHUB_ACTIONS,
                            max_builds: existing?.max_builds ?? null,
                        },
                    };
                });
            } catch (err) {
                console.error(err);
                setLanguageError((prev) => ({
                    ...prev,
                    [repo.full_name]: "Failed to detect languages",
                }));
            } finally {
                setLanguageLoading((prev) => ({ ...prev, [repo.full_name]: false }));
            }
        },
        [supportedLanguages]
    );

    const toggleSelection = (repo: RepoSuggestion) => {
        setSelectedRepos((prev) => {
            const next = { ...prev };
            if (next[repo.full_name]) {
                delete next[repo.full_name];
                // Remove config and all related states
                setRepoConfigs((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
                // Clean up related states to prevent stale data
                setAvailableLanguages((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
                setLanguageLoading((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
                setLanguageError((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
                setFeatureSearch((current) => {
                    const updated = { ...current };
                    delete updated[repo.full_name];
                    return updated;
                });
            } else {
                next[repo.full_name] = repo;
                // Initialize config
                setRepoConfigs((current) => ({
                    ...current,
                    [repo.full_name]: {
                        test_frameworks: [],
                        source_languages: [],
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
    const anyLanguageLoading = selectedList.some((repo) => languageLoading[repo.full_name]);
    const anyLanguageMissing = selectedList.some(
        (repo) => !repoConfigs[repo.full_name]?.source_languages?.length
    );
    const step2Loading =
        frameworksLoading ||
        selectedList.some(
            (repo) => languageLoading[repo.full_name] || !availableLanguages[repo.full_name]
        );

    useEffect(() => {
        if (selectedList.length === 0) {
            setActiveRepo(null);
            return;
        }
        if (!activeRepo || !selectedRepos[activeRepo]) {
            setActiveRepo(selectedList[0].full_name);
        }
    }, [selectedList, activeRepo, selectedRepos]);

    const getFrameworkSuggestions = useCallback(
        (config: {
            source_languages: string[];
        }) => {
            const languageSet = new Set(config.source_languages.map((l) => l.toLowerCase()));
            // Get frameworks from API data based on selected languages
            const fromApi = Array.from(
                new Set(
                    Array.from(languageSet).flatMap((lang) => {
                        // Try exact match first, then try aliases (e.g., "c++" -> "cpp")
                        return frameworksByLang[lang] ||
                            frameworksByLang[lang.replace("+", "p")] ||
                            [];
                    })
                )
            );
            if (fromApi.length) return fromApi;
            return frameworks || [];
        },
        [frameworksByLang, frameworks]
    );

    // Load features and detect languages when entering config/feature steps
    useEffect(() => {
        if (step < 2) return;
        void loadFeatures();
        void loadFrameworks();
        selectedList.forEach((repo) => {
            if (!availableLanguages[repo.full_name]) {
                void fetchLanguages(repo);
            }
        });
        if (step === 2) {
            void loadDAG();
            void loadSelectedTemplate();
            void loadFeatures(); // Load feature descriptions for tooltips
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, selectedList.length]);

    const handleImport = async () => {
        if (!selectedList.length) return;
        setImporting(true);
        setImportError(null);

        try {
            const payloads: RepoImportPayload[] = selectedList.map((repo) => {
                const config = repoConfigs[repo.full_name];
                return {
                    full_name: repo.full_name,
                    provider: "github",
                    test_frameworks: config.test_frameworks,
                    source_languages: config.source_languages,
                    ci_provider: config.ci_provider,
                    max_builds: config.max_builds ?? null,
                    since_days: config.since_days ?? null,
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
                                    {step2Loading || !activeRepo ? (
                                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Loading languages & frameworks...
                                        </div>
                                    ) : (
                                        <div className="space-y-4">

                                            <RepoConfigItem
                                                key={activeRepo}
                                                repo={
                                                    selectedList.find((r) => r.full_name === activeRepo) ||
                                                    selectedList[0]
                                                }
                                                config={
                                                    repoConfigs[activeRepo] || {
                                                        test_frameworks: [],
                                                        source_languages: [],
                                                        ci_provider: CIProvider.GITHUB_ACTIONS,
                                                        max_builds: null,
                                                    }
                                                }
                                                languageLoading={languageLoading[activeRepo]}
                                                languageError={languageError[activeRepo]}
                                                availableLanguages={availableLanguages[activeRepo] || []}
                                                availableFrameworks={getFrameworkSuggestions(
                                                    repoConfigs[activeRepo] || {
                                                        source_languages: [],
                                                    }
                                                )}
                                                frameworksError={frameworksError}
                                                frameworksLoading={frameworksLoading}
                                                frameworks={frameworks}
                                                onChange={(newConfig) =>
                                                    setRepoConfigs((prev) => ({
                                                        ...prev,
                                                        [activeRepo]: newConfig,
                                                    }))
                                                }
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
                                    disabled={selectedList.length === 0 || frameworksLoading || anyLanguageLoading}
                                >
                                    Next
                                </Button>
                            ) : (
                                // Step 2 is now final - Import button directly
                                <Button
                                    onClick={handleImport}
                                    disabled={
                                        importing ||
                                        frameworksLoading ||
                                        anyLanguageLoading ||
                                        anyLanguageMissing ||
                                        selectedList.length === 0
                                    }
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

function RepoConfigItem({
    repo,
    config,
    languageLoading,
    languageError,
    availableLanguages,
    availableFrameworks,
    frameworksError,
    frameworksLoading,
    frameworks,
    onChange,
}: {
    repo: RepoSuggestion;
    config: {
        test_frameworks: string[];
        source_languages: string[];
        ci_provider: string;
        features?: string[];
        max_builds?: number | null;
        since_days?: number | null;
    };
    languageLoading?: boolean;
    languageError?: string | null;
    availableLanguages?: string[];
    availableFrameworks?: string[];
    frameworksError?: string | null;
    frameworksLoading?: boolean;
    frameworks?: string[];
    onChange: (config: any) => void;
}) {
    const toggleFramework = (framework: string) => {
        const current = config.test_frameworks;
        const next = current.includes(framework)
            ? current.filter((f) => f !== framework)
            : [...current, framework];
        onChange({ ...config, test_frameworks: next });
    };

    const toggleLanguage = (language: string) => {
        const current = config.source_languages;
        const next = current.includes(language)
            ? current.filter((l) => l !== language)
            : [...current, language];
        onChange({ ...config, source_languages: next });
    };

    return (
        <div className="rounded-xl border p-4 space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="font-semibold">{repo.full_name}</h3>
                <Badge variant="outline">{repo.private ? "Private" : "Public"}</Badge>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
                <div>
                    <label className="text-xs font-semibold text-muted-foreground uppercase mb-2 block">
                        Test Frameworks
                    </label>
                    <div className="space-y-2">
                        {frameworksError ? (
                            <div className="text-xs text-red-600 dark:text-red-400">
                                {frameworksError}
                            </div>
                        ) : null}
                        {frameworksLoading ? (
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Loader2 className="h-3 w-3 animate-spin" /> Loading frameworks...
                            </div>
                        ) : null}
                        {!frameworksLoading && config.source_languages.length === 0 ? (
                            <div className="text-xs text-muted-foreground">
                                Select a source language to see suggested frameworks.
                            </div>
                        ) : null}
                        {!frameworksLoading && config.source_languages.length > 0 && (availableFrameworks?.length ?? 0) === 0 ? (
                            <div className="text-xs text-muted-foreground">
                                No framework suggestions for the selected languages. You can still choose from all frameworks.
                            </div>
                        ) : null}
                        <div className="grid grid-cols-2 gap-2">
                            {(availableFrameworks && availableFrameworks.length
                                ? availableFrameworks
                                : frameworks && frameworks.length
                                    ? frameworks
                                    : []
                            ).map((fw) => (
                                <label key={fw} className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="rounded border-gray-300"
                                        checked={config.test_frameworks.includes(fw)}
                                        onChange={() => toggleFramework(fw)}
                                        disabled={frameworksLoading || config.source_languages.length === 0}
                                    />
                                    {fw}
                                </label>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground uppercase block">
                        Source Languages
                    </label>
                    {languageLoading ? (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Loader2 className="h-3 w-3 animate-spin" /> Detecting languages from GitHub...
                        </div>
                    ) : null}
                    {languageError ? (
                        <div className="text-xs text-red-600 dark:text-red-400">
                            {languageError}
                        </div>
                    ) : null}

                    <div className="flex flex-wrap gap-2">
                        {(availableLanguages || []).map((lang) => (
                            <Badge
                                key={lang}
                                variant={config.source_languages.includes(lang) ? "default" : "outline"}
                                className="cursor-pointer"
                                onClick={() => toggleLanguage(lang)}
                            >
                                {lang}
                            </Badge>
                        ))}
                    </div>
                    {(!availableLanguages || availableLanguages.length === 0) && !languageLoading ? (
                        <div className="text-xs text-muted-foreground">
                            No languages detected. Try syncing repo or add manually later.
                        </div>
                    ) : null}
                    {config.source_languages.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                            {config.source_languages.map((lang) => (
                                <Badge
                                    key={lang}
                                    variant="secondary"
                                    className="flex items-center gap-1"
                                >
                                    {lang}
                                    <button
                                        type="button"
                                        className="ml-1 text-xs"
                                        onClick={() => toggleLanguage(lang)}
                                    >
                                        ×
                                    </button>
                                </Badge>
                            ))}
                        </div>
                    ) : null}
                </div>
            </div>

            <div className="space-y-2 max-w-full">
                <label className="text-xs font-semibold text-muted-foreground uppercase block">
                    Max Builds to Ingest
                </label>
                <Input
                    type="number"
                    min={1}
                    placeholder="e.g. 50"
                    value={config.max_builds ?? ""}
                    onChange={(e) =>
                        onChange({
                            ...config,
                            max_builds: e.target.value ? Number(e.target.value) : null,
                        })
                    }
                />
                <p className="text-xs text-muted-foreground">
                    Leave blank to ingest all available workflow runs.
                </p>
            </div>

            <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase mb-2 block">
                    Since
                </label>
                <select
                    className="w-full rounded-lg border bg-transparent px-3 py-2 text-sm"
                    value={config.since_days || ""}
                    onChange={(e) =>
                        onChange({
                            ...config,
                            since_days: e.target.value ? Number(e.target.value) : null,
                        })
                    }
                >
                    <option value="">All time (no limit)</option>
                    <option value="7">Last 7 days</option>
                    <option value="14">Last 14 days</option>
                    <option value="30">Last 30 days</option>
                    <option value="60">Last 60 days</option>
                    <option value="90">Last 90 days</option>
                    <option value="180">Last 6 months</option>
                    <option value="365">Last year</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                    Only ingest builds from the selected time period.
                </p>
            </div>

            <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase mb-2 block">
                    CI Provider
                </label>
                <select
                    className="w-full rounded-lg border bg-transparent px-3 py-2 text-sm"
                    value={config.ci_provider}
                    onChange={(e) => onChange({ ...config, ci_provider: e.target.value })}
                >
                    <option value={CIProvider.GITHUB_ACTIONS}>GitHub Actions</option>
                    <option value={CIProvider.GITLAB_CI}>GitLab CI</option>
                    <option value={CIProvider.CIRCLECI}>CircleCI</option>
                    <option value={CIProvider.TRAVIS_CI}>Travis CI</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                    Select the CI/CD system used by this repository.
                </p>
            </div>
        </div>
    );
}

function FeaturesStep({
    selectedList,
    repoConfigs,
    availableFeatures,
    featuresLoading,
    featuresError,
    templates,
    searchTerms,
    onSearchChange,
    onUpdateFeatures,
    onApplyTemplate,
    dagData,
    dagLoading,
    onLoadDAG,
}: {
    selectedList: RepoSuggestion[];
    repoConfigs: Record<string, { feature_names?: string[] }>;
    availableFeatures: FeatureCategoryGroup[] | null;
    featuresLoading: boolean;
    featuresError: string | null;
    templates: DatasetTemplateRecord[];
    searchTerms: Record<string, string>;
    onSearchChange: (fullName: string, value: string) => void;
    onUpdateFeatures: (fullName: string, featureNames: string[]) => void;
    onApplyTemplate: (fullName: string, featureNames: string[]) => void;
    dagData: FeatureDAGData | null;
    dagLoading: boolean;
    onLoadDAG: () => void;
}) {
    const groupedFeatures = availableFeatures || [];
    const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
    const [viewMode, setViewMode] = useState<"list" | "dag">("dag");

    // Load DAG when switching to DAG view
    useEffect(() => {
        if (viewMode === "dag" && !dagData && !dagLoading) {
            onLoadDAG();
        }
    }, [viewMode, dagData, dagLoading, onLoadDAG]);

    const toggleCategory = (cat: string) => {
        setCollapsed((prev) => {
            const next = new Set(prev);
            if (next.has(cat)) {
                next.delete(cat);
            } else {
                next.add(cat);
            }
            return next;
        });
    };

    const filterMatch = (feat: FeatureDefinitionSummary, term: string) => {
        if (!term.trim()) return true;
        const q = term.toLowerCase();
        return (
            feat.name.toLowerCase().includes(q) ||
            (feat.display_name || "").toLowerCase().includes(q) ||
            (feat.category || "").toLowerCase().includes(q)
        );
    };

    // Mappings for ID <-> Name resolution
    const { nameToId, idToName, idLabels, nameLabels } = useMemo(() => {
        const n2i: Record<string, string> = {};
        const i2n: Record<string, string> = {};
        const labels: Record<string, string> = {}; // ID/Name -> Label mapping (since keys for nameLabels will be names)


        groupedFeatures.forEach((cat) => {
            cat.features.forEach((feat) => {
                n2i[feat.name] = feat.id;
                i2n[feat.id] = feat.name;
                labels[feat.id] = feat.display_name || feat.name;
                labels[feat.name] = feat.display_name || feat.name; // Add name mapping too
            });
        });
        return { nameToId: n2i, idToName: i2n, idLabels: labels, nameLabels: labels };
    }, [groupedFeatures]);

    // Get node labels from DAG data
    const nodeLabels = useMemo(() => {
        const labels: Record<string, string> = {};
        dagData?.nodes.forEach((node) => {
            labels[node.id] = node.label;
        });
        return labels;
    }, [dagData]);

    // Get active (selected) nodes based on selected features
    const getActiveNodes = useCallback((selectedNames: string[]): Set<string> => {
        if (!dagData) return new Set();
        const selectedSet = new Set(selectedNames);
        const active = new Set<string>();
        dagData.nodes.forEach((node) => {
            // Check if ANY of the feature names in the node are selected
            if (node.features.some((f) => selectedSet.has(f))) {
                active.add(node.id);
            }
        });
        return active;
    }, [dagData]);

    return (
        <div className="space-y-4">
            {/* View Mode Toggle */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={() => setViewMode("dag")}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${viewMode === "dag"
                            ? "bg-blue-500 text-white"
                            : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                            }`}
                    >
                        <span className="flex items-center gap-1.5">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                            Graph View
                        </span>
                    </button>
                    <button
                        type="button"
                        onClick={() => setViewMode("list")}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${viewMode === "list"
                            ? "bg-blue-500 text-white"
                            : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                            }`}
                    >
                        <span className="flex items-center gap-1.5">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                            </svg>
                            List View
                        </span>
                    </button>
                </div>
                <Badge variant="outline" className="text-xs">
                    {dagData?.total_features || 0} features available
                </Badge>
            </div>

            {featuresLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading features...
                </div>
            ) : null}
            {featuresError ? (
                <div className="text-sm text-red-600 dark:text-red-400">{featuresError}</div>
            ) : null}

            {selectedList.map((repo) => {
                const current = repoConfigs[repo.full_name]?.feature_names || [];
                const searchTerm = searchTerms[repo.full_name] || "";
                const activeNodes = getActiveNodes(current);

                const tplSearchKey = `${repo.full_name}::_template`;
                const tplShowKey = `${repo.full_name}::_showTemplates`;
                const tplSelIdKey = `${repo.full_name}::_selectedTemplateId`;

                return (
                    <div key={repo.full_name} className="rounded-xl border p-4 space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h3 className="font-semibold">{repo.full_name}</h3>
                                <p className="text-xs text-muted-foreground">
                                    {viewMode === "dag"
                                        ? "Click on nodes to select/deselect features"
                                        : "Select features or apply a template for this repository."
                                    }
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge variant="secondary">
                                    {current.length} selected
                                </Badge>
                                <Badge variant="outline">{repo.private ? "Private" : "Public"}</Badge>
                            </div>
                        </div>

                        {/* Templates */}
                        {/* Template Selection - Searchable Dropdown */}
                        <div className="space-y-4 rounded-lg border p-4 bg-slate-50/50 dark:bg-slate-900/20">
                            <h4 className="text-sm font-semibold mb-2">Apply Feature Template</h4>
                            <div className="flex flex-col gap-4">
                                <div className="relative">
                                    <div className="flex gap-2">
                                        <div className="relative flex-1">
                                            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                                            <Input
                                                placeholder="Search templates..."
                                                className="pl-9"
                                                value={searchTerms[tplSearchKey] || ""}
                                                onChange={(e) => onSearchChange(tplSearchKey, e.target.value)}
                                                onFocus={() => onSearchChange(tplShowKey, "true")}
                                                // We delay hiding to allow clicking items
                                                onBlur={() => setTimeout(() => onSearchChange(tplShowKey, "false"), 200)}
                                            />

                                            {/* Dropdown List */}
                                            {searchTerms[tplShowKey] === "true" && (
                                                <div className="absolute top-full left-0 right-0 mt-1 max-h-[300px] overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-md z-50 p-1 bg-white dark:bg-slate-950">
                                                    {templates
                                                        .filter(t => !searchTerms[tplSearchKey] || t.name.toLowerCase().includes(searchTerms[tplSearchKey].toLowerCase()))
                                                        .map(tpl => (
                                                            <div
                                                                key={tpl.id}
                                                                className="flex flex-col gap-1 rounded-sm px-2 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                                                                onClick={() => {
                                                                    onSearchChange(tplSearchKey, tpl.name);
                                                                    onSearchChange(tplSelIdKey, tpl.id);
                                                                }}
                                                            >
                                                                <div className="flex items-center justify-between">
                                                                    <span className="font-medium text-sm">{tpl.name}</span>
                                                                    <Badge variant="secondary" className="text-[10px]">{(tpl.feature_names || []).length} feats</Badge>
                                                                </div>
                                                                <span className="text-xs text-muted-foreground line-clamp-1">{tpl.description}</span>
                                                            </div>
                                                        ))
                                                    }
                                                    {templates.length === 0 && <div className="p-2 text-sm text-muted-foreground text-center">No templates found</div>}
                                                </div>
                                            )}
                                        </div>
                                        <Button
                                            disabled={!searchTerms[tplSelIdKey]}
                                            onClick={() => {
                                                const tplId = searchTerms[tplSelIdKey];
                                                const tpl = templates.find(t => t.id === tplId);
                                                if (tpl) {
                                                    const selectedFeatures = tpl.feature_names || [];
                                                    onApplyTemplate(repo.full_name, selectedFeatures);
                                                }
                                            }}
                                        >
                                            Apply
                                        </Button>
                                    </div>
                                </div>

                                {/* Active Template Details */}
                                {searchTerms[tplSelIdKey] && (() => {
                                    const tpl = templates.find(t => t.id === searchTerms[tplSelIdKey]);
                                    if (!tpl) return null;
                                    return (
                                        <div className="flex items-start gap-3 p-3 text-sm border rounded-md bg-background">
                                            <div className="flex-1 space-y-2">
                                                <div className="font-medium">Selected: {tpl.name}</div>
                                                <p className="text-muted-foreground text-xs">{tpl.description}</p>
                                                <div className="flex flex-wrap gap-1">
                                                    {(tpl.tags || []).map((b) => (
                                                        <Badge key={b} variant="outline" className="text-[10px]">
                                                            {b}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>

                        {viewMode === "dag" ? (
                            <div className="space-y-4">
                                {/* DAG Visualization */}
                                <FeatureDAGVisualization
                                    className="w-full h-[500px]"
                                    dagData={dagData}
                                    selectedFeatures={current}
                                    onFeaturesChange={(names) => {
                                        onUpdateFeatures(repo.full_name, names);
                                    }}
                                    isLoading={dagLoading}
                                />

                                {/* Selected Features Panel */}
                                <SelectedFeaturesPanel
                                    selectedFeatures={current}
                                    featureLabels={nameLabels}

                                    onRemove={(featureName) =>
                                        onUpdateFeatures(
                                            repo.full_name,
                                            current.filter((name) => name !== featureName)
                                        )
                                    }
                                    onClear={() => onUpdateFeatures(repo.full_name, [])}
                                />

                                {/* Extraction Plan Timeline */}
                                {dagData && (
                                    <ExtractionPlanTimeline
                                        executionLevels={dagData.execution_levels}
                                        nodeLabels={nodeLabels}
                                        activeNodes={activeNodes}
                                    />
                                )}
                            </div>
                        ) : (
                            <>
                                {/* Search input for list view */}
                                <div className="flex items-center gap-2">
                                    <Input
                                        placeholder="Search features in this repo..."
                                        value={searchTerm}
                                        onChange={(e) => onSearchChange(repo.full_name, e.target.value)}
                                        className="flex-1"
                                    />
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => onUpdateFeatures(repo.full_name, [])}
                                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                                        disabled={current.length === 0}
                                    >
                                        <X className="h-4 w-4 mr-1" />
                                        Clear All
                                    </Button>
                                </div>

                                {/* List View */}
                                <div className="space-y-3 max-w-full">
                                    {!featuresLoading && groupedFeatures.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">No features available.</div>
                                    ) : null}
                                    {groupedFeatures.map((cat) => {
                                        const visibleFeatures = cat.features.filter((feat) =>
                                            filterMatch(feat, searchTerm)
                                        );
                                        if (!visibleFeatures.length) return null;

                                        const isCollapsed = collapsed.has(cat.category);
                                        return (
                                            <div key={cat.category} className="space-y-2">
                                                <div className="flex items-center justify-between">
                                                    <div className="text-[11px] uppercase text-muted-foreground font-semibold">
                                                        {cat.display_name || cat.category}
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <Badge variant="secondary">{visibleFeatures.length} features</Badge>
                                                        <Button
                                                            type="button"
                                                            size="sm"
                                                            variant="ghost"
                                                            onClick={() => toggleCategory(cat.category)}
                                                            className="h-7 px-2 text-xs"
                                                        >
                                                            {isCollapsed ? "Expand" : "Collapse"}
                                                        </Button>
                                                    </div>
                                                </div>
                                                {!isCollapsed && (
                                                    <div className="grid gap-2 sm:grid-cols-2">
                                                        {visibleFeatures.map((feat) => (
                                                            <label
                                                                key={feat.name}
                                                                className="flex items-start gap-2 rounded-lg border border-transparent p-2 hover:border-slate-200 dark:hover:border-slate-800"
                                                            >
                                                                <Checkbox
                                                                    checked={current.includes(feat.name)}
                                                                    onCheckedChange={() => {
                                                                        const next = current.includes(feat.name)
                                                                            ? current.filter((n) => n !== feat.name)
                                                                            : [...current, feat.name];
                                                                        onUpdateFeatures(repo.full_name, next);
                                                                    }}
                                                                />
                                                                <div className="space-y-1">
                                                                    <div className="flex items-center gap-2">
                                                                        <span className="text-sm font-semibold">{feat.display_name || feat.name}</span>
                                                                        <Badge variant="outline" className="text-[11px]">
                                                                            {feat.data_type}
                                                                        </Badge>
                                                                    </div>
                                                                    <p className="text-xs text-muted-foreground line-clamp-2">
                                                                        {feat.description}
                                                                    </p>
                                                                </div>
                                                            </label>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
