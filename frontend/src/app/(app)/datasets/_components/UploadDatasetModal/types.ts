import { CIProvider, DatasetRecord, DatasetTemplateRecord, FeatureDefinitionSummary } from "@/types";
import type { FeatureDAGData } from "@/app/(app)/admin/repos/_components/FeatureDAGVisualization";

export { type FeatureDAGData };

export type MappingKey = "build_id" | "repo_name";
export type Step = 1 | 2 | 3 | 4;

export interface UploadDatasetModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess: (dataset: DatasetRecord) => void;
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
    mappings: Record<MappingKey, string>;
    isMappingValid: boolean;
    fileInputRef: React.RefObject<HTMLInputElement>;
    onFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
    onNameChange: (value: string) => void;
    onDescriptionChange: (value: string) => void;
    onMappingChange: (field: MappingKey, value: string) => void;
    onClearFile: () => void;
}

export interface StepConfigureReposProps {
    uniqueRepos: string[];
    invalidFormatRepos: string[];
    repoConfigs: Record<string, RepoConfig>;
    activeRepo: string | null;
    availableLanguages: Record<string, string[]>;
    languageLoading: Record<string, boolean>;
    frameworksByLang: Record<string, string[]>;
    transitionLoading: boolean;
    onActiveRepoChange: (repo: string) => void;
    onToggleLanguage: (repo: string, lang: string) => void;
    onToggleFramework: (repo: string, fw: string) => void;
    onSetCiProvider: (repo: string, provider: CIProvider) => void;
    getSuggestedFrameworks: (config: RepoConfig) => string[];
}

export interface StepSelectFeaturesProps {
    features: FeatureCategoryGroup[];
    templates: DatasetTemplateRecord[];
    selectedFeatures: Set<string>;
    featureSearch: string;
    featuresLoading: boolean;
    collapsedCategories: Set<string>;
    onFeatureSearchChange: (value: string) => void;
    onToggleFeature: (featureName: string) => void;
    onToggleCategory: (category: string) => void;
    onApplyTemplate: (template: DatasetTemplateRecord) => void;
    onClearAll: () => void;
    // DAG-related props
    dagData: FeatureDAGData | null;
    dagLoading: boolean;
    onLoadDAG: () => void;
    onSetSelectedFeatures: (features: string[]) => void;
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

export interface TemplateSelectorProps {
    templates: DatasetTemplateRecord[];
    selectedTemplate: DatasetTemplateRecord | null;
    onSelectTemplate: (template: DatasetTemplateRecord) => void;
    onApplyTemplate: () => void;
}
