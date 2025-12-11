import { CIProvider, DatasetRecord, DatasetTemplateRecord, FeatureDefinitionSummary, ValidationStats, RepoValidationResultNew } from "@/types";
import type { FeatureDAGData } from "@/app/(app)/admin/repos/_components/FeatureDAGVisualization";

export { type FeatureDAGData };

export type MappingKey = "build_id" | "repo_name";
export type Step = 1 | 2 | 3;

export interface UploadDatasetModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess: (dataset: DatasetRecord) => void;
    onDatasetCreated?: (dataset: DatasetRecord) => void;
    existingDataset?: DatasetRecord;
}

export interface CSVPreview {
    columns: string[];
    rows: Record<string, string>[];
    totalRows: number;
    fileName: string;
    fileSize: number;
}

export interface RepoConfig {
    source_languages: string[];
    test_frameworks: string[];
    ci_provider: CIProvider;
    validation_status: "pending" | "validating" | "valid" | "not_found" | "error";
    validation_error?: string;
}

export interface FeatureCategoryGroup {
    category: string;
    display_name?: string;
    features: FeatureDefinitionSummary[];
}

export interface StepUploadProps {
    preview: CSVPreview | null;
    uploading: boolean;
    name: string;
    description: string;
    ciProvider: CIProvider;
    mappings: Record<MappingKey, string>;
    isMappingValid: boolean;
    isDatasetCreated: boolean;
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    onFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
    onNameChange: (value: string) => void;
    onDescriptionChange: (value: string) => void;
    onCiProviderChange: (value: CIProvider) => void;
    onMappingChange: (field: MappingKey, value: string) => void;
    onClearFile: () => void;
}

// Step 2: Configure repos with per-repo languages/frameworks
export interface StepConfigureReposProps {
    uniqueRepos: string[];
    invalidFormatRepos: string[];
    repoConfigs: Record<string, RepoConfig>;
    activeRepo: string | null;
    availableLanguages: Record<string, string[]>;
    languageLoading: Record<string, boolean>;
    transitionLoading: boolean;
    validReposCount: number;
    invalidReposCount: number;
    onActiveRepoChange: (repo: string) => void;
    onToggleLanguage: (repo: string, lang: string) => void;
    onToggleFramework: (repo: string, fw: string) => void;
    onSetCiProvider: (repo: string, provider: CIProvider) => void;
    getSuggestedFrameworks: (config: RepoConfig) => string[];
}

// Step 3: Validation progress
export interface StepValidateProps {
    datasetId: string | null;
    validationStatus: "pending" | "validating" | "completed" | "failed" | "cancelled";
    validationProgress: number;
    validationStats: ValidationStats | null;
    validationError: string | null;
    validatedRepos: RepoValidationResultNew[];
    onStartValidation: () => void;
    onCancelValidation: () => void;
}

export interface ColumnSelectorProps {
    value: string;
    columns: string[];
    onChange: (value: string) => void;
    placeholder?: string;
}

export interface StepIndicatorProps {
    currentStep: Step;
}
