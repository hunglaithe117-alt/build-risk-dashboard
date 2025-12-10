"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import Papa from "papaparse";
import { CIProvider, type DatasetRecord, type DatasetTemplateRecord } from "@/types";
import { datasetsApi, featuresApi, reposApi } from "@/lib/api";
import type { CSVPreview, MappingKey, RepoConfig, FeatureCategoryGroup, Step, FeatureDAGData } from "../types";

interface UseUploadDatasetFormProps {
    open: boolean;
    existingDataset?: DatasetRecord;
    onSuccess: (dataset: DatasetRecord) => void;
    onOpenChange: (open: boolean) => void;
}

export function useUploadDatasetForm({
    open,
    existingDataset,
    onSuccess,
    onOpenChange,
}: UseUploadDatasetFormProps) {
    const [step, setStep] = useState<Step>(1);
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<CSVPreview | null>(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isResuming, setIsResuming] = useState(false);
    const [minStep, setMinStep] = useState<Step>(1);

    // Step 1: Configuration state
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [mappings, setMappings] = useState<Record<MappingKey, string>>({
        build_id: "",
        repo_name: "",
    });

    // Step 2: Repo configuration state
    const [uniqueRepos, setUniqueRepos] = useState<string[]>([]);
    const [invalidFormatRepos, setInvalidFormatRepos] = useState<string[]>([]);
    const [repoConfigs, setRepoConfigs] = useState<Record<string, RepoConfig>>({});
    const [availableLanguages, setAvailableLanguages] = useState<Record<string, string[]>>({});
    const [languageLoading, setLanguageLoading] = useState<Record<string, boolean>>({});
    const [activeRepo, setActiveRepo] = useState<string | null>(null);
    const [frameworks, setFrameworks] = useState<string[]>([]);
    const [frameworksByLang, setFrameworksByLang] = useState<Record<string, string[]>>({});
    const [supportedLanguages, setSupportedLanguages] = useState<string[]>([]);
    const [transitionLoading, setTransitionLoading] = useState(false);

    // Step 3: Data sources state
    const [enabledSources, setEnabledSources] = useState<Set<string>>(
        new Set(["git", "build_log", "github_api"]) // Core sources enabled by default
    );

    // Step 4: Feature selection state
    const [features, setFeatures] = useState<FeatureCategoryGroup[]>([]);
    const [templates, setTemplates] = useState<DatasetTemplateRecord[]>([]);
    const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set());
    const [featureSearch, setFeatureSearch] = useState("");
    const [featuresLoading, setFeaturesLoading] = useState(false);
    const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

    // DAG state
    const [dagData, setDagData] = useState<FeatureDAGData | null>(null);
    const [dagLoading, setDagLoading] = useState(false);

    // Created dataset
    const [createdDataset, setCreatedDataset] = useState<DatasetRecord | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);

    const resetState = useCallback(() => {
        setStep(1);
        setFile(null);
        setPreview(null);
        setUploading(false);
        setError(null);
        setName("");
        setDescription("");
        setMappings({ build_id: "", repo_name: "" });
        setUniqueRepos([]);
        setRepoConfigs({});
        setAvailableLanguages({});
        setLanguageLoading({});
        setActiveRepo(null);
        setEnabledSources(new Set(["git", "build_log", "github_api"]));
        setSelectedFeatures(new Set());
        setFeatureSearch("");
        setCollapsedCategories(new Set());
        setDagData(null);
        setDagLoading(false);
        setCreatedDataset(null);
        setTransitionLoading(false);
        setIsResuming(false);
        setMinStep(1);
    }, []);

    // Load existing dataset when modal opens in resume mode
    useEffect(() => {
        if (!open || !existingDataset) {
            if (!open) resetState();
            return;
        }

        // Resume mode - load existing dataset data
        setIsResuming(true);
        setCreatedDataset(existingDataset);
        setName(existingDataset.name || "");
        setDescription(existingDataset.description || "");

        // Load mappings
        if (existingDataset.mapped_fields) {
            setMappings({
                build_id: existingDataset.mapped_fields.build_id || "",
                repo_name: existingDataset.mapped_fields.repo_name || "",
            });
        }

        // Load preview from existing columns
        if (existingDataset.columns?.length > 0) {
            const previewRows = (existingDataset.preview || []).map(row => {
                const converted: Record<string, string> = {};
                Object.entries(row).forEach(([key, value]) => {
                    converted[key] = String(value ?? "");
                });
                return converted;
            });
            setPreview({
                columns: existingDataset.columns,
                rows: previewRows,
                totalRows: existingDataset.rows || 0,
                fileName: existingDataset.file_name || "dataset.csv",
                fileSize: existingDataset.size_bytes || 0,
            });
        }

        // Load selected features
        if (existingDataset.selected_features?.length > 0) {
            setSelectedFeatures(new Set(existingDataset.selected_features));
        }

        // Determine which step to start from
        const hasMappings = existingDataset.mapped_fields?.build_id && existingDataset.mapped_fields?.repo_name;
        const hasFeatures = (existingDataset.selected_features?.length || 0) > 0;

        if (!hasMappings) {
            setStep(1);
            setMinStep(1);
        } else if (!hasFeatures) {
            if (existingDataset.preview?.length > 0 && existingDataset.mapped_fields?.repo_name) {
                const repoCol = existingDataset.mapped_fields.repo_name;
                const repos = [...new Set(
                    existingDataset.preview
                        .map(row => String(row[repoCol] ?? ""))
                        .filter(Boolean)
                )];
                setUniqueRepos(repos);
                if (repos.length > 0) setActiveRepo(repos[0]);
            }
            setStep(2);
            setMinStep(2);
        } else {
            setStep(3);
            setMinStep(3);
        }
    }, [open, existingDataset, resetState]);

    const parseCSVPreview = useCallback(async (file: File): Promise<CSVPreview> => {
        return new Promise((resolve, reject) => {
            const previewSlice = file.slice(0, 100000);
            const reader = new FileReader();

            reader.onload = (e) => {
                const csvText = e.target?.result as string;

                Papa.parse(csvText, {
                    header: true,
                    skipEmptyLines: true,
                    preview: 5,
                    complete: (results) => {
                        if (results.errors.length > 0 && results.data.length === 0) {
                            reject(new Error(results.errors[0].message));
                            return;
                        }

                        const columns = results.meta.fields || [];
                        const rows = results.data as Record<string, string>[];

                        const avgRowSize = csvText.length / Math.max(rows.length + 1, 1);
                        const estimatedTotalRows = Math.floor(file.size / avgRowSize) - 1;

                        resolve({
                            columns,
                            rows,
                            totalRows: estimatedTotalRows > 0 ? estimatedTotalRows : rows.length,
                            fileName: file.name,
                            fileSize: file.size,
                        });
                    },
                    error: (error: Error) => {
                        reject(new Error(error.message));
                    },
                });
            };

            reader.onerror = () => reject(new Error("Failed to read file"));
            reader.readAsText(previewSlice);
        });
    }, []);


    const guessMapping = useCallback((columns: string[]) => {
        const lowered = columns.map(c => c.toLowerCase());

        const findMatch = (options: string[]): string => {
            for (const opt of options) {
                const idx = lowered.findIndex(c => c.includes(opt) || c === opt);
                if (idx !== -1) return columns[idx];
            }
            return "";
        };

        return {
            build_id: findMatch(["build_id", "build id", "id", "workflow_run_id", "run_id", "tr_build_id"]),
            repo_name: findMatch(["repo", "repository", "repo_name", "full_name", "project", "gh_project_name"]),
        };
    }, []);

    const handleFileSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = event.target.files?.[0];
        if (!selectedFile) return;

        setError(null);
        setUploading(true);

        try {
            const csvPreview = await parseCSVPreview(selectedFile);
            setFile(selectedFile);
            setPreview(csvPreview);
            setName(selectedFile.name.replace(/\.csv$/i, ""));

            const guessed = guessMapping(csvPreview.columns);
            setMappings(guessed);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to parse CSV");
        } finally {
            setUploading(false);
            if (event.target) event.target.value = "";
        }
    }, [parseCSVPreview, guessMapping]);

    // Extract unique repos from preview when mapping changes
    // Returns { valid: repos with owner/name format, invalid: repos with bad format }
    const extractUniqueRepos = useCallback((): { valid: string[], invalid: string[] } => {
        if (!preview || !mappings.repo_name) return { valid: [], invalid: [] };

        const validRepos = new Set<string>();
        const invalidRepos = new Set<string>();

        preview.rows.forEach(row => {
            const repoName = row[mappings.repo_name]?.trim();
            if (!repoName) return;

            // Check format: must be owner/repo
            if (repoName.includes("/") && repoName.split("/").length === 2) {
                const [owner, name] = repoName.split("/");
                if (owner && name) {
                    validRepos.add(repoName);
                } else {
                    invalidRepos.add(repoName);
                }
            } else {
                invalidRepos.add(repoName);
            }
        });
        return { valid: Array.from(validRepos), invalid: Array.from(invalidRepos) };
    }, [preview, mappings.repo_name]);

    // Load frameworks and languages on mount
    useEffect(() => {
        if (!open) return;

        featuresApi.getSupportedLanguages().then((data) => {
            setSupportedLanguages(data.languages);
        }).catch(console.error);

        reposApi.getTestFrameworks().then((res) => {
            setFrameworks(res.frameworks || []);
            setFrameworksByLang(res.by_language || {});
        }).catch(console.error);
    }, [open]);

    // Initialize repo configs when entering step 2
    useEffect(() => {
        if (step !== 2 || uniqueRepos.length === 0) return;

        // Only run once when entering step 2
        const configs: Record<string, RepoConfig> = {};
        uniqueRepos.forEach(repo => {
            if (!repoConfigs[repo]) {
                configs[repo] = {
                    source_languages: [],
                    test_frameworks: [],
                    ci_provider: CIProvider.GITHUB_ACTIONS,
                };
            } else {
                configs[repo] = repoConfigs[repo];
            }
        });
        setRepoConfigs(configs);
        if (!activeRepo && uniqueRepos.length > 0) {
            setActiveRepo(uniqueRepos[0]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, uniqueRepos.length]);

    // Fetch languages when resuming an existing dataset
    useEffect(() => {
        if (step !== 2 || !isResuming || supportedLanguages.length === 0) return;
        if (uniqueRepos.length === 0) return;

        // Check if we need to fetch any languages
        const reposNeedingFetch = uniqueRepos.filter(repo =>
            !availableLanguages[repo] && !languageLoading[repo]
        );

        if (reposNeedingFetch.length === 0) return;

        setTransitionLoading(true);
        Promise.all(reposNeedingFetch.map(repo => {
            setLanguageLoading(prev => ({ ...prev, [repo]: true }));
            return reposApi.detectLanguages(repo).then(res => {
                const detected = res.languages || [];
                const validLangs = detected.filter(l =>
                    supportedLanguages.some(sl => sl.toLowerCase() === l.toLowerCase())
                );
                setAvailableLanguages(prev => ({ ...prev, [repo]: validLangs }));
                setLanguageLoading(prev => ({ ...prev, [repo]: false }));
            }).catch(err => {
                console.error(`Failed to detect languages for ${repo}:`, err);
                setAvailableLanguages(prev => ({ ...prev, [repo]: [] }));
                setLanguageLoading(prev => ({ ...prev, [repo]: false }));
            });
        })).finally(() => {
            setTransitionLoading(false);
        });
        // Only run when entering step 2 with resuming flag
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, isResuming, supportedLanguages.length, uniqueRepos.length]);

    // Load features and templates when entering step 3
    useEffect(() => {
        if (step === 3 && features.length === 0) {
            setFeaturesLoading(true);
            Promise.all([
                featuresApi.list({ is_active: true }),
                datasetsApi.listTemplates(),
            ])
                .then(([featResult, templatesResult]) => {
                    const grouped: Record<string, FeatureCategoryGroup> = {};
                    featResult.items.forEach((feat) => {
                        const key = feat.category || "uncategorized";
                        if (!grouped[key]) {
                            grouped[key] = { category: key, features: [] };
                        }
                        grouped[key].features.push(feat);
                    });
                    setFeatures(Object.values(grouped).sort((a, b) => a.category.localeCompare(b.category)));
                    setTemplates(templatesResult.items || []);
                })
                .catch(console.error)
                .finally(() => setFeaturesLoading(false));
        }
    }, [step, features.length]);

    const handleMappingChange = (field: MappingKey, value: string) => {
        setMappings(prev => ({ ...prev, [field]: value }));
    };

    const isMappingValid = Boolean(mappings.build_id && mappings.repo_name);

    // Fetch languages for a single repo
    const fetchLanguagesForRepo = useCallback(
        async (repoName: string) => {
            setLanguageLoading(prev => ({ ...prev, [repoName]: true }));
            try {
                const res = await reposApi.detectLanguages(repoName);
                const detected = res.languages || [];

                const validLangs = supportedLanguages.length > 0
                    ? detected.filter(l => supportedLanguages.some(sl => sl.toLowerCase() === l.toLowerCase()))
                    : detected;

                setAvailableLanguages(prev => ({ ...prev, [repoName]: validLangs }));

                setRepoConfigs(current => {
                    const existing = current[repoName];
                    return {
                        ...current,
                        [repoName]: {
                            test_frameworks: existing?.test_frameworks || [],
                            source_languages: existing?.source_languages || [],
                            ci_provider: existing?.ci_provider || CIProvider.GITHUB_ACTIONS,
                        },
                    };
                });
            } catch (err) {
                console.error(`Failed to detect languages for ${repoName}:`, err);
                setAvailableLanguages(prev => ({ ...prev, [repoName]: [] }));
            } finally {
                setLanguageLoading(prev => ({ ...prev, [repoName]: false }));
            }
        },
        [supportedLanguages]
    );

    // Step 1 -> Step 2
    const handleProceedToStep2 = async () => {
        if (!file || !isMappingValid) return;

        setUploading(true);
        setError(null);

        try {
            const dataset = await datasetsApi.upload(file, {
                name: name || file.name.replace(/\.csv$/i, ""),
                description: description || undefined,
            });

            await datasetsApi.update(dataset.id, {
                mapped_fields: {
                    build_id: mappings.build_id || null,
                    repo_name: mappings.repo_name || null,
                    commit_sha: null,
                },
            });

            setCreatedDataset(dataset);

            const { valid: validRepos, invalid: invalidRepos } = extractUniqueRepos();
            setUniqueRepos(validRepos);
            setInvalidFormatRepos(invalidRepos);

            setStep(2);
            setTransitionLoading(true);

            await Promise.all(validRepos.map((repo: string) => fetchLanguagesForRepo(repo)));

            if (validRepos.length > 0) {
                setActiveRepo(validRepos[0]);
            }
        } catch (err) {
            console.error("Upload failed:", err);
            setError(err instanceof Error ? err.message : "Failed to upload dataset");
        } finally {
            setUploading(false);
            setTransitionLoading(false);
        }
    };

    // Toggle language for a repo
    const toggleLanguage = (repo: string, lang: string) => {
        setRepoConfigs(prev => {
            const config = prev[repo] || { source_languages: [], test_frameworks: [], ci_provider: CIProvider.GITHUB_ACTIONS };
            const languages = config.source_languages.includes(lang)
                ? config.source_languages.filter(l => l !== lang)
                : [...config.source_languages, lang];
            return { ...prev, [repo]: { ...config, source_languages: languages } };
        });
    };

    // Toggle framework for a repo
    const toggleFramework = (repo: string, fw: string) => {
        setRepoConfigs(prev => {
            const config = prev[repo] || { source_languages: [], test_frameworks: [], ci_provider: CIProvider.GITHUB_ACTIONS };
            const frameworks = config.test_frameworks.includes(fw)
                ? config.test_frameworks.filter(f => f !== fw)
                : [...config.test_frameworks, fw];
            return { ...prev, [repo]: { ...config, test_frameworks: frameworks } };
        });
    };

    // Set CI provider for a repo
    const setCiProvider = (repo: string, provider: CIProvider) => {
        setRepoConfigs(prev => {
            const config = prev[repo] || { source_languages: [], test_frameworks: [], ci_provider: CIProvider.GITHUB_ACTIONS };
            return { ...prev, [repo]: { ...config, ci_provider: provider } };
        });
    };

    // Get suggested frameworks based on selected languages
    const getSuggestedFrameworks = (config: RepoConfig) => {
        const langs = config.source_languages.map(l => l.toLowerCase());
        const suggested = new Set<string>();
        langs.forEach(lang => {
            const fws = frameworksByLang[lang] || [];
            fws.forEach(fw => suggested.add(fw));
        });
        return Array.from(suggested);
    };

    const toggleFeature = (featureName: string) => {
        setSelectedFeatures(prev => {
            const next = new Set(prev);
            if (next.has(featureName)) {
                next.delete(featureName);
            } else {
                next.add(featureName);
            }
            return next;
        });
    };

    const applyTemplate = (template: DatasetTemplateRecord) => {
        setSelectedFeatures(new Set(template.feature_names));
    };

    const toggleCategory = (category: string) => {
        setCollapsedCategories(prev => {
            const next = new Set(prev);
            if (next.has(category)) {
                next.delete(category);
            } else {
                next.add(category);
            }
            return next;
        });
    };

    // Toggle data source on/off
    const toggleSource = (sourceType: string) => {
        setEnabledSources(prev => {
            const next = new Set(prev);
            if (next.has(sourceType)) {
                next.delete(sourceType);
            } else {
                next.add(sourceType);
            }
            return next;
        });
    };

    // Load DAG data
    const loadDAG = useCallback(async () => {
        if (dagData || dagLoading) return;
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

    // Set selected features from DAG (array to Set)
    const setSelectedFeaturesFromDAG = useCallback((features: string[]) => {
        setSelectedFeatures(new Set(features));
    }, []);

    // Final submission
    const handleSubmit = async () => {
        if (!createdDataset) return;

        setUploading(true);
        setError(null);

        try {
            const firstRepoConfig = uniqueRepos.length > 0 ? repoConfigs[uniqueRepos[0]] : null;

            const updated = await datasetsApi.update(createdDataset.id, {
                selected_features: Array.from(selectedFeatures),
                ci_provider: firstRepoConfig?.ci_provider || CIProvider.GITHUB_ACTIONS,
            });

            onSuccess(updated);
            onOpenChange(false);
            resetState();
        } catch (err) {
            console.error("Failed to save:", err);
            setError(err instanceof Error ? err.message : "Failed to save dataset");
        } finally {
            setUploading(false);
        }
    };

    const handleClearFile = () => {
        setFile(null);
        setPreview(null);
    };

    // Map enabledSources (data source types) to feature source values
    // enabledSources: git, build_log, github_api, sonarqube, trivy
    // feature.source: git_repo, build_log, github_api, sonarqube, trivy, workflow_run, metadata, computed
    const SOURCE_TYPE_TO_FEATURE_SOURCE: Record<string, string[]> = {
        git: ["git_repo"],
        build_log: ["build_log"],
        github_api: ["github_api", "workflow_run"],
        sonarqube: ["sonarqube"],
        trivy: ["trivy"],
        // metadata and computed features are always included
    };

    // Filter features based on enabledSources
    const filteredFeatures = useMemo(() => {
        // Get all allowed feature sources based on enabledSources
        const allowedFeatureSources = new Set<string>();

        // Always include metadata and computed sources
        allowedFeatureSources.add("metadata");
        allowedFeatureSources.add("computed");

        // Add sources based on enabled data sources
        for (const source of enabledSources) {
            const featureSources = SOURCE_TYPE_TO_FEATURE_SOURCE[source];
            if (featureSources) {
                featureSources.forEach(s => allowedFeatureSources.add(s));
            }
        }

        // Filter features by source
        return features
            .map(group => ({
                ...group,
                features: group.features.filter(f =>
                    allowedFeatureSources.has(f.source || "")
                ),
            }))
            .filter(group => group.features.length > 0);
    }, [features, enabledSources]);

    // Filter DAG data based on enabledSources (removes nodes from disabled sources)
    const filteredDagData = useMemo((): FeatureDAGData | null => {
        if (!dagData) return null;

        // Map enabledSources to resource names used in DAG
        // Backend resources: git_repo, github_client, log_storage, sonar_client, trivy_client
        const SOURCE_TO_RESOURCE: Record<string, string[]> = {
            git: ["git_repo"],
            build_log: ["log_storage"],
            github_api: ["github_client"],
            sonarqube: ["sonar_client"],
            trivy: ["trivy_client"],
        };

        // Get allowed resources
        const allowedResources = new Set<string>();
        for (const source of enabledSources) {
            const resources = SOURCE_TO_RESOURCE[source];
            if (resources) {
                resources.forEach(r => allowedResources.add(r));
            }
        }

        // Filter nodes: keep resource nodes if allowed, keep extractor nodes if their required resources are all allowed
        const filteredNodes = dagData.nodes.filter(node => {
            if (node.type === "resource") {
                return allowedResources.has(node.id);
            }
            // Extractor nodes: check if all required resources are enabled
            const requiredResources = node.requires_resources || [];
            return requiredResources.every(r => allowedResources.has(r));
        });

        const filteredNodeIds = new Set(filteredNodes.map(n => n.id));

        // Filter edges: keep only edges where both source and target exist
        const filteredEdges = dagData.edges.filter(edge =>
            filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target)
        );

        // Recalculate execution levels
        const filteredExecutionLevels = dagData.execution_levels
            .map(level => ({
                ...level,
                nodes: level.nodes.filter(n => filteredNodeIds.has(n)),
            }))
            .filter(level => level.nodes.length > 0);

        return {
            nodes: filteredNodes,
            edges: filteredEdges,
            execution_levels: filteredExecutionLevels,
            total_features: filteredNodes.reduce((sum, n) => sum + (n.feature_count || 0), 0),
            total_nodes: filteredNodes.filter(n => n.type === "extractor").length,
        };
    }, [dagData, enabledSources]);

    return {
        // State
        step,
        file,
        preview,
        uploading,
        error,
        name,
        description,
        mappings,
        isMappingValid,
        uniqueRepos,
        invalidFormatRepos,
        repoConfigs,
        availableLanguages,
        languageLoading,
        activeRepo,
        transitionLoading,
        frameworksByLang,
        features: filteredFeatures,
        templates,
        selectedFeatures,
        featureSearch,
        featuresLoading,
        collapsedCategories,
        dagData: filteredDagData,
        dagLoading,
        minStep,
        fileInputRef,
        enabledSources,

        // Setters
        setStep,
        setName,
        setDescription,
        setActiveRepo,
        setFeatureSearch,

        // Handlers
        resetState,
        handleFileSelect,
        handleMappingChange,
        handleProceedToStep2,
        handleSubmit,
        handleClearFile,
        toggleLanguage,
        toggleFramework,
        setCiProvider,
        getSuggestedFrameworks,
        toggleFeature,
        applyTemplate,
        toggleCategory,
        loadDAG,
        setSelectedFeaturesFromDAG,
        toggleSource,
    };
}
