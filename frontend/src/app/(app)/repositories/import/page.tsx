"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
    ArrowLeft,
    ArrowRight,
    Building2,
    Globe,
    Loader2,
    Maximize2,
    Search,
    X,
} from "lucide-react";

import { FeatureDAGVisualization, type FeatureDAGData } from "@/components/features";
import { FeatureConfigForm, type FeatureConfigsData } from "@/components/features/config/FeatureConfigForm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { useDebounce } from "@/hooks/use-debounce";
import { featuresApi, reposApi, templatesApi } from "@/lib/api";
import {
    CIProvider,
    FeatureDefinitionSummary,
    RepoImportPayload,
    RepoSuggestion
} from "@/types";

// Hook to detect languages for repos
function useRepoLanguages(repos: Array<{ id: string; full_name: string }>) {
    const [repoLanguages, setRepoLanguages] = useState<Record<string, string[]>>({});
    const [loading, setLoading] = useState<Record<string, boolean>>({});

    useEffect(() => {
        if (repos.length === 0) return;

        const detectLanguagesForRepos = async () => {
            for (const repo of repos) {
                if (repoLanguages[repo.id] !== undefined || loading[repo.id]) {
                    continue;
                }

                setLoading(prev => ({ ...prev, [repo.id]: true }));
                try {
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

type FeatureCategoryGroup = {
    category: string;
    display_name: string;
    features: FeatureDefinitionSummary[];
};

export default function ImportRepositoriesPage() {
    const router = useRouter();
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

    // Features data
    const [featuresData, setFeaturesData] = useState<FeatureCategoryGroup[] | null>(null);
    const [featuresLoading, setFeaturesLoading] = useState(false);

    const [importing, setImporting] = useState(false);
    const [activeRepo, setActiveRepo] = useState<string | null>(null);

    // Templates state
    const [templatesLoading, setTemplatesLoading] = useState(false);


    // DAG state
    const [dagData, setDagData] = useState<FeatureDAGData | null>(null);
    const [dagLoading, setDagLoading] = useState(false);
    const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);

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

    const loadSelectedTemplate = useCallback(async () => {
        if (templatesLoading) return;
        if (selectedFeatures.length > 0) return;
        setTemplatesLoading(true);
        try {
            const template = await templatesApi.getByName("Risk Prediction");
            setSelectedFeatures(template.feature_names || []);
        } catch (err) {
            console.error("Failed to load selected template:", err);
        } finally {
            setTemplatesLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [templatesLoading]);

    useEffect(() => {
        if (debouncedSearchTerm === searchTerm) {
            performSearch(debouncedSearchTerm);
        }
    }, [debouncedSearchTerm, searchTerm, performSearch]);

    useEffect(() => {
        performSearch("", true);
    }, [performSearch]);

    const toggleSelection = (repo: RepoSuggestion) => {
        const repoId = String(repo.github_repo_id);
        setSelectedRepos((prev) => {
            const next = { ...prev };
            if (next[repoId]) {
                delete next[repoId];
                setBaseConfigs((current) => {
                    const updated = { ...current };
                    delete updated[repoId];
                    return updated;
                });
            } else {
                next[repoId] = repo;
                setBaseConfigs((current) => ({
                    ...current,
                    [repoId]: {
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
            // Using ID as key
            setActiveRepo(String(selectedList[0].github_repo_id));
        }
    }, [selectedList, activeRepo, selectedRepos]);

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

        try {
            const payloads: RepoImportPayload[] = selectedList.map((repo) => {
                const repoId = String(repo.github_repo_id);
                const baseConfig = baseConfigs[repoId];
                const dynamicRepoConfig = featureConfigs.repos[repoId] || {};

                return {
                    full_name: repo.full_name,
                    provider: "github",
                    ci_provider: baseConfig.ci_provider,
                    max_builds: baseConfig.max_builds ?? null,
                    since_days: baseConfig.since_days ?? null,
                    feature_configs: {
                        global: featureConfigs.global,
                        repos: {
                            [repoId]: dynamicRepoConfig,
                        },
                    },
                };
            });

            await reposApi.importBulk(payloads);
            router.push("/repositories?imported=true");
        } catch (err: unknown) {
            console.error(err);
        } finally {
            setImporting(false);
        }
    };

    const featureFormFeatures = useMemo(() => new Set(selectedFeatures), [selectedFeatures]);

    const featureFormRepos = useMemo(() => selectedList.map(r => ({
        id: String(r.github_repo_id),
        full_name: r.full_name,
        validation_status: "unknown"
    })), [selectedList]);

    // Build feature descriptions map for tooltips
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

    // Detect languages for selected repos
    const { repoLanguages } = useRepoLanguages(featureFormRepos);

    return (
        <div className="flex flex-col h-full min-h-0">
            {/* Header */}
            <div className="flex items-center justify-between border-b bg-background px-6 py-4">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="sm" onClick={() => router.push("/repositories")}>
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Repositories
                    </Button>
                    <div className="h-4 w-px bg-border" />
                    <div>
                        <h1 className="text-lg font-semibold">Import Repositories</h1>
                        <p className="text-sm text-muted-foreground">
                            Step {step} of 2: {step === 1 ? "Select repositories" : "Configure & Import"}
                        </p>
                    </div>
                </div>

                {/* Step Indicator */}
                <div className="hidden md:flex items-center gap-2">
                    <StepIndicator step={1} currentStep={step} label="Select" />
                    <div className="w-8 h-px bg-border" />
                    <StepIndicator step={2} currentStep={step} label="Configure" />
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-2">
                    {step > 1 && (
                        <Button variant="outline" onClick={() => setStep(1)}>
                            <ArrowLeft className="h-4 w-4 mr-1" />
                            Back
                        </Button>
                    )}
                    {step === 1 ? (
                        <Button onClick={() => setStep(2)} disabled={selectedList.length === 0}>
                            Next
                            <ArrowRight className="h-4 w-4 ml-1" />
                        </Button>
                    ) : (
                        <Button onClick={handleImport} disabled={importing || selectedList.length === 0}>
                            {importing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Import {selectedList.length} Repositories
                        </Button>
                    )}
                </div>
            </div>

            {/* Main Content - Split View */}
            <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_400px] min-h-0 overflow-hidden">
                {/* Left Panel */}
                <div className="overflow-y-auto p-6">
                    {step === 1 ? (
                        <Step1Content
                            searchTerm={searchTerm}
                            setSearchTerm={setSearchTerm}
                            isSearching={isSearching}
                            searchError={searchError}
                            privateMatches={privateMatches}
                            publicMatches={publicMatches}
                            selectedRepos={selectedRepos}
                            toggleSelection={toggleSelection}
                        />
                    ) : (
                        <Step2Content
                            selectedList={selectedList}
                            activeRepo={activeRepo}
                            setActiveRepo={setActiveRepo}
                            baseConfigs={baseConfigs}
                            setBaseConfigs={setBaseConfigs}
                            featureFormFeatures={featureFormFeatures}
                            featureFormRepos={featureFormRepos}
                            setFeatureConfigs={setFeatureConfigs}
                            repoLanguages={repoLanguages}
                        />
                    )}
                </div>

                {/* Right Panel - Preview */}
                <div className="hidden lg:flex flex-col border-l bg-slate-50 dark:bg-slate-900/30 overflow-y-auto">
                    <div className="p-4 border-b bg-background">
                        <h3 className="font-semibold text-sm">
                            {step === 1 ? "Selected Repositories" : "Feature Extraction Plan"}
                        </h3>
                    </div>
                    <div className="flex-1 p-4 space-y-4 overflow-y-auto">
                        {step === 1 ? (
                            <SelectedReposPreview
                                selectedList={selectedList}
                                onRemove={(repo) => toggleSelection(repo)}
                            />
                        ) : (
                            <ExtractionPreview
                                dagData={dagData}
                                dagLoading={dagLoading || templatesLoading}
                                selectedFeatures={selectedFeatures}
                                featureDescriptions={featureDescriptions}
                            />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// Step Indicator Component
function StepIndicator({ step, currentStep, label }: { step: number; currentStep: number; label: string }) {
    const isActive = step === currentStep;
    const isComplete = step < currentStep;

    return (
        <div className="flex items-center gap-2">
            <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${isActive
                    ? "bg-primary text-primary-foreground"
                    : isComplete
                        ? "bg-green-500 text-white"
                        : "bg-muted text-muted-foreground"
                    }`}
            >
                {isComplete ? "✓" : step}
            </div>
            <span className={`text-sm ${isActive ? "font-medium" : "text-muted-foreground"}`}>
                {label}
            </span>
        </div>
    );
}

// Step 1 Content
interface Step1Props {
    searchTerm: string;
    setSearchTerm: (val: string) => void;
    isSearching: boolean;
    searchError: string | null;
    privateMatches: RepoSuggestion[];
    publicMatches: RepoSuggestion[];
    selectedRepos: Record<string, RepoSuggestion>;
    toggleSelection: (repo: RepoSuggestion) => void;
}

function Step1Content({
    searchTerm,
    setSearchTerm,
    isSearching,
    searchError,
    privateMatches,
    publicMatches,
    selectedRepos,
    toggleSelection,
}: Step1Props) {
    return (
        <div className="space-y-6 max-w-3xl">
            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                    type="text"
                    className="w-full rounded-lg border bg-background pl-10 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="Search repositories (e.g. owner/repo)..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>

            {searchError && (
                <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                    {searchError}
                </div>
            )}

            {/* Organization Repos */}
            <div>
                <h3 className="mb-3 text-sm font-semibold text-muted-foreground flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    Organization Repositories
                </h3>
                <div className="space-y-2">
                    {privateMatches.length === 0 && !isSearching ? (
                        <div className="text-sm text-muted-foreground italic py-3 px-4 rounded-lg bg-muted/30">
                            No matching organization repositories found.
                        </div>
                    ) : (
                        privateMatches.map((repo) => (
                            <RepoItem
                                key={repo.github_repo_id}
                                repo={repo}
                                isSelected={!!selectedRepos[String(repo.github_repo_id)]}
                                onToggle={() => toggleSelection(repo)}
                            />
                        ))
                    )}
                </div>
            </div>

            {/* Public Repos */}
            <div>
                <h3 className="mb-3 text-sm font-semibold text-muted-foreground flex items-center gap-2">
                    <Globe className="h-4 w-4" />
                    Public GitHub Repositories
                </h3>
                <div className="space-y-2">
                    {publicMatches.length === 0 && !isSearching ? (
                        <div className="text-sm text-muted-foreground italic py-3 px-4 rounded-lg bg-muted/30">
                            {searchTerm.length >= 3
                                ? "No matching public repositories found."
                                : "Type at least 3 characters to search."}
                        </div>
                    ) : (
                        publicMatches.map((repo) => (
                            <RepoItem
                                key={repo.github_repo_id}
                                repo={repo}
                                isSelected={!!selectedRepos[String(repo.github_repo_id)]}
                                onToggle={() => toggleSelection(repo)}
                            />
                        ))
                    )}
                </div>
            </div>

            {isSearching && (
                <div className="flex justify-center py-6">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            )}
        </div>
    );
}

// Step 2 Content
interface Step2Props {
    selectedList: RepoSuggestion[];
    activeRepo: string | null;
    setActiveRepo: (repo: string) => void;
    baseConfigs: Record<string, { ci_provider: string; max_builds?: number | null; since_days?: number | null }>;
    setBaseConfigs: React.Dispatch<React.SetStateAction<Record<string, { ci_provider: string; max_builds?: number | null; since_days?: number | null }>>>;
    featureFormFeatures: Set<string>;
    featureFormRepos: { id: string; full_name: string; validation_status: string }[];
    setFeatureConfigs: React.Dispatch<React.SetStateAction<FeatureConfigsData>>;
    repoLanguages: Record<string, string[]>;
}

function Step2Content({
    selectedList,
    activeRepo,
    setActiveRepo,
    baseConfigs,
    setBaseConfigs,
    featureFormFeatures,
    featureFormRepos,
    setFeatureConfigs,
    repoLanguages,
}: Step2Props) {
    return (
        <div className="space-y-6 max-w-3xl">
            {/* Repo Tabs */}
            <div className="flex gap-2 overflow-x-auto pb-2">
                {selectedList.map((repo) => (
                    <button
                        key={repo.github_repo_id}
                        className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${activeRepo === String(repo.github_repo_id)
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted hover:bg-muted/80"
                            }`}
                        onClick={() => setActiveRepo(String(repo.github_repo_id))}
                    >
                        {repo.full_name.split("/")[1]}
                    </button>
                ))}
            </div>

            {activeRepo && (
                <div className="space-y-6">
                    {/* Base Config */}
                    <Card>
                        <CardHeader className="pb-4">
                            <CardTitle className="text-base">Import Settings</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid gap-4 sm:grid-cols-3">
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
                        </CardContent>
                    </Card>

                    {/* Feature Config */}
                    <FeatureConfigForm
                        selectedFeatures={featureFormFeatures}
                        repos={featureFormRepos}
                        repoLanguages={repoLanguages}
                        onChange={setFeatureConfigs}
                        showValidationStatusColumn={false}
                    />
                </div>
            )}
        </div>
    );
}

// Repo Item Component
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
        <label
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors ${isSelected
                ? "bg-primary/5 border-primary/30 dark:bg-primary/10"
                : "hover:bg-muted/50"
                }`}
        >
            <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                checked={isSelected}
                onChange={onToggle}
            />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{repo.full_name}</span>
                    {repo.private && (
                        <Badge variant="secondary" className="text-[10px] h-5">Private</Badge>
                    )}
                </div>
                <p className="text-xs text-muted-foreground line-clamp-1 mt-1">
                    {repo.description || "No description provided"}
                </p>
            </div>
        </label>
    );
}

// Selected Repos Preview
function SelectedReposPreview({
    selectedList,
    onRemove,
}: {
    selectedList: RepoSuggestion[];
    onRemove: (repo: RepoSuggestion) => void;
}) {
    if (selectedList.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3">
                    <Search className="h-5 w-5 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">
                    Select repositories from the list
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {selectedList.map((repo) => (
                <div
                    key={repo.github_repo_id}
                    className="flex items-center justify-between gap-2 rounded-lg border bg-background p-3"
                >
                    <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{repo.full_name}</p>
                        <p className="text-xs text-muted-foreground truncate">
                            {repo.description || "No description"}
                        </p>
                    </div>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => onRemove(repo)}
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            ))}
        </div>
    );
}

// Extraction Preview
function ExtractionPreview({
    dagData,
    dagLoading,
    selectedFeatures,
    featureDescriptions,
}: {
    dagData: FeatureDAGData | null;
    dagLoading: boolean;
    selectedFeatures: string[];
    featureDescriptions: Record<string, string>;
}) {
    // Feature list state
    const [expandedFeatures, setExpandedFeatures] = useState(false);
    // DAG modal state
    const [isDagOpen, setIsDagOpen] = useState(false);

    const DISPLAY_LIMIT = 20;

    const visibleFeatures = expandedFeatures
        ? selectedFeatures
        : selectedFeatures.slice(0, DISPLAY_LIMIT);

    const hasMore = selectedFeatures.length > DISPLAY_LIMIT;

    if (dagLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!dagData || selectedFeatures.length === 0) {
        return (
            <div className="text-sm text-muted-foreground text-center py-12">
                No features selected for extraction
            </div>
        );
    }



    return (
        <div className="space-y-4">
            {/* DAG Visualization */}
            <div className="rounded-lg border bg-background overflow-hidden relative group">
                <FeatureDAGVisualization
                    dagData={dagData}
                    selectedFeatures={selectedFeatures}
                    onFeaturesChange={() => { }}
                    className="h-[350px]"
                />

                {/* Maximize Button Overlay */}
                <Dialog open={isDagOpen} onOpenChange={setIsDagOpen}>
                    <DialogTrigger asChild>
                        <Button
                            variant="secondary"
                            size="icon"
                            className="absolute top-2 right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity bg-white/80 hover:bg-white border shadow-sm"
                            title="Maximize Graph"
                        >
                            <Maximize2 className="h-4 w-4" />
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="max-w-[90vw] h-[90vh] flex flex-col p-0 gap-0">
                        <DialogHeader className="px-6 py-4 border-b flex flex-row items-center justify-between space-y-0">
                            <DialogTitle>Feature Extraction Dependency Graph</DialogTitle>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setIsDagOpen(false)}
                                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </DialogHeader>
                        <div className="flex-1 bg-slate-50 p-4 overflow-hidden">
                            <FeatureDAGVisualization
                                dagData={dagData}
                                selectedFeatures={selectedFeatures}
                                onFeaturesChange={() => { }}
                                className="h-full w-full"
                            />
                        </div>
                    </DialogContent>
                </Dialog>
            </div>

            {/* Selected Features */}
            <div className="rounded-lg border bg-background p-3">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold">Selected Features</span>
                    <Badge variant="secondary" className="text-xs">{selectedFeatures.length}</Badge>
                </div>
                <TooltipProvider delayDuration={200}>
                    <div className="flex flex-wrap gap-1 max-h-[300px] overflow-y-auto">
                        {visibleFeatures.map(feat => (
                            <Tooltip key={feat}>
                                <TooltipTrigger>
                                    <Badge
                                        variant="outline"
                                        className="text-[10px] cursor-help hover:bg-muted"
                                    >
                                        {feat}
                                    </Badge>
                                </TooltipTrigger>
                                <TooltipContent>
                                    <p className="font-semibold">{feat}</p>
                                    <p className="text-xs text-muted-foreground">{featureDescriptions[feat] || "No description available"}</p>
                                </TooltipContent>
                            </Tooltip>
                        ))}

                        {hasMore && !expandedFeatures && (
                            <Badge
                                variant="secondary"
                                className="text-[10px] cursor-pointer hover:bg-secondary/80"
                                onClick={() => setExpandedFeatures(true)}
                            >
                                +{selectedFeatures.length - DISPLAY_LIMIT} more
                            </Badge>
                        )}

                        {expandedFeatures && hasMore && (
                            <Badge
                                variant="secondary"
                                className="text-[10px] cursor-pointer hover:bg-secondary/80"
                                onClick={() => setExpandedFeatures(false)}
                            >
                                Show less
                            </Badge>
                        )}
                    </div>
                </TooltipProvider>
            </div>
        </div>
    );
}
