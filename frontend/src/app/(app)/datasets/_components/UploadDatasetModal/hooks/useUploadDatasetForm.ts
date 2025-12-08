"use client";

import { useState, useRef, useCallback, useEffect } from "react";
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
    const [repoConfigs, setRepoConfigs] = useState<Record<string, RepoConfig>>({});
    const [availableLanguages, setAvailableLanguages] = useState<Record<string, string[]>>({});
    const [languageLoading, setLanguageLoading] = useState<Record<string, boolean>>({});
    const [activeRepo, setActiveRepo] = useState<string | null>(null);
    const [frameworks, setFrameworks] = useState<string[]>([]);
    const [frameworksByLang, setFrameworksByLang] = useState<Record<string, string[]>>({});
    const [supportedLanguages, setSupportedLanguages] = useState<string[]>([]);
    const [transitionLoading, setTransitionLoading] = useState(false);

    // Step 3: Feature selection state
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
                fileSize: (existingDataset.size_mb || 0) * 1024 * 1024,
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
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const text = e.target?.result as string;
                    const lines = text.split("\n").filter(line => line.trim());

                    if (lines.length === 0) {
                        reject(new Error("CSV file is empty"));
                        return;
                    }

                    const header = lines[0].split(",").map(col => col.trim().replace(/^"|"$/g, ""));

                    const previewRows: Record<string, string>[] = [];
                    for (let i = 1; i < Math.min(6, lines.length); i++) {
                        const values = lines[i].split(",").map(v => v.trim().replace(/^"|"$/g, ""));
                        const row: Record<string, string> = {};
                        header.forEach((col, idx) => {
                            row[col] = values[idx] || "";
                        });
                        previewRows.push(row);
                    }

                    resolve({
                        columns: header,
                        rows: previewRows,
                        totalRows: lines.length - 1,
                        fileName: file.name,
                        fileSize: file.size,
                    });
                } catch (err) {
                    reject(err);
                }
            };
            reader.onerror = () => reject(new Error("Failed to read file"));
            reader.readAsText(file.slice(0, 100000));
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
    const extractUniqueRepos = useCallback(() => {
        if (!preview || !mappings.repo_name) return [];

        const repos = new Set<string>();
        preview.rows.forEach(row => {
            const repoName = row[mappings.repo_name]?.trim();
            if (repoName && repoName.includes("/")) {
                repos.add(repoName);
            }
        });
        return Array.from(repos);
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
        if (step === 2 && uniqueRepos.length > 0) {
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

            if (isResuming && supportedLanguages.length > 0) {
                const needsFetch = uniqueRepos.some(repo => !availableLanguages[repo] && !languageLoading[repo]);
                if (needsFetch) {
                    setTransitionLoading(true);
                    Promise.all(uniqueRepos.map(repo => {
                        if (!availableLanguages[repo] && !languageLoading[repo]) {
                            return reposApi.detectLanguages(repo).then(res => {
                                const detected = res.languages || [];
                                const validLangs = detected.filter(l =>
                                    supportedLanguages.some(sl => sl.toLowerCase() === l.toLowerCase())
                                );
                                setAvailableLanguages(prev => ({ ...prev, [repo]: validLangs }));
                            }).catch(err => {
                                console.error(`Failed to detect languages for ${repo}:`, err);
                                setAvailableLanguages(prev => ({ ...prev, [repo]: [] }));
                            });
                        }
                        return Promise.resolve();
                    })).finally(() => {
                        setTransitionLoading(false);
                    });
                }
            }
        }
    }, [step, uniqueRepos, isResuming, supportedLanguages, availableLanguages, languageLoading]);

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
                    timestamp: null,
                },
            });

            setCreatedDataset(dataset);

            const repos = extractUniqueRepos();
            setUniqueRepos(repos);

            setStep(2);
            setTransitionLoading(true);

            await Promise.all(repos.map(repo => fetchLanguagesForRepo(repo)));

            if (repos.length > 0) {
                setActiveRepo(repos[0]);
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
        repoConfigs,
        availableLanguages,
        languageLoading,
        activeRepo,
        transitionLoading,
        frameworksByLang,
        features,
        templates,
        selectedFeatures,
        featureSearch,
        featuresLoading,
        collapsedCategories,
        dagData,
        dagLoading,
        minStep,
        fileInputRef,

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
    };
}
