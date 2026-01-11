"use client";

import { createContext, useContext, useState, ReactNode } from "react";

// =============================================================================
// Constants - Matching backend enums
// =============================================================================

/**
 * Supported CI providers from backend/app/ci_providers/models.py
 */
export const CI_PROVIDERS = [
    { value: "github_actions", label: "GitHub Actions" },
    { value: "circleci", label: "CircleCI" },
    { value: "travis_ci", label: "Travis CI" },
] as const;

export type CIProviderKey = typeof CI_PROVIDERS[number]["value"];

/**
 * Build conclusions that are actually stored in the database.
 * Note: SKIPPED, CANCELLED, STALE, ACTION_REQUIRED are filtered out during ingestion
 * (see dataset_validation.py and model_ingestion.py)
 */
export const BUILD_CONCLUSIONS = [
    { value: "success", label: "Success" },
    { value: "failure", label: "Failure" },
] as const;

export type BuildConclusionKey = typeof BUILD_CONCLUSIONS[number]["value"];

/**
 * Supported languages from backend/app/tasks/pipeline/feature_dag/languages/registry.py
 */
export const SUPPORTED_LANGUAGES = [
    { value: "python", label: "Python" },
    { value: "javascript", label: "JavaScript" },
    { value: "typescript", label: "TypeScript" },
    { value: "java", label: "Java" },
    { value: "go", label: "Go" },
    { value: "ruby", label: "Ruby" },
    { value: "cpp", label: "C/C++" },
] as const;

export type LanguageKey = typeof SUPPORTED_LANGUAGES[number]["value"];

// =============================================================================
// Types
// =============================================================================

export interface DataSourceConfig {
    filter_by: "all" | "by_language" | "by_name";
    languages: string[];
    repo_names: string[];
    date_start: string;
    date_end: string;
    conclusions: string[];
    ci_provider: CIProviderKey | "all";

}

export interface FeatureConfig {
    dag_features: string[];
    scan_metrics: {
        sonarqube: string[];
        trivy: string[];
    };
    exclude: string[];
}

export interface SplittingConfig {
    strategy: string;
    group_by: string;
    groups: string[];
    ratios: {
        train: number;
        val: number;
        test: number;
    };
    stratify_by: string;
    // Advanced options
    temporal_ordering: boolean;
    test_groups: string[];
    val_groups: string[];
    train_groups: string[];
}

export interface PreprocessingConfig {
    missing_values_strategy: "drop_row" | "fill" | "skip_feature";
    fill_value: number | string;
    normalization_method: "z_score" | "min_max" | "robust" | "none";
    strict_mode: boolean;
}

export interface OutputConfig {
    format: "parquet" | "csv" | "pickle";
    include_metadata: boolean;
}

export interface PreviewStats {
    total_builds: number;
    total_repos: number;
    outcome_distribution: {
        success: number;
        failure: number;
    };
    repos?: { id: string; full_name: string }[];
}

export interface WizardState {
    // Current step (1-5)
    step: number;

    // Scenario metadata
    name: string;
    description: string;

    // Step 1: Data Source
    dataSource: DataSourceConfig;
    previewStats: PreviewStats | null;
    previewRepos: { id: string; full_name: string }[];

    // Step 2: Features
    features: FeatureConfig;
    featureConfigs: Record<string, any>; // Detailed feature params
    scanConfigs: Record<string, any>; // Detailed scan params

    // Step 3: Splitting
    splitting: SplittingConfig;

    // Step 4: Preprocessing & Output
    preprocessing: PreprocessingConfig;
    output: OutputConfig;

    // Loading states
    isPreviewLoading: boolean;
    isSubmitting: boolean;
}

interface WizardContextValue {
    state: WizardState;
    setStep: (step: number) => void;
    setName: (name: string) => void;
    setDescription: (description: string) => void;
    updateDataSource: (updates: Partial<DataSourceConfig>) => void;
    setPreviewStats: (stats: PreviewStats | null) => void;
    setPreviewRepos: (repos: { id: string; full_name: string }[]) => void;
    updateFeatures: (updates: Partial<FeatureConfig>) => void;
    setFeatureConfigs: (configs: Record<string, any>) => void;
    setScanConfigs: (configs: Record<string, any>) => void;
    updateSplitting: (updates: Partial<SplittingConfig>) => void;
    updatePreprocessing: (updates: Partial<PreprocessingConfig>) => void;
    updateOutput: (updates: Partial<OutputConfig>) => void;
    setIsPreviewLoading: (loading: boolean) => void;
    setIsSubmitting: (submitting: boolean) => void;
    resetState: () => void;
}

// =============================================================================
// Initial State
// =============================================================================

const initialDataSource: DataSourceConfig = {
    filter_by: "all",
    languages: [],
    repo_names: [],
    date_start: "",
    date_end: "",
    conclusions: ["success", "failure"],
    ci_provider: "all",
};

const initialFeatures: FeatureConfig = {
    dag_features: ["build_*", "git_*", "log_*", "repo_*", "history_*", "author_*"],
    scan_metrics: {
        sonarqube: [],
        trivy: [],
    },
    exclude: [],
};

const initialSplitting: SplittingConfig = {
    strategy: "stratified_within_group",
    group_by: "language_group",
    groups: ["backend", "fullstack", "scripting", "other"],
    ratios: { train: 0.7, val: 0.15, test: 0.15 },
    stratify_by: "outcome",
    temporal_ordering: true,
    test_groups: [],
    val_groups: [],
    train_groups: [],
};

const initialPreprocessing: PreprocessingConfig = {
    missing_values_strategy: "drop_row",
    fill_value: 0,
    normalization_method: "z_score",
    strict_mode: false,
};

const initialOutput: OutputConfig = {
    format: "parquet",
    include_metadata: true,
};

const initialState: WizardState = {
    step: 1,
    name: "",
    description: "",
    dataSource: initialDataSource,
    previewStats: null,
    previewRepos: [],
    features: initialFeatures,
    featureConfigs: {},
    scanConfigs: {},
    splitting: initialSplitting,
    preprocessing: initialPreprocessing,
    output: initialOutput,
    isPreviewLoading: false,
    isSubmitting: false,
};

// =============================================================================
// Context
// =============================================================================

const WizardContext = createContext<WizardContextValue | null>(null);

export function WizardProvider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<WizardState>(initialState);

    const setStep = (step: number) => setState((s) => ({ ...s, step }));
    const setName = (name: string) => setState((s) => ({ ...s, name }));
    const setDescription = (description: string) => setState((s) => ({ ...s, description }));

    const updateDataSource = (updates: Partial<DataSourceConfig>) =>
        setState((s) => ({ ...s, dataSource: { ...s.dataSource, ...updates } }));

    const setPreviewStats = (stats: PreviewStats | null) =>
        setState((s) => ({ ...s, previewStats: stats }));

    const setPreviewRepos = (repos: { id: string; full_name: string }[]) =>
        setState((s) => ({ ...s, previewRepos: repos }));

    const updateFeatures = (updates: Partial<FeatureConfig>) =>
        setState((s) => ({ ...s, features: { ...s.features, ...updates } }));

    const setFeatureConfigs = (configs: Record<string, any>) =>
        setState((s) => ({ ...s, featureConfigs: configs }));

    const setScanConfigs = (configs: Record<string, any>) =>
        setState((s) => ({ ...s, scanConfigs: configs }));

    const updateSplitting = (updates: Partial<SplittingConfig>) =>
        setState((s) => ({ ...s, splitting: { ...s.splitting, ...updates } }));

    const updatePreprocessing = (updates: Partial<PreprocessingConfig>) =>
        setState((s) => ({ ...s, preprocessing: { ...s.preprocessing, ...updates } }));

    const updateOutput = (updates: Partial<OutputConfig>) =>
        setState((s) => ({ ...s, output: { ...s.output, ...updates } }));

    const setIsPreviewLoading = (loading: boolean) =>
        setState((s) => ({ ...s, isPreviewLoading: loading }));

    const setIsSubmitting = (submitting: boolean) =>
        setState((s) => ({ ...s, isSubmitting: submitting }));

    const resetState = () => setState(initialState);

    return (
        <WizardContext.Provider
            value={{
                state,
                setStep,
                setName,
                setDescription,
                updateDataSource,
                setPreviewStats,
                setPreviewRepos,
                updateFeatures,
                setFeatureConfigs,
                setScanConfigs,
                updateSplitting,
                updatePreprocessing,
                updateOutput,
                setIsPreviewLoading,
                setIsSubmitting,
                resetState,
            }}
        >
            {children}
        </WizardContext.Provider>
    );
}

export function useWizard() {
    const context = useContext(WizardContext);
    if (!context) {
        throw new Error("useWizard must be used within a WizardProvider");
    }
    return context;
}
