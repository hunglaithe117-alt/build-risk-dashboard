"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import type { DatasetRecord } from "@/types";
import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Edit,
    ExternalLink,
    FileText,
    GitBranch,
    Github,
    MapPin,
    Settings,
    Shield,
    XCircle,
    Zap,
} from "lucide-react";

interface ConfigurationTabProps {
    dataset: DatasetRecord;
    onEditMapping?: () => void;
    onEditSources?: () => void;
    onEditFeatures?: () => void;
}

type FeatureCategory = "git" | "github" | "build_log" | "sonar" | "trivy" | "repo" | "other";

const CATEGORY_CONFIG: Record<FeatureCategory, { label: string; icon: React.ElementType; color: string }> = {
    git: { label: "Git", icon: GitBranch, color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
    github: { label: "GitHub", icon: Github, color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" },
    build_log: { label: "Build Log", icon: FileText, color: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" },
    sonar: { label: "SonarQube", icon: Shield, color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" },
    trivy: { label: "Trivy", icon: Shield, color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" },
    repo: { label: "Repository", icon: Settings, color: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    other: { label: "Other", icon: Zap, color: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
};

function categorizeFeature(name: string): FeatureCategory {
    if (name.startsWith("git_")) return "git";
    if (name.startsWith("gh_")) return "github";
    if (name.startsWith("tr_log_")) return "build_log";
    if (name.startsWith("tr_")) return "repo";
    if (name.startsWith("sonar_")) return "sonar";
    if (name.startsWith("trivy_")) return "trivy";
    return "other";
}

// Data source configuration
const DATA_SOURCES = [
    { id: "git", name: "Git Repository", icon: GitBranch },
    { id: "build_log", name: "Build Logs", icon: FileText },
    { id: "github_api", name: "GitHub API", icon: Github },
    { id: "sonarqube", name: "SonarQube", icon: Shield },
    { id: "trivy", name: "Trivy", icon: Shield },
];

export function ConfigurationTab({
    dataset,
    onEditMapping,
    onEditSources,
    onEditFeatures,
}: ConfigurationTabProps) {
    const [showAllFeatures, setShowAllFeatures] = useState(false);

    const hasMapping = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );
    const features = dataset.selected_features || [];

    // Group features by category for summary
    const groupedFeatures = features.reduce((acc, feature) => {
        const category = categorizeFeature(feature);
        if (!acc[category]) acc[category] = [];
        acc[category].push(feature);
        return acc;
    }, {} as Record<FeatureCategory, string[]>);

    // Get unique repos from preview data
    const repoField = dataset.mapped_fields?.repo_name || "";
    const uniqueRepos = Array.from(
        new Set(
            dataset.preview
                ?.map(row => row[repoField] as string)
                .filter(Boolean) || []
        )
    ).slice(0, 10);

    // Determine which sources are enabled based on selected features
    const enabledSources = new Set<string>();
    features.forEach(f => {
        if (f.startsWith("git_")) enabledSources.add("git");
        if (f.startsWith("gh_")) enabledSources.add("github_api");
        if (f.startsWith("tr_log_")) enabledSources.add("build_log");
        if (f.startsWith("sonar_")) enabledSources.add("sonarqube");
        if (f.startsWith("trivy_")) enabledSources.add("trivy");
    });

    return (
        <div className="space-y-6">
            {/* Column Mapping */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <MapPin className="h-5 w-5" />
                                Column Mapping
                            </CardTitle>
                            <CardDescription>
                                Required field mappings for enrichment
                            </CardDescription>
                        </div>
                        {onEditMapping && (
                            <Button variant="outline" size="sm" onClick={onEditMapping}>
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                            </Button>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-3 md:grid-cols-2">
                        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800">
                            <span className="text-sm text-muted-foreground">Build ID</span>
                            <div className="flex items-center gap-2">
                                {dataset.mapped_fields?.build_id ? (
                                    <>
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        <Badge variant="secondary" className="font-mono">
                                            {dataset.mapped_fields.build_id}
                                        </Badge>
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="h-4 w-4 text-amber-500" />
                                        <span className="text-amber-600">Not mapped</span>
                                    </>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800">
                            <span className="text-sm text-muted-foreground">Repo Name</span>
                            <div className="flex items-center gap-2">
                                {dataset.mapped_fields?.repo_name ? (
                                    <>
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        <Badge variant="secondary" className="font-mono">
                                            {dataset.mapped_fields.repo_name}
                                        </Badge>
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="h-4 w-4 text-amber-500" />
                                        <span className="text-amber-600">Not mapped</span>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Data Sources */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Settings className="h-5 w-5" />
                                Data Sources
                            </CardTitle>
                            <CardDescription>
                                Enabled sources for feature extraction
                            </CardDescription>
                        </div>
                        {onEditSources && (
                            <Button variant="outline" size="sm" onClick={onEditSources}>
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                            </Button>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-3 md:grid-cols-3">
                        {DATA_SOURCES.map(source => {
                            const isEnabled = enabledSources.has(source.id);
                            const Icon = source.icon;
                            return (
                                <div
                                    key={source.id}
                                    className={`flex items-center gap-3 rounded-lg border p-3 ${isEnabled
                                            ? "border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-900/20"
                                            : "border-slate-200 bg-slate-50/50 dark:border-slate-700 dark:bg-slate-800/50"
                                        }`}
                                >
                                    <div className={`rounded-lg p-2 ${isEnabled ? "bg-green-100 text-green-600" : "bg-slate-100 text-slate-400"}`}>
                                        <Icon className="h-4 w-4" />
                                    </div>
                                    <div>
                                        <p className={`font-medium ${isEnabled ? "" : "text-muted-foreground"}`}>
                                            {source.name}
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            {isEnabled ? "Enabled" : "Disabled"}
                                        </p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </CardContent>
            </Card>

            {/* Selected Features */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Zap className="h-5 w-5 text-amber-500" />
                                Selected Features ({features.length})
                            </CardTitle>
                            <CardDescription>
                                Features to extract from builds
                            </CardDescription>
                        </div>
                        {onEditFeatures && (
                            <Button variant="outline" size="sm" onClick={onEditFeatures}>
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                            </Button>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    {features.length > 0 ? (
                        <>
                            {/* Category summary badges */}
                            <div className="mb-4 flex flex-wrap gap-2">
                                {Object.entries(groupedFeatures).map(([category, categoryFeatures]) => {
                                    const config = CATEGORY_CONFIG[category as FeatureCategory];
                                    return (
                                        <Badge key={category} className={config.color}>
                                            {config.label}: {categoryFeatures.length}
                                        </Badge>
                                    );
                                })}
                            </div>

                            {/* Feature badges */}
                            <div className="flex flex-wrap gap-2">
                                {(showAllFeatures ? features : features.slice(0, 15)).map(feature => (
                                    <Badge key={feature} variant="secondary" className="font-mono text-xs">
                                        {feature}
                                    </Badge>
                                ))}
                                {features.length > 15 && !showAllFeatures && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setShowAllFeatures(true)}
                                        className="h-6 text-xs"
                                    >
                                        +{features.length - 15} more
                                    </Button>
                                )}
                                {showAllFeatures && features.length > 15 && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setShowAllFeatures(false)}
                                        className="h-6 text-xs"
                                    >
                                        Show less
                                    </Button>
                                )}
                            </div>
                        </>
                    ) : (
                        <p className="py-4 text-center text-muted-foreground">
                            No features selected yet.
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Repositories */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Github className="h-5 w-5" />
                        Repositories ({uniqueRepos.length})
                    </CardTitle>
                    <CardDescription>
                        Unique repositories from this dataset
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {uniqueRepos.length > 0 ? (
                        <div className="space-y-2">
                            {uniqueRepos.map(repo => (
                                <div
                                    key={repo}
                                    className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-2 dark:bg-slate-800"
                                >
                                    <div className="flex items-center gap-3">
                                        <Github className="h-4 w-4 text-muted-foreground" />
                                        <span className="font-mono text-sm">{repo}</span>
                                    </div>
                                    <a
                                        href={`https://github.com/${repo}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-muted-foreground hover:text-foreground"
                                    >
                                        <ExternalLink className="h-4 w-4" />
                                    </a>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="py-4 text-center text-muted-foreground">
                            No repositories found. Please ensure column mapping is configured.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
