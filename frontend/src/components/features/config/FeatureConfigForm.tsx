"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronDown, ChevronUp, Settings, Globe, AlertCircle } from "lucide-react";
import { featuresApi, datasetsApi } from "@/lib/api";
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
    id: string; // raw_repo_id
    full_name: string;
    validation_status: string;
}

// Dynamic config: field name -> array of selected values
export type RepoConfig = Record<string, string[]>;

/** Structure for configs: { global: {...}, repos: {...} } */
export interface FeatureConfigsData {
    global: Record<string, unknown>;
    repos: Record<string, RepoConfig>;
}

interface FeatureConfigFormProps {
    datasetId?: string; // Optional if repos provided directly
    repos?: RepoInfo[]; // Direct shuffle for ImportRepoModal
    selectedFeatures: Set<string>;
    onChange: (configs: FeatureConfigsData) => void;
    disabled?: boolean;
}

export function FeatureConfigForm({
    datasetId,
    repos: providedRepos,
    selectedFeatures,
    onChange,
    disabled = false,
}: FeatureConfigFormProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [globalConfigs, setGlobalConfigs] = useState<Record<string, unknown>>({});
    const [repoConfigs, setRepoConfigs] = useState<Record<string, RepoConfig>>({});
    const [configFields, setConfigFields] = useState<ConfigFieldSpec[]>([]);
    const [repos, setRepos] = useState<RepoInfo[]>(providedRepos || []);
    const [isLoading, setIsLoading] = useState(false);
    const [isLoadingRepos, setIsLoadingRepos] = useState(false);
    const [error, setError] = useState<string | null>(null);

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

    // Fetch repos from dataset (only if datasetId used and no direct repos)
    useEffect(() => {
        if (!datasetId || providedRepos) return;

        let isCancelled = false;

        async function fetchRepos() {
            setIsLoadingRepos(true);
            try {
                const summary = await datasetsApi.getValidationSummary(datasetId!);
                if (!isCancelled && summary.repos) {
                    setRepos(summary.repos.map(r => ({
                        id: r.id,
                        full_name: r.full_name,
                        validation_status: r.validation_status,
                    })));
                }
            } catch (err) {
                console.error("Failed to fetch repos:", err);
                // Non-blocking error - repos section just won't show
            } finally {
                if (!isCancelled) setIsLoadingRepos(false);
            }
        }

        fetchRepos();
        return () => { isCancelled = true; };
    }, [datasetId, providedRepos]);

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

    // If no features selected or no config fields, don't render
    if (selectedFeaturesArray.length === 0 || (!isLoading && configFields.length === 0)) {
        return null;
    }

    const hasGlobalFields = globalFields.length > 0;
    const hasRepoFields = repoFields.length > 0;

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <Card className="border-dashed">
                <CollapsibleTrigger asChild>
                    <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors py-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Settings className="h-4 w-4 text-muted-foreground" />
                                <CardTitle className="text-sm font-medium">
                                    Feature Configuration
                                </CardTitle>
                                {isLoading ? (
                                    <Skeleton className="h-5 w-16" />
                                ) : configFields.length > 0 && (
                                    <Badge variant="secondary" className="text-xs">
                                        {configFields.length} field{configFields.length > 1 ? "s" : ""}
                                    </Badge>
                                )}
                            </div>
                            <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                                {isOpen ? (
                                    <ChevronUp className="h-4 w-4" />
                                ) : (
                                    <ChevronDown className="h-4 w-4" />
                                )}
                            </Button>
                        </div>
                        <CardDescription className="text-xs">
                            {isLoading
                                ? "Loading configuration options..."
                                : "Configure parameters for selected features"}
                        </CardDescription>
                    </CardHeader>
                </CollapsibleTrigger>

                <CollapsibleContent>
                    <CardContent className="pt-0 space-y-6">
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
                                    />
                                )}
                            </>
                        )}
                    </CardContent>
                </CollapsibleContent>
            </Card>
        </Collapsible>
    );
}
