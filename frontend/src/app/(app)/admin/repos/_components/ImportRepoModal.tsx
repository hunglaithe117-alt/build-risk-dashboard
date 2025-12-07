"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import {
    AlertCircle,
    CheckCircle2,
    Loader2,
    RefreshCw,
    Search,
    X,
    Globe,
    Lock,

} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { integrationApi, reposApi, featuresApi, datasetsApi } from "@/lib/api";
import {
    RepoSuggestion,
    RepoImportPayload,
    TestFramework,
    CIProvider,
    FeatureDefinitionSummary,
    DatasetTemplateRecord,
} from "@/types";
import { useAuth } from "@/contexts/auth-context";
import { useDebounce } from "@/hooks/use-debounce";
import { Input } from "@/components/ui/input";
import { FeatureDAGVisualization, type FeatureDAGData } from "./FeatureDAGVisualization";
import { SelectedFeaturesPanel } from "./SelectedFeaturesPanel";
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

// Map languages to suggested test frameworks
const FRAMEWORKS_BY_LANG: Record<string, string[]> = {
    python: [TestFramework.PYTEST, TestFramework.UNITTEST],
    ruby: [TestFramework.RSPEC, TestFramework.MINITEST, TestFramework.TESTUNIT, TestFramework.CUCUMBER],
    java: [TestFramework.JUNIT, TestFramework.TESTNG],
};



interface ImportRepoModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImport: () => void;
}

export function ImportRepoModal({ isOpen, onClose, onImport }: ImportRepoModalProps) {
    const [step, setStep] = useState<1 | 2 | 3>(1);
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
            feature_ids: string[];  // FeatureDefinition ObjectIds
            max_builds?: number | null;
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
            setPrivateMatches(data.private_matches);
            setPublicMatches(data.public_matches);
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
            const res = await reposApi.getTestFrameworks();
            setFrameworks(res.frameworks || []);
            setFrameworksByLang(res.by_language || {});
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

    const loadTemplates = useCallback(async () => {
        if (templatesLoading || templates.length > 0) return;
        setTemplatesLoading(true);
        try {
            const data = await datasetsApi.listTemplates();
            setTemplates(data.items);
        } catch (err) {
            console.error("Failed to load templates:", err);
        } finally {
            setTemplatesLoading(false);
        }
    }, [templatesLoading, templates.length]);

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

    const handleSync = async () => {
        setIsSearching(true);
        try {
            await reposApi.sync();
            await performSearch(searchTerm, true);
        } catch (err) {
            console.error(err);
            setSearchError("Failed to sync repositories from GitHub.");
            setIsSearching(false);
        }
    };

    const [supportedLanguages, setSupportedLanguages] = useState<string[]>([]);

    useEffect(() => {
        if (isOpen) {
            featuresApi.getSupportedLanguages().then((data) => {
                setSupportedLanguages(data.languages);
            }).catch(console.error);
        }
    }, [isOpen]);

    const fetchLanguages = useCallback(
        async (repo: RepoSuggestion) => {
            setLanguageLoading((prev) => ({ ...prev, [repo.full_name]: true }));
            setLanguageError((prev) => ({ ...prev, [repo.full_name]: null }));
            try {
                const res = await reposApi.detectLanguages(repo.full_name);
                const detected = res.languages || [];

                // Filter by supported languages if loaded
                const validLangs = supportedLanguages.length > 0
                    ? detected.filter(l => supportedLanguages.some(sl => sl.toLowerCase() === l.toLowerCase()))
                    : detected;

                setAvailableLanguages((prev) => ({ ...prev, [repo.full_name]: validLangs }));

                setRepoConfigs((current) => {
                    const existing = current[repo.full_name];
                    const hasExistingLangs = existing?.source_languages?.length > 0;
                    return {
                        ...current,
                        [repo.full_name]: {
                            test_frameworks: existing?.test_frameworks || [],
                            source_languages: hasExistingLangs ? existing.source_languages : validLangs,
                            ci_provider: existing?.ci_provider || CIProvider.GITHUB_ACTIONS,
                            feature_ids: existing?.feature_ids || [],
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
                // Remove config
                setRepoConfigs((current) => {
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
                        feature_ids: [],
                        max_builds: null,
                        ingest_start_date: null,
                        ingest_end_date: null,
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
            const fromApi = Array.from(
                new Set(
                    Array.from(languageSet).flatMap((lang) => frameworksByLang[lang] || [])
                )
            );
            const fromPreset = Array.from(
                new Set(
                    Array.from(languageSet).flatMap((lang) => FRAMEWORKS_BY_LANG[lang] || [])
                )
            );
            if (fromApi.length) return fromApi;
            if (fromPreset.length) return fromPreset;
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
            loadFeatures();
            loadFrameworks();
            loadDAG();
            loadTemplates();
        }
    }, [step, loadFeatures, loadFrameworks, loadDAG, loadTemplates, selectedList, availableLanguages, fetchLanguages]);

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
                    installation_id: repo.installation_id, // Can be undefined for public repos
                    test_frameworks: config.test_frameworks,
                    source_languages: config.source_languages,
                    ci_provider: config.ci_provider,
                    feature_ids: config.feature_ids,
                    max_builds: config.max_builds ?? null,
                    ingest_start_date: (config as any).ingest_start_date || null,
                    ingest_end_date: (config as any).ingest_end_date || null,
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

    const { status } = useAuth();
    const [isAppInstalled, setIsAppInstalled] = useState(false);
    const [isPolling, setIsPolling] = useState(false);

    // Check installation status on mount and when status changes
    useEffect(() => {
        if (status?.app_installed) {
            setIsAppInstalled(true);
        } else {
            checkInstallation();
        }
    }, [status]);

    const checkInstallation = async () => {
        try {
            const response = await integrationApi.syncInstallations();

            if (response.installations.length > 0) {
                setIsAppInstalled(true);
            }
        } catch (error) {
            console.error("Failed to check installation status", error);
        }
    };

    const handleInstallApp = () => {
        window.open("https://github.com/apps/builddefection", "_blank");
        setIsPolling(true);
    };

    // Polling logic
    useEffect(() => {
        let intervalId: NodeJS.Timeout;
        let attempts = 0;
        const maxAttempts = 24; // 2 minutes (5s interval)

        if (isPolling && !isAppInstalled) {
            intervalId = setInterval(async () => {
                attempts++;
                await checkInstallation();

                // If installed (checked via effect on status) or max attempts reached
                if (attempts >= maxAttempts) {
                    setIsPolling(false);
                }
            }, 5000);
        }

        return () => {
            if (intervalId) clearInterval(intervalId);
        };
    }, [isPolling, isAppInstalled]);

    // Stop polling if installed
    useEffect(() => {
        if (isAppInstalled) {
            setIsPolling(false);
        }
    }, [isAppInstalled]);

    if (!isOpen) return null;

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
                <div className="w-full max-w-7xl h-[90vh] rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-950 border dark:border-slate-800 flex flex-col overflow-hidden">
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold">Import Repositories</h2>
                            <p className="text-sm text-muted-foreground">
                                Step {step} of 3:{" "}
                                {step === 1
                                    ? "Select repositories"
                                    : step === 2
                                        ? "Configure languages & frameworks"
                                        : "Choose features"}
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

                    {!isAppInstalled ? (
                        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-900/20">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                                <div className="flex-1">
                                    <h3 className="text-sm font-medium text-amber-900 dark:text-amber-200">
                                        GitHub App Required
                                    </h3>
                                    <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
                                        To import private repositories and enable automatic build tracking, you must install the BuildGuard GitHub App.
                                    </p>
                                    <div className="mt-3 flex items-center gap-3">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="border-amber-200 bg-white text-amber-900 hover:bg-amber-50 hover:text-amber-900 dark:border-amber-800 dark:bg-slate-950 dark:text-amber-200 dark:hover:bg-amber-900/20"
                                            onClick={handleInstallApp}
                                            disabled={isPolling}
                                        >
                                            {isPolling ? (
                                                <>
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                    Checking installation...
                                                </>
                                            ) : (
                                                "Install GitHub App"
                                            )}
                                        </Button>
                                        {isPolling && (
                                            <span className="text-xs text-amber-700 dark:text-amber-300 animate-pulse">
                                                Listening for installation...
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="mb-6 rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-900/50 dark:bg-green-900/20">
                            <div className="flex items-center gap-3">
                                <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                                <div>
                                    <h3 className="text-sm font-medium text-green-900 dark:text-green-200">
                                        GitHub App Connected
                                    </h3>
                                    <p className="text-sm text-green-700 dark:text-green-300">
                                        Your private repositories are ready to be imported.
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex-1 overflow-y-auto">
                        {step === 1 ? (
                            <div className="space-y-6">
                                <div className="flex gap-2">
                                    <div className="relative flex-1">
                                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <input
                                            type="text"
                                            className="w-full rounded-lg border border-slate-200 bg-transparent pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-0 focus:border-primary"
                                            placeholder="Search repositories (e.g. owner/repo)..."
                                            value={searchTerm}
                                            onChange={(e) => setSearchTerm(e.target.value)}
                                        />
                                    </div>
                                    <Button
                                        variant="outline"
                                        onClick={handleSync}
                                        title="Sync private repositories from GitHub App"
                                        disabled={isSearching}
                                    >
                                        <RefreshCw className={`h-4 w-4 ${isSearching ? "animate-spin" : ""}`} />
                                    </Button>
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
                                            <Lock className="h-3 w-3" /> Your Repositories (App Installed)
                                        </h3>
                                        <div className="space-y-2">
                                            {privateMatches.length === 0 && !isSearching ? (
                                                <div className="text-sm text-muted-foreground italic px-2">
                                                    No matching private repositories found.
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
                                    {step === 2 ? (
                                        step2Loading || !activeRepo ? (
                                            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                Loading languages & frameworks...
                                            </div>
                                        ) : (
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
                                                        feature_ids: [],
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
                                        )
                                    ) : (
                                        <FeaturesStep
                                            selectedList={
                                                activeRepo
                                                    ? selectedList.filter((r) => r.full_name === activeRepo)
                                                    : []
                                            }
                                            repoConfigs={repoConfigs}
                                            availableFeatures={featuresData}
                                            featuresLoading={featuresLoading}
                                            featuresError={featuresError}
                                            templates={templates}
                                            searchTerms={featureSearch}
                                            onSearchChange={(repoName, val) =>
                                                setFeatureSearch((prev) => ({ ...prev, [repoName]: val }))
                                            }
                                            onUpdateFeatures={(fullName, featureIds) =>
                                                setRepoConfigs((prev) => ({
                                                    ...prev,
                                                    [fullName]: {
                                                        ...prev[fullName],
                                                        feature_ids: featureIds,
                                                    },
                                                }))
                                            }
                                            onApplyTemplate={(fullName, featureIds) =>
                                                setRepoConfigs((prev) => ({
                                                    ...prev,
                                                    [fullName]: {
                                                        ...prev[fullName],
                                                        feature_ids: Array.from(
                                                            new Set([...(prev[fullName]?.feature_ids || []), ...featureIds])
                                                        ),
                                                    },
                                                }))
                                            }
                                            dagData={dagData}
                                            dagLoading={dagLoading}
                                            onLoadDAG={loadDAG}
                                        />
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
                                        setStep((prev) => (prev > 1 ? ((prev - 1) as 1 | 2 | 3) : prev))
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
                                    Next ({selectedList.length})
                                </Button>
                            ) : step === 2 ? (
                                <Button
                                    onClick={() => setStep(3)}
                                    disabled={
                                        frameworksLoading ||
                                        anyLanguageLoading ||
                                        anyLanguageMissing ||
                                        selectedList.length === 0
                                    }
                                >
                                    Next (Features)
                                </Button>
                            ) : (
                                <Button
                                    onClick={handleImport}
                                    disabled={importing || frameworksLoading || anyLanguageLoading}
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
        ingest_start_date?: string | null;
        ingest_end_date?: string | null;
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
                                    : Object.values(TestFramework)
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
                <div className="grid grid-cols-2 gap-4 mt-3">
                    <div className="space-y-1">
                        <label className="text-xs font-semibold text-muted-foreground uppercase block">
                            Start Date
                        </label>
                        <Input
                            type="date"
                            value={config.ingest_start_date || ""}
                            onChange={(e) =>
                                onChange({
                                    ...config,
                                    ingest_start_date: e.target.value || null,
                                })
                            }
                            className="[&::-webkit-calendar-picker-indicator]:ml-auto"
                        />
                    </div>
                    <div className="space-y-1">
                        <label className="text-xs font-semibold text-muted-foreground uppercase block">
                            End Date
                        </label>
                        <Input
                            type="date"
                            value={config.ingest_end_date || ""}
                            onChange={(e) =>
                                onChange({
                                    ...config,
                                    ingest_end_date: e.target.value || null,
                                })
                            }
                            className="[&::-webkit-calendar-picker-indicator]:ml-auto"
                        />
                    </div>
                </div>
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
                </select>
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
    repoConfigs: Record<string, { feature_ids?: string[] }>;
    availableFeatures: FeatureCategoryGroup[] | null;
    featuresLoading: boolean;
    featuresError: string | null;
    templates: DatasetTemplateRecord[];
    searchTerms: Record<string, string>;
    onSearchChange: (fullName: string, value: string) => void;
    onUpdateFeatures: (fullName: string, featureIds: string[]) => void;
    onApplyTemplate: (fullName: string, featureIds: string[]) => void;
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
    const { nameToId, idToName, idLabels } = useMemo(() => {
        const n2i: Record<string, string> = {};
        const i2n: Record<string, string> = {};
        const labels: Record<string, string> = {};

        groupedFeatures.forEach((cat) => {
            cat.features.forEach((feat) => {
                n2i[feat.name] = feat.id;
                i2n[feat.id] = feat.name;
                labels[feat.id] = feat.display_name || feat.name;
            });
        });
        return { nameToId: n2i, idToName: i2n, idLabels: labels };
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
    const getActiveNodes = useCallback((selectedIds: string[]): Set<string> => {
        if (!dagData) return new Set();
        // Convert IDs to names for DAG comparison
        const selectedNames = new Set(
            selectedIds.map(id => idToName[id]).filter((n): n is string => !!n)
        );
        const active = new Set<string>();
        dagData.nodes.forEach((node) => {
            if (node.features.some((f) => selectedNames.has(f))) {
                active.add(node.id);
            }
        });
        return active;
    }, [dagData, idToName]);

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
                const current = repoConfigs[repo.full_name]?.feature_ids || [];
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
                                                                    <Badge variant="secondary" className="text-[10px]">{tpl.selected_features.length} feats</Badge>
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
                                                    const ids = tpl.selected_features
                                                        .map(name => nameToId[name])
                                                        .filter((id): id is string => !!id);
                                                    onApplyTemplate(repo.full_name, ids);
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
                                                    {tpl.tags.map((b) => (
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
                                    selectedFeatures={current.map(id => idToName[id]).filter((n): n is string => !!n)}
                                    onFeaturesChange={(names) => {
                                        const ids = names.map(n => nameToId[n]).filter((id): id is string => !!id);
                                        onUpdateFeatures(repo.full_name, ids);
                                    }}
                                    isLoading={dagLoading}
                                />

                                {/* Selected Features Panel */}
                                <SelectedFeaturesPanel
                                    selectedFeatures={current}
                                    featureLabels={idLabels}
                                    onRemove={(featureId) =>
                                        onUpdateFeatures(
                                            repo.full_name,
                                            current.filter((id) => id !== featureId)
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
                                                                    checked={current.includes(feat.id)}
                                                                    onChange={() => {
                                                                        const next = current.includes(feat.id)
                                                                            ? current.filter((id) => id !== feat.id)
                                                                            : [...current, feat.id];
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
