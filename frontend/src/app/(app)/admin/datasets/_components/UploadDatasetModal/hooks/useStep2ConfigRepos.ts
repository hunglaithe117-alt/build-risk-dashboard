"use client";

import { useState, useCallback, useEffect } from "react";
import { CIProvider } from "@/types";
import { reposApi, featuresApi } from "@/lib/api";
import type { CSVPreview, RepoConfig } from "../types";

interface UseStep2ConfigReposReturn {
    uniqueRepos: string[];
    invalidFormatRepos: string[];
    repoConfigs: Record<string, RepoConfig>;
    activeRepo: string | null;
    availableLanguages: Record<string, string[]>;
    languageLoading: Record<string, boolean>;
    frameworks: string[];
    frameworksByLang: Record<string, string[]>;
    supportedLanguages: string[];
    transitionLoading: boolean;
    validReposCount: number;
    invalidReposCount: number;
    setActiveRepo: (repo: string | null) => void;
    toggleLanguage: (repo: string, lang: string) => void;
    toggleFramework: (repo: string, fw: string) => void;
    setCiProvider: (repo: string, provider: CIProvider) => void;
    getSuggestedFrameworks: (config: RepoConfig) => string[];
    extractAndSetRepos: (preview: CSVPreview | null, repoColumn: string) => { valid: string[]; invalid: string[] };
    fetchLanguagesForRepo: (repoName: string) => Promise<void>;
    fetchLanguagesForAllRepos: (repos: string[]) => Promise<void>;
    initializeFromRepoConfigs: (repoConfigs: Array<{
        normalized_full_name: string;
        validation_status: string;
        validation_error?: string;
        source_languages: string[];
        test_frameworks: string[];
        ci_provider: string;
    }>) => void;
    resetStep2: () => void;
}

export function useStep2ConfigRepos(): UseStep2ConfigReposReturn {
    const [uniqueRepos, setUniqueRepos] = useState<string[]>([]);
    const [invalidFormatRepos, setInvalidFormatRepos] = useState<string[]>([]);
    const [repoConfigs, setRepoConfigs] = useState<Record<string, RepoConfig>>({});
    const [activeRepo, setActiveRepo] = useState<string | null>(null);
    const [availableLanguages, setAvailableLanguages] = useState<Record<string, string[]>>({});
    const [languageLoading, setLanguageLoading] = useState<Record<string, boolean>>({});
    const [frameworks, setFrameworks] = useState<string[]>([]);
    const [frameworksByLang, setFrameworksByLang] = useState<Record<string, string[]>>({});
    const [supportedLanguages, setSupportedLanguages] = useState<string[]>([]);
    const [transitionLoading, setTransitionLoading] = useState(false);

    // Load frameworks and languages on mount
    useEffect(() => {
        featuresApi.getConfig()
            .then((config) => {
                setSupportedLanguages(config.languages || []);
                setFrameworks(config.frameworks || []);
                setFrameworksByLang(config.frameworks_by_language || {});
            })
            .catch(console.error);
    }, []);

    // Initialize repo configs when uniqueRepos changes
    useEffect(() => {
        if (uniqueRepos.length === 0) return;

        setRepoConfigs((prev) => {
            const configs: Record<string, RepoConfig> = {};
            uniqueRepos.forEach((repo) => {
                if (!prev[repo]) {
                    configs[repo] = {
                        source_languages: [],
                        test_frameworks: [],
                        ci_provider: CIProvider.GITHUB_ACTIONS,
                        validation_status: "pending",
                    };
                } else {
                    configs[repo] = prev[repo];
                }
            });
            return configs;
        });

        if (!activeRepo && uniqueRepos.length > 0) {
            setActiveRepo(uniqueRepos[0]);
        }
    }, [uniqueRepos, activeRepo]);

    const validReposCount = Object.values(repoConfigs).filter(
        (c) => c.validation_status === "valid"
    ).length;

    const invalidReposCount = Object.values(repoConfigs).filter(
        (c) => c.validation_status === "not_found" || c.validation_status === "error"
    ).length;

    const resetStep2 = useCallback(() => {
        setUniqueRepos([]);
        setInvalidFormatRepos([]);
        setRepoConfigs({});
        setActiveRepo(null);
        setAvailableLanguages({});
        setLanguageLoading({});
        setTransitionLoading(false);
    }, []);

    const initializeFromRepoConfigs = useCallback((repoConfigs: Array<{
        normalized_full_name: string;
        validation_status: string;
        validation_error?: string;
        source_languages: string[];
        test_frameworks: string[];
        ci_provider: string;
    }>) => {
        const valid: string[] = [];
        const invalid: string[] = [];
        const configs: Record<string, RepoConfig> = {};
        const languages: Record<string, string[]> = {};

        repoConfigs.forEach(repo => {
            const fullName = repo.normalized_full_name;
            const isValid = repo.validation_status === "valid";

            if (isValid) {
                valid.push(fullName);
                languages[fullName] = repo.source_languages || [];
            } else {
                invalid.push(fullName);
            }

            configs[fullName] = {
                source_languages: repo.source_languages || [],
                test_frameworks: repo.test_frameworks || [],
                ci_provider: (repo.ci_provider as CIProvider) || CIProvider.GITHUB_ACTIONS,
                validation_status: repo.validation_status as RepoConfig["validation_status"],
                validation_error: repo.validation_error,
            };
        });

        setUniqueRepos(valid);
        setInvalidFormatRepos(invalid);
        setRepoConfigs(configs);
        setAvailableLanguages(languages);
        setTransitionLoading(false);
        if (valid.length > 0) setActiveRepo(valid[0]);
    }, []);

    const extractAndSetRepos = useCallback(
        (preview: CSVPreview | null, repoColumn: string): { valid: string[]; invalid: string[] } => {
            if (!preview || !repoColumn) {
                return { valid: [], invalid: [] };
            }

            const validRepos = new Set<string>();
            const invalidRepos = new Set<string>();

            preview.rows.forEach((row) => {
                const repoName = row[repoColumn]?.trim();
                if (!repoName) return;

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

            const valid = Array.from(validRepos);
            const invalid = Array.from(invalidRepos);

            setUniqueRepos(valid);
            setInvalidFormatRepos(invalid);

            return { valid, invalid };
        },
        []
    );

    const fetchLanguagesForRepo = useCallback(
        async (repoName: string) => {
            setLanguageLoading((prev) => ({ ...prev, [repoName]: true }));

            setRepoConfigs((current) => ({
                ...current,
                [repoName]: {
                    ...current[repoName],
                    test_frameworks: current[repoName]?.test_frameworks || [],
                    source_languages: current[repoName]?.source_languages || [],
                    ci_provider: current[repoName]?.ci_provider || CIProvider.GITHUB_ACTIONS,
                    validation_status: "validating" as const,
                },
            }));

            try {
                const res = await reposApi.detectLanguages(repoName);
                const detected = res.languages || [];

                const validLangs =
                    supportedLanguages.length > 0
                        ? detected.filter((l) =>
                            supportedLanguages.some((sl) => sl.toLowerCase() === l.toLowerCase())
                        )
                        : detected;

                setAvailableLanguages((prev) => ({ ...prev, [repoName]: validLangs }));

                setRepoConfigs((current) => ({
                    ...current,
                    [repoName]: {
                        test_frameworks: current[repoName]?.test_frameworks || [],
                        source_languages: current[repoName]?.source_languages || [],
                        ci_provider: current[repoName]?.ci_provider || CIProvider.GITHUB_ACTIONS,
                        validation_status: "valid" as const,
                    },
                }));
            } catch (err) {
                console.error(`Failed to detect languages for ${repoName}:`, err);
                setAvailableLanguages((prev) => ({ ...prev, [repoName]: [] }));

                const errorMessage = err instanceof Error ? err.message : "Repository not found";
                const isNotFound =
                    errorMessage.includes("404") || errorMessage.toLowerCase().includes("not found");

                setRepoConfigs((current) => ({
                    ...current,
                    [repoName]: {
                        test_frameworks: [],
                        source_languages: [],
                        ci_provider: current[repoName]?.ci_provider || CIProvider.GITHUB_ACTIONS,
                        validation_status: isNotFound ? ("not_found" as const) : ("error" as const),
                        validation_error: errorMessage,
                    },
                }));
            } finally {
                setLanguageLoading((prev) => ({ ...prev, [repoName]: false }));
            }
        },
        [supportedLanguages]
    );

    const fetchLanguagesForAllRepos = useCallback(
        async (repos: string[]) => {
            setTransitionLoading(true);
            try {
                await Promise.all(repos.map((repo) => fetchLanguagesForRepo(repo)));
            } finally {
                setTransitionLoading(false);
            }
        },
        [fetchLanguagesForRepo]
    );

    const toggleLanguage = useCallback((repo: string, lang: string) => {
        setRepoConfigs((prev) => {
            const config = prev[repo] || {
                source_languages: [],
                test_frameworks: [],
                ci_provider: CIProvider.GITHUB_ACTIONS,
                validation_status: "pending" as const,
            };
            const languages = config.source_languages.includes(lang)
                ? config.source_languages.filter((l) => l !== lang)
                : [...config.source_languages, lang];
            return { ...prev, [repo]: { ...config, source_languages: languages } };
        });
    }, []);

    const toggleFramework = useCallback((repo: string, fw: string) => {
        setRepoConfigs((prev) => {
            const config = prev[repo] || {
                source_languages: [],
                test_frameworks: [],
                ci_provider: CIProvider.GITHUB_ACTIONS,
                validation_status: "pending" as const,
            };
            const frameworks = config.test_frameworks.includes(fw)
                ? config.test_frameworks.filter((f) => f !== fw)
                : [...config.test_frameworks, fw];
            return { ...prev, [repo]: { ...config, test_frameworks: frameworks } };
        });
    }, []);

    const setCiProvider = useCallback((repo: string, provider: CIProvider) => {
        setRepoConfigs((prev) => {
            const config = prev[repo] || {
                source_languages: [],
                test_frameworks: [],
                ci_provider: CIProvider.GITHUB_ACTIONS,
                validation_status: "pending" as const,
            };
            return { ...prev, [repo]: { ...config, ci_provider: provider } };
        });
    }, []);

    const getSuggestedFrameworks = useCallback(
        (config: RepoConfig) => {
            const langs = config.source_languages.map((l) => l.toLowerCase());
            const suggested = new Set<string>();
            langs.forEach((lang) => {
                const fws = frameworksByLang[lang] || [];
                fws.forEach((fw) => suggested.add(fw));
            });
            return Array.from(suggested);
        },
        [frameworksByLang]
    );

    return {
        uniqueRepos,
        invalidFormatRepos,
        repoConfigs,
        activeRepo,
        availableLanguages,
        languageLoading,
        frameworks,
        frameworksByLang,
        supportedLanguages,
        transitionLoading,
        validReposCount,
        invalidReposCount,
        setActiveRepo,
        toggleLanguage,
        toggleFramework,
        setCiProvider,
        getSuggestedFrameworks,
        extractAndSetRepos,
        fetchLanguagesForRepo,
        fetchLanguagesForAllRepos,
        initializeFromRepoConfigs,
        resetStep2,
    };
}
