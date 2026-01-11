"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import yaml from "js-yaml";
import {
    ChevronLeft,
    FileCode,
    CheckCircle2,
    AlertTriangle,
    Upload,
    Copy,
    Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useToast } from "@/components/ui/use-toast";
import { trainingScenariosApi } from "@/lib/api";

// Validation types based on TrainingScenario entity
interface ValidationError {
    path: string;
    message: string;
}

interface YamlConfig {
    scenario?: {
        name?: string;
        description?: string;
        version?: string;
    };
    data_source?: {
        repositories?: {
            filter_by?: string;
            languages?: string[];
            repo_names?: string[];
            owners?: string[];
        };
        builds?: {
            date_range?: {
                start?: string;
                end?: string;
            };
            conclusions?: string[];
            exclude_bots?: boolean;
        };
        ci_provider?: string;
    };
    features?: {
        dag_features?: string[];
        scan_metrics?: {
            sonarqube?: string[];
            trivy?: string[];
        };
        exclude?: string[];
    };
    splitting?: {
        strategy?: string;
        group_by?: string;
        config?: {
            ratios?: {
                train?: number;
                val?: number;
                test?: number;
            };
            stratify_by?: string;
            test_groups?: string[];
            val_groups?: string[];
            train_groups?: string[];
        };
    };
    output?: {
        format?: string;
        include_metadata?: boolean;
    };
}

// Valid values for enums
const VALID_FILTER_BY = ["all", "by_language", "by_name", "by_owner"];
const VALID_CI_PROVIDERS = ["all", "github_actions", "circleci"];
const VALID_STRATEGIES = [
    "stratified_within_group",
    "leave_one_out",
    "leave_two_out",
    "imbalanced_train",
    "extreme_novelty",
];
const VALID_GROUP_BY = [
    "language_group",
    "percentage_of_builds_before",
    "number_of_builds_before",
    "time_of_day",
];
const VALID_OUTPUT_FORMATS = ["parquet", "csv", "pickle"];

function validateYamlConfig(config: YamlConfig): ValidationError[] {
    const errors: ValidationError[] = [];

    // Scenario validation
    if (!config.scenario?.name) {
        errors.push({ path: "scenario.name", message: "Name is required" });
    }

    // Data source validation
    if (config.data_source?.repositories?.filter_by) {
        if (!VALID_FILTER_BY.includes(config.data_source.repositories.filter_by)) {
            errors.push({
                path: "data_source.repositories.filter_by",
                message: `Invalid filter_by. Must be one of: ${VALID_FILTER_BY.join(", ")}`,
            });
        }
    }

    if (config.data_source?.ci_provider) {
        if (!VALID_CI_PROVIDERS.includes(config.data_source.ci_provider)) {
            errors.push({
                path: "data_source.ci_provider",
                message: `Invalid ci_provider. Must be one of: ${VALID_CI_PROVIDERS.join(", ")}`,
            });
        }
    }

    // Splitting validation
    if (config.splitting?.strategy) {
        if (!VALID_STRATEGIES.includes(config.splitting.strategy)) {
            errors.push({
                path: "splitting.strategy",
                message: `Invalid strategy. Must be one of: ${VALID_STRATEGIES.join(", ")}`,
            });
        }
    }

    if (config.splitting?.group_by) {
        if (!VALID_GROUP_BY.includes(config.splitting.group_by)) {
            errors.push({
                path: "splitting.group_by",
                message: `Invalid group_by. Must be one of: ${VALID_GROUP_BY.join(", ")}`,
            });
        }
    }

    // Ratios validation
    if (config.splitting?.config?.ratios) {
        const { train, val, test } = config.splitting.config.ratios;
        if (train !== undefined && val !== undefined && test !== undefined) {
            const sum = train + val + test;
            if (Math.abs(sum - 1) > 0.01) {
                errors.push({
                    path: "splitting.config.ratios",
                    message: `Ratios must sum to 1.0, got ${sum.toFixed(2)}`,
                });
            }
        }
    }

    // Output validation
    if (config.output?.format) {
        if (!VALID_OUTPUT_FORMATS.includes(config.output.format)) {
            errors.push({
                path: "output.format",
                message: `Invalid format. Must be one of: ${VALID_OUTPUT_FORMATS.join(", ")}`,
            });
        }
    }

    return errors;
}

// Transform YAML config to API payload
function transformToPayload(config: YamlConfig) {
    return {
        name: config.scenario?.name || "Untitled",
        description: config.scenario?.description,
        data_source_config: {
            filter_by: config.data_source?.repositories?.filter_by || "all",
            languages: config.data_source?.repositories?.languages || [],
            repo_names: config.data_source?.repositories?.repo_names || [],
            date_start: config.data_source?.builds?.date_range?.start,
            date_end: config.data_source?.builds?.date_range?.end,
            conclusions: config.data_source?.builds?.conclusions || ["success", "failure"],
            ci_provider: config.data_source?.ci_provider || "all",
        },
        feature_config: {
            dag_features: config.features?.dag_features || [],
            scan_metrics: config.features?.scan_metrics || {},
            exclude: config.features?.exclude || [],
        },
        splitting_config: {
            strategy: config.splitting?.strategy || "stratified_within_group",
            group_by: config.splitting?.group_by || "language_group",
            ratios: config.splitting?.config?.ratios || { train: 0.7, val: 0.15, test: 0.15 },
            stratify_by: config.splitting?.config?.stratify_by || "outcome",
        },
        output_config: {
            format: config.output?.format || "parquet",
            include_metadata: config.output?.include_metadata ?? true,
        },
    };
}

const SAMPLE_YAML = `scenario:
  name: "my_dataset_config"
  description: "Dataset configuration for training"
  version: "1.0"

data_source:
  repositories:
    filter_by: "all"
  builds:
    conclusions: ["success", "failure"]
    exclude_bots: true
  ci_provider: "github_actions"

features:
  dag_features:
    - "build_*"
    - "git_*"
    - "log_*"

splitting:
  strategy: "stratified_within_group"
  group_by: "language_group"
  config:
    ratios:
      train: 0.70
      val: 0.15
      test: 0.15

output:
  format: "parquet"
  include_metadata: true`;

export default function ImportYamlPage() {
    const router = useRouter();
    const { toast } = useToast();
    const [yamlContent, setYamlContent] = useState("");
    const [errors, setErrors] = useState<ValidationError[]>([]);
    const [parseError, setParseError] = useState<string | null>(null);
    const [isValid, setIsValid] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [parsedConfig, setParsedConfig] = useState<YamlConfig | null>(null);

    const handleValidate = useCallback(() => {
        setParseError(null);
        setErrors([]);
        setIsValid(false);
        setParsedConfig(null);

        if (!yamlContent.trim()) {
            setParseError("Please enter YAML content");
            return;
        }

        try {
            const parsed = yaml.load(yamlContent) as YamlConfig;
            setParsedConfig(parsed);

            const validationErrors = validateYamlConfig(parsed);
            setErrors(validationErrors);

            if (validationErrors.length === 0) {
                setIsValid(true);
                toast({
                    title: "Validation passed",
                    description: "YAML configuration is valid!",
                });
            }
        } catch (e) {
            setParseError(`YAML parse error: ${(e as Error).message}`);
        }
    }, [yamlContent, toast]);

    const handleSubmit = async () => {
        if (!isValid || !parsedConfig) return;

        setIsSubmitting(true);
        try {
            const payload = transformToPayload(parsedConfig);
            const scenario = await trainingScenariosApi.create(payload);

            toast({
                title: "Dataset config created",
                description: "Starting ingestion...",
            });

            await trainingScenariosApi.startIngestion(scenario.id);
            router.push(`/scenarios/${scenario.id}`);
        } catch (error) {
            console.error("Failed to create", error);
            toast({
                title: "Creation failed",
                description: "Failed to create from YAML. Check console for details.",
                variant: "destructive",
            });
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target?.result as string;
            setYamlContent(content);
            setIsValid(false);
            setErrors([]);
            setParseError(null);
        };
        reader.readAsText(file);
    };

    const handleLoadSample = () => {
        setYamlContent(SAMPLE_YAML);
        setIsValid(false);
        setErrors([]);
        setParseError(null);
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => router.push("/scenarios")}
                    className="gap-2"
                >
                    <ChevronLeft className="h-4 w-4" />
                    Back to Datasets
                </Button>
            </div>

            <div className="flex items-center gap-3">
                <FileCode className="h-8 w-8 text-purple-500" />
                <div>
                    <h1 className="text-2xl font-bold">Import YAML Configuration</h1>
                    <p className="text-sm text-muted-foreground">
                        Paste or upload a YAML file to create a dataset configuration
                    </p>
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
                {/* Editor */}
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle>YAML Editor</CardTitle>
                                <CardDescription>Paste your configuration below</CardDescription>
                            </div>
                            <div className="flex gap-2">
                                <Button variant="outline" size="sm" onClick={handleLoadSample}>
                                    <Copy className="h-4 w-4 mr-1" />
                                    Sample
                                </Button>
                                <label>
                                    <input
                                        type="file"
                                        accept=".yaml,.yml"
                                        onChange={handleFileUpload}
                                        className="hidden"
                                    />
                                    <Button variant="outline" size="sm" asChild>
                                        <span>
                                            <Upload className="h-4 w-4 mr-1" />
                                            Upload
                                        </span>
                                    </Button>
                                </label>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <textarea
                            value={yamlContent}
                            onChange={(e) => {
                                setYamlContent(e.target.value);
                                setIsValid(false);
                            }}
                            className="w-full h-96 p-4 font-mono text-sm bg-slate-950 text-slate-100 rounded-lg border resize-none focus:outline-none focus:ring-2 focus:ring-purple-500"
                            placeholder="Paste your YAML configuration here..."
                        />
                        <div className="flex justify-between mt-4">
                            <Button variant="outline" onClick={handleValidate}>
                                Validate
                            </Button>
                            <Button
                                onClick={handleSubmit}
                                disabled={!isValid || isSubmitting}
                                className="bg-emerald-600 hover:bg-emerald-700"
                            >
                                {isSubmitting ? (
                                    <>
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        Creating...
                                    </>
                                ) : (
                                    "Create & Start"
                                )}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Validation Results */}
                <Card>
                    <CardHeader>
                        <CardTitle>Validation Results</CardTitle>
                        <CardDescription>
                            Check your configuration before submitting
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {parseError && (
                            <Alert variant="destructive">
                                <AlertTriangle className="h-4 w-4" />
                                <AlertTitle>Parse Error</AlertTitle>
                                <AlertDescription>{parseError}</AlertDescription>
                            </Alert>
                        )}

                        {errors.length > 0 && (
                            <Alert variant="destructive">
                                <AlertTriangle className="h-4 w-4" />
                                <AlertTitle>Validation Errors ({errors.length})</AlertTitle>
                                <AlertDescription>
                                    <ul className="list-disc list-inside mt-2 space-y-1">
                                        {errors.map((err, idx) => (
                                            <li key={idx} className="text-sm">
                                                <code className="text-xs bg-red-900/30 px-1 rounded">
                                                    {err.path}
                                                </code>
                                                : {err.message}
                                            </li>
                                        ))}
                                    </ul>
                                </AlertDescription>
                            </Alert>
                        )}

                        {isValid && (
                            <Alert className="border-green-500 bg-green-500/10">
                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                <AlertTitle className="text-green-500">Valid Configuration</AlertTitle>
                                <AlertDescription className="text-green-400">
                                    Your YAML configuration is valid and ready to submit.
                                </AlertDescription>
                            </Alert>
                        )}

                        {parsedConfig && !parseError && (
                            <div className="space-y-3 pt-4 border-t">
                                <h4 className="font-medium">Parsed Configuration</h4>
                                <div className="text-sm space-y-2">
                                    <div>
                                        <span className="text-muted-foreground">Name:</span>{" "}
                                        {parsedConfig.scenario?.name || "—"}
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground">Strategy:</span>{" "}
                                        {parsedConfig.splitting?.strategy || "—"}
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground">Features:</span>{" "}
                                        {parsedConfig.features?.dag_features?.length || 0} groups
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground">Output:</span>{" "}
                                        {parsedConfig.output?.format || "parquet"}
                                    </div>
                                </div>
                            </div>
                        )}

                        {!parseError && !isValid && errors.length === 0 && !yamlContent && (
                            <div className="text-center py-8 text-muted-foreground">
                                <FileCode className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                <p>Paste YAML content and click Validate</p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
