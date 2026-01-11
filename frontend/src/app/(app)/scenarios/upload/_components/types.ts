import { CIProviderOption, BuildSourceRecord, ValidationStats } from "@/types";

export type MappingKey = "build_id" | "repo_name";
export type Step = 1 | 2;
export type CIProviderMode = "single" | "column";

export interface UploadBuildSourceModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess: (source: BuildSourceRecord) => void;
    onSourceCreated?: (source: BuildSourceRecord) => void;
    existingSource?: BuildSourceRecord;
}

export interface CSVPreview {
    columns: string[];
    rows: Record<string, string>[];
    totalRows: number;
    fileName: string;
    fileSize: number;
}

export interface StepUploadProps {
    preview: CSVPreview | null;
    uploading: boolean;
    name: string;
    description: string;
    ciProvider: string;
    ciProviderMode: CIProviderMode;
    ciProviderColumn: string;
    ciProviders: CIProviderOption[];
    mappings: Record<MappingKey, string>;
    isMappingValid: boolean;
    isSourceCreated: boolean;
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    onFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => void;
    onNameChange: (value: string) => void;
    onDescriptionChange: (value: string) => void;
    onCiProviderChange: (value: string) => void;
    onCiProviderModeChange: (mode: CIProviderMode) => void;
    onCiProviderColumnChange: (column: string) => void;
    onMappingChange: (field: MappingKey, value: string) => void;
    onClearFile: () => void;
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
