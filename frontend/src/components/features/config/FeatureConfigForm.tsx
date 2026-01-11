"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Settings, Globe, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { featuresApi, reposApi } from "@/lib/api";
import { RepoConfigSection } from "./RepoConfigSection";

/** Config field spec from API */
interface ConfigFieldSpec {
    name: string;
    type: string;
    scope: string;
    required: boolean;
    description: string;
    default: unknown;
    options: string[] | null;
}

interface RepoInfo {
    id: string; // github_repo_id
    full_name: string;
    validation_status?: string; // Optional - not available in Training Scenario wizard
}

// Dynamic config: field name -> array of selected values
export type RepoConfig = Record<string, string[]>;

/** Structure for configs: { global: {...}, repos: {...} } */
export interface FeatureConfigsData {
    global: Record<string, unknown>;
    repos: Record<string, RepoConfig>;
}

interface FeatureConfigFormProps {
    datasetId?: string; // Deprecated - repos should be passed directly
    repos?: RepoInfo[]; // Direct repos list
    repoLanguages?: Record<string, string[]>; // Pre-fetched languages per repo (key = repo id)
    selectedFeatures: Set<string>;
    value?: FeatureConfigsData;
    onChange: (configs: FeatureConfigsData) => void;
    disabled?: boolean;
    showValidationStatusColumn?: boolean;
}

export function FeatureConfigForm({
    datasetId,
    repos: providedRepos,
    repoLanguages: providedRepoLanguages,
    selectedFeatures,
    value,
    onChange,
    disabled = false,
    showValidationStatusColumn = true,
}: FeatureConfigFormProps) {
    // State initialization
    const [globalConfigs, setGlobalConfigs] = useState<Record<string, unknown>>(value?.global || {});
    const [repoConfigs, setRepoConfigs] = useState<Record<string, RepoConfig>>(value?.repos || {});
    const [configFields, setConfigFields] = useState<ConfigFieldSpec[]>([]);
    const [repos, setRepos] = useState<RepoInfo[]>(providedRepos || []);
    const [isLoading, setIsLoading] = useState(false);
    const [isLoadingRepos, setIsLoadingRepos] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Use provided languages or fallback to empty (no internal fetching)
    const repoLanguages = providedRepoLanguages || {};

    // Update repos if provided directly
    useEffect(() => {
        if (providedRepos) {
            setRepos(providedRepos);
        }
    }, [providedRepos]);

    // Memoize selected features array
    const selectedFeaturesArray = useMemo(
        () => Array.from(selectedFeatures),
        [selectedFeatures]
    );

    // Separate fields by scope
    const { globalFields, repoFields } = useMemo(() => {
        const global = configFields.filter(f => f.scope === "global");
        const repo = configFields.filter(f => f.scope === "repo");
        return { globalFields: global, repoFields: repo };
    }, [configFields]);

    // Note: Language detection has been moved to parent components
    // Parent should pass repoLanguages prop with pre-fetched language data

    // Fetch config requirements when selected features change
    useEffect(() => {
        if (selectedFeaturesArray.length === 0) {
            setConfigFields([]);
            setGlobalConfigs({});
            return;
        }

        let isCancelled = false;

        async function fetchConfigRequirements() {
            setIsLoading(true);
            setError(null);

            try {
                const response = await featuresApi.getConfigRequirements(selectedFeaturesArray);

                if (!isCancelled) {
                    setConfigFields(response.fields);

                    // Initialize global configs with defaults
                    const defaultGlobal: Record<string, unknown> = {};
                    response.fields
                        .filter(f => f.scope === "global")
                        .forEach((field) => {
                            if (field.default !== null && field.default !== undefined) {
                                defaultGlobal[field.name] = field.default;
                            } else if (field.type === "list") {
                                defaultGlobal[field.name] = [];
                            }
                        });
                    setGlobalConfigs((prev) => ({ ...defaultGlobal, ...prev }));
                }
            } catch (err) {
                if (!isCancelled) {
                    console.error("Failed to fetch config requirements:", err);
                    setError("Failed to load configuration options");
                }
            } finally {
                if (!isCancelled) {
                    setIsLoading(false);
                }
            }
        }

        const timeoutId = setTimeout(fetchConfigRequirements, 300);

        return () => {
            isCancelled = true;
            clearTimeout(timeoutId);
        };
    }, [selectedFeaturesArray]);

    // Update parent when configs change
    useEffect(() => {
        onChange({
            global: globalConfigs,
            repos: repoConfigs,
        });
    }, [globalConfigs, repoConfigs, onChange]);

    // Handle global config value change
    const handleGlobalConfigChange = useCallback((key: string, value: unknown) => {
        setGlobalConfigs((prev) => ({
            ...prev,
            [key]: value,
        }));
    }, []);

    // Handle repo configs change
    const handleRepoConfigsChange = useCallback((configs: Record<string, RepoConfig>) => {
        setRepoConfigs(configs);
    }, []);

    // Parse comma-separated string to array
    const parseArrayValue = (value: string): string[] => {
        return value
            .split(",")
            .map((v) => v.trim().toLowerCase())
            .filter((v) => v.length > 0);
    };

    // Render input for global fields
    const renderGlobalConfigInput = (field: ConfigFieldSpec) => {
        const currentValue = globalConfigs[field.name] ?? field.default ?? "";

        // Number input
        if (field.type === "int" || field.type === "integer" || field.type === "number") {
            return (
                <Input
                    type="number"
                    min={1}
                    max={365}
                    value={currentValue as number}
                    onChange={(e) =>
                        handleGlobalConfigChange(
                            field.name,
                            parseInt(e.target.value) || field.default || 0
                        )
                    }
                    disabled={disabled}
                    className="w-24"
                />
            );
        }

        // Boolean/Select
        if (field.options && field.options.length > 0 && field.type !== "list") {
            return (
                <Select
                    value={String(currentValue || "")}
                    onValueChange={(value) => handleGlobalConfigChange(field.name, value)}
                    disabled={disabled}
                >
                    <SelectTrigger className="w-40">
                        <SelectValue placeholder="Select..." />
                    </SelectTrigger>
                    <SelectContent>
                        {field.options.map((option) => (
                            <SelectItem key={option} value={option}>
                                {option}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            );
        }

        // List input (comma-separated)
        if (field.type === "list") {
            const arrayValue = (currentValue as string[]) || [];
            return (
                <Input
                    type="text"
                    placeholder="Enter values separated by commas"
                    value={arrayValue.join(", ")}
                    onChange={(e) =>
                        handleGlobalConfigChange(field.name, parseArrayValue(e.target.value))
                    }
                    disabled={disabled}
                    className="flex-1"
                />
            );
        }

        // Default: text input
        return (
            <Input
                type="text"
                value={String(currentValue)}
                onChange={(e) => handleGlobalConfigChange(field.name, e.target.value)}
                disabled={disabled}
                className="flex-1"
            />
        );
    };

    // If no features selected or no config fields, don't render config
    if (selectedFeaturesArray.length === 0 || (!isLoading && configFields.length === 0)) {
        return null;
    }

    const hasGlobalFields = globalFields.length > 0;
    const hasRepoFields = repoFields.length > 0;

    return (
        <div className="space-y-6">
            {/* Header Section */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Settings className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-medium">
                        Feature Configuration
                    </h3>
                    {isLoading ? (
                        <Skeleton className="h-5 w-16" />
                    ) : configFields.length > 0 && (
                        <Badge variant="secondary" className="text-xs">
                            {configFields.length} field{configFields.length > 1 ? "s" : ""}
                        </Badge>
                    )}
                </div>
            </div>

            <p className="text-xs text-muted-foreground -mt-4">
                {isLoading
                    ? "Loading configuration options..."
                    : "Configure parameters for selected features"}
            </p>

            {error && (
                <div className="flex items-center gap-2 p-2 rounded-md bg-destructive/10 text-destructive text-sm">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            {isLoading ? (
                <div className="space-y-3">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                </div>
            ) : (
                <>
                    {/* Global Settings Section */}
                    {hasGlobalFields && (
                        <div className="space-y-3">
                            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                                <Globe className="h-4 w-4" />
                                Global Settings
                            </div>

                            {globalFields.map((field) => (
                                <div
                                    key={field.name}
                                    className="grid grid-cols-[140px_1fr] gap-3 items-start"
                                >
                                    <Label
                                        htmlFor={field.name}
                                        className="text-sm pt-2 flex items-center gap-1"
                                    >
                                        {field.name.replace(/_/g, " ")}
                                        {field.required && (
                                            <span className="text-destructive">*</span>
                                        )}
                                    </Label>
                                    <div className="flex flex-col gap-1">
                                        {renderGlobalConfigInput(field)}
                                        <span className="text-xs text-muted-foreground">
                                            {field.description}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Repository Settings Section */}
                    {hasRepoFields && (
                        <RepoConfigSection
                            repos={repos}
                            repoFields={repoFields}
                            repoConfigs={repoConfigs}
                            onChange={handleRepoConfigsChange}
                            disabled={disabled}
                            isLoading={isLoadingRepos}
                            repoLanguages={repoLanguages}
                            showValidationStatusColumn={showValidationStatusColumn}
                        />
                    )}
                </>
            )}
        </div>
    );
}
