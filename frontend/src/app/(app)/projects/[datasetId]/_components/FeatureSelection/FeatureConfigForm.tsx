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
import { ChevronDown, ChevronUp, Settings, Globe, Folder, AlertCircle } from "lucide-react";
import { featuresApi } from "@/lib/api";

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

interface FeatureConfigFormProps {
    selectedFeatures: Set<string>;
    onChange: (configs: Record<string, unknown>) => void;
    disabled?: boolean;
}

export function FeatureConfigForm({
    selectedFeatures,
    onChange,
    disabled = false,
}: FeatureConfigFormProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [configs, setConfigs] = useState<Record<string, unknown>>({});
    const [configFields, setConfigFields] = useState<ConfigFieldSpec[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Memoize selected features array to prevent unnecessary API calls
    const selectedFeaturesArray = useMemo(
        () => Array.from(selectedFeatures),
        [selectedFeatures]
    );

    // Fetch config requirements from API when selected features change
    useEffect(() => {
        if (selectedFeaturesArray.length === 0) {
            setConfigFields([]);
            setConfigs({});
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

                    // Initialize configs with defaults
                    const defaultConfigs: Record<string, unknown> = {};
                    response.fields.forEach((field) => {
                        if (field.default !== null && field.default !== undefined) {
                            defaultConfigs[field.name] = field.default;
                        } else if (field.type === "list") {
                            defaultConfigs[field.name] = [];
                        }
                    });
                    setConfigs((prev) => ({ ...defaultConfigs, ...prev }));
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

        // Debounce API call slightly
        const timeoutId = setTimeout(fetchConfigRequirements, 300);

        return () => {
            isCancelled = true;
            clearTimeout(timeoutId);
        };
    }, [selectedFeaturesArray]);

    // Update parent when configs change
    useEffect(() => {
        onChange(configs);
    }, [configs, onChange]);

    // Handle config value change
    const handleConfigChange = useCallback((key: string, value: unknown) => {
        setConfigs((prev) => ({
            ...prev,
            [key]: value,
        }));
    }, []);

    // Parse comma-separated string to array
    const parseArrayValue = (value: string): string[] => {
        return value
            .split(",")
            .map((v) => v.trim().toLowerCase())
            .filter((v) => v.length > 0);
    };

    // Render input based on field type and options
    const renderConfigInput = (field: ConfigFieldSpec) => {
        const currentValue = configs[field.name] ?? field.default ?? "";

        // If options are available, use Select
        if (field.options && field.options.length > 0) {
            if (field.type === "list") {
                // Multi-select with clickable badges
                const arrayValue = (currentValue as string[]) || [];

                const toggleOption = (option: string) => {
                    if (disabled) return;
                    const lowerOption = option.toLowerCase();
                    const newValue = arrayValue.includes(lowerOption)
                        ? arrayValue.filter((v) => v !== lowerOption)
                        : [...arrayValue, lowerOption];
                    handleConfigChange(field.name, newValue);
                };

                return (
                    <div className="flex flex-col gap-2">
                        {/* Option badges grid */}
                        <div className="flex flex-wrap gap-1.5">
                            {field.options.map((option) => {
                                const isSelected = arrayValue.includes(option.toLowerCase());
                                return (
                                    <Badge
                                        key={option}
                                        variant={isSelected ? "default" : "outline"}
                                        className={`cursor-pointer transition-colors ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                            } ${isSelected ? "" : "hover:bg-muted"}`}
                                        onClick={() => toggleOption(option)}
                                    >
                                        {option}
                                    </Badge>
                                );
                            })}
                        </div>
                        {/* Selected count */}
                        {arrayValue.length > 0 && (
                            <span className="text-xs text-muted-foreground">
                                {arrayValue.length} selected: {arrayValue.join(", ")}
                            </span>
                        )}
                    </div>
                );
            } else {
                // Single select
                return (
                    <Select
                        value={String(currentValue || "")}
                        onValueChange={(value) => handleConfigChange(field.name, value)}
                        disabled={disabled}
                    >
                        <SelectTrigger className="flex-1">
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
        }

        // Number input
        if (field.type === "int" || field.type === "number") {
            return (
                <Input
                    type="number"
                    min={1}
                    max={365}
                    value={currentValue as number}
                    onChange={(e) =>
                        handleConfigChange(
                            field.name,
                            parseInt(e.target.value) || field.default || 0
                        )
                    }
                    disabled={disabled}
                    className="w-24"
                />
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
                        handleConfigChange(field.name, parseArrayValue(e.target.value))
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
                onChange={(e) => handleConfigChange(field.name, e.target.value)}
                disabled={disabled}
                className="flex-1"
            />
        );
    };

    // If no features selected or no config fields, don't render
    if (selectedFeaturesArray.length === 0 || (!isLoading && configFields.length === 0)) {
        return null;
    }

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
                    <CardContent className="pt-0 space-y-4">
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
                                {/* Global Configs Section */}
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                                        <Globe className="h-4 w-4" />
                                        Global Settings
                                    </div>

                                    {configFields.map((field) => (
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
                                                {renderConfigInput(field)}
                                                <span className="text-xs text-muted-foreground">
                                                    {field.description}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {/* Info about per-repo configs */}
                                <div className="flex items-start gap-2 p-3 rounded-md bg-muted/50 text-xs text-muted-foreground">
                                    <Folder className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                    <div>
                                        <strong>Note:</strong> These are global settings applied to
                                        all repositories. Per-repository overrides are not yet
                                        supported in the UI.
                                    </div>
                                </div>
                            </>
                        )}
                    </CardContent>
                </CollapsibleContent>
            </Card>
        </Collapsible>
    );
}
