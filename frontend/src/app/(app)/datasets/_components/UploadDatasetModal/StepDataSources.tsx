"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Check,
    ChevronDown,
    ChevronRight,
    GitBranch,
    FileText,
    Github,
    ShieldCheck,
    ShieldAlert,
    Loader2,
    Settings,
    AlertTriangle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { dataSourcesApi, DataSourceInfo } from "@/lib/api";

interface StepDataSourcesProps {
    enabledSources: Set<string>;
    onToggleSource: (sourceType: string) => void;
}

// Map source types to icons
const SOURCE_ICONS: Record<string, React.ReactNode> = {
    git: <GitBranch className="h-5 w-5" />,
    build_log: <FileText className="h-5 w-5" />,
    github_api: <Github className="h-5 w-5" />,
    sonarqube: <ShieldCheck className="h-5 w-5" />,
    trivy: <ShieldAlert className="h-5 w-5" />,
};

// Group sources by category
const SOURCE_CATEGORIES = [
    {
        id: "core",
        name: "Core Data Sources",
        description: "Essential sources for feature extraction",
        sources: ["git", "build_log", "github_api"],
    },
    {
        id: "quality",
        name: "Code Quality",
        description: "Code quality and metrics collection",
        sources: ["sonarqube"],
    },
    {
        id: "security",
        name: "Security Scanning",
        description: "Vulnerability and container scanning",
        sources: ["trivy"],
    },
];

export function StepDataSources({
    enabledSources,
    onToggleSource,
}: StepDataSourcesProps) {
    const [dataSources, setDataSources] = useState<DataSourceInfo[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
        new Set(["core", "quality", "security"])
    );

    // Fetch available data sources
    const fetchDataSources = useCallback(async () => {
        try {
            setLoading(true);
            const response = await dataSourcesApi.list();
            setDataSources(response.sources);
            setError(null);
        } catch (err) {
            setError("Failed to load data sources");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDataSources();
    }, [fetchDataSources]);

    const toggleCategory = (categoryId: string) => {
        setExpandedCategories((prev) => {
            const next = new Set(prev);
            if (next.has(categoryId)) {
                next.delete(categoryId);
            } else {
                next.add(categoryId);
            }
            return next;
        });
    };

    const getSourceInfo = (sourceType: string): DataSourceInfo | undefined => {
        return dataSources.find((s) => s.source_type === sourceType);
    };

    const getTotalEnabledFeatures = (): number => {
        return dataSources
            .filter((s) => enabledSources.has(s.source_type))
            .reduce((sum, s) => sum + s.features_count, 0);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                {error}
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary header */}
            <div className="flex items-center justify-between rounded-lg bg-slate-50 p-4 dark:bg-slate-900">
                <div>
                    <h3 className="font-medium">Configure Data Sources</h3>
                    <p className="text-sm text-muted-foreground">
                        Enable data sources to extract features from your build data
                    </p>
                </div>
                <div className="text-right">
                    <p className="text-2xl font-bold">{enabledSources.size}</p>
                    <p className="text-xs text-muted-foreground">
                        sources enabled • ~{getTotalEnabledFeatures()} features
                    </p>
                </div>
            </div>

            {/* Data source categories */}
            <div className="space-y-4">
                {SOURCE_CATEGORIES.map((category) => {
                    const isExpanded = expandedCategories.has(category.id);
                    const categorySources = category.sources
                        .map(getSourceInfo)
                        .filter(Boolean) as DataSourceInfo[];
                    const enabledCount = categorySources.filter((s) =>
                        enabledSources.has(s.source_type)
                    ).length;

                    return (
                        <Card key={category.id} className="overflow-hidden">
                            <CardHeader
                                className="cursor-pointer py-3"
                                onClick={() => toggleCategory(category.id)}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        {isExpanded ? (
                                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                        ) : (
                                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                        )}
                                        <div>
                                            <CardTitle className="text-base">
                                                {category.name}
                                            </CardTitle>
                                            <CardDescription className="text-xs">
                                                {category.description}
                                            </CardDescription>
                                        </div>
                                    </div>
                                    <Badge variant="secondary">
                                        {enabledCount}/{categorySources.length} enabled
                                    </Badge>
                                </div>
                            </CardHeader>

                            {isExpanded && (
                                <CardContent className="border-t pt-4">
                                    <div className="space-y-3">
                                        {categorySources.map((source) => {
                                            const isEnabled = enabledSources.has(
                                                source.source_type
                                            );
                                            const canEnable =
                                                source.is_available ||
                                                !source.requires_config;

                                            return (
                                                <div
                                                    key={source.source_type}
                                                    className={`flex items-center justify-between rounded-lg border p-4 transition-colors ${isEnabled
                                                        ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-900/20"
                                                        : "border-slate-200 dark:border-slate-800"
                                                        } ${!canEnable
                                                            ? "opacity-60"
                                                            : ""
                                                        }`}
                                                >
                                                    <div className="flex items-center gap-4">
                                                        <div
                                                            className={`rounded-lg p-2 ${isEnabled
                                                                ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-900 dark:text-emerald-400"
                                                                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                                                                }`}
                                                        >
                                                            {SOURCE_ICONS[
                                                                source.source_type
                                                            ] || (
                                                                    <Settings className="h-5 w-5" />
                                                                )}
                                                        </div>
                                                        <div>
                                                            <div className="flex items-center gap-2">
                                                                <h4 className="font-medium">
                                                                    {source.display_name}
                                                                </h4>
                                                                {!source.is_configured &&
                                                                    source.requires_config && (
                                                                        <Badge
                                                                            variant="outline"
                                                                            className="border-amber-500 text-amber-600 text-xs"
                                                                        >
                                                                            <AlertTriangle className="mr-1 h-3 w-3" />
                                                                            Not configured
                                                                        </Badge>
                                                                    )}
                                                            </div>
                                                            <p className="text-sm text-muted-foreground">
                                                                {source.description}
                                                            </p>
                                                            <p className="mt-1 text-xs text-muted-foreground">
                                                                {source.features_count}{" "}
                                                                features available
                                                            </p>
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-3">
                                                        {source.requires_config &&
                                                            !source.is_configured && (
                                                                <span className="text-xs text-muted-foreground">
                                                                    Configure in .env
                                                                </span>
                                                            )}
                                                        <Switch
                                                            checked={isEnabled}
                                                            onCheckedChange={() =>
                                                                onToggleSource(
                                                                    source.source_type
                                                                )
                                                            }
                                                            disabled={
                                                                !canEnable &&
                                                                !isEnabled
                                                            }
                                                        />
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    );
                })}
            </div>
        </div>
    );
}
