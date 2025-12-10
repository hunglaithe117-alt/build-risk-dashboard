"use client";

import {
    CheckCircle2,
    Clock,
    Database,
    GitBranch,
    FileText,
    Github,
    ShieldCheck,
    ShieldAlert,
    AlertTriangle,
    Info,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import type { CSVPreview, RepoConfig, FeatureCategoryGroup } from "./types";

interface StepExtractionPlanProps {
    preview: CSVPreview | null;
    uniqueRepos: string[];
    repoConfigs: Record<string, RepoConfig>;
    enabledSources: Set<string>;
    selectedFeatures: Set<string>;
    features: FeatureCategoryGroup[];
}

// Map source types to display info
const SOURCE_INFO: Record<string, { name: string; icon: React.ReactNode; color: string }> = {
    git: { name: "Git Repository", icon: <GitBranch className="h-4 w-4" />, color: "text-orange-600" },
    build_log: { name: "Build Logs", icon: <FileText className="h-4 w-4" />, color: "text-blue-600" },
    github_api: { name: "GitHub API", icon: <Github className="h-4 w-4" />, color: "text-slate-600" },
    sonarqube: { name: "SonarQube", icon: <ShieldCheck className="h-4 w-4" />, color: "text-cyan-600" },
    trivy: { name: "Trivy Scanner", icon: <ShieldAlert className="h-4 w-4" />, color: "text-purple-600" },
};

export function StepExtractionPlan({
    preview,
    uniqueRepos,
    repoConfigs,
    enabledSources,
    selectedFeatures,
    features,
}: StepExtractionPlanProps) {
    // Estimate processing time based on data size and sources
    const estimateProcessingTime = (): string => {
        const rowCount = preview?.totalRows || 0;
        const sourceCount = enabledSources.size;
        const featureCount = selectedFeatures.size;

        // Rough estimate: base 5s + 0.5s per row + 10s per source + 0.1s per feature
        const baseTime = 5;
        const rowTime = rowCount * 0.5;
        const sourceTime = sourceCount * 10;
        const featureTime = featureCount * 0.1;
        const totalSeconds = baseTime + rowTime + sourceTime + featureTime;

        if (totalSeconds < 60) return "< 1 minute";
        if (totalSeconds < 300) return `${Math.ceil(totalSeconds / 60)} minutes`;
        return `${Math.ceil(totalSeconds / 60)} minutes`;
    };

    // Group selected features by category
    const getFeaturesByCategory = (): Record<string, string[]> => {
        const result: Record<string, string[]> = {};
        features.forEach((group) => {
            const selected = group.features
                .filter((f) => selectedFeatures.has(f.name))
                .map((f) => f.display_name || f.name);
            if (selected.length > 0) {
                result[group.category] = selected;
            }
        });
        return result;
    };

    const featuresByCategory = getFeaturesByCategory();
    const enabledSourcesList = Array.from(enabledSources);

    return (
        <div className="space-y-6">
            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-4">
                <Card>
                    <CardContent className="pt-4">
                        <div className="flex items-center gap-3">
                            <div className="rounded-lg bg-blue-100 p-2 text-blue-600 dark:bg-blue-900/50">
                                <Database className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold">{preview?.totalRows || 0}</p>
                                <p className="text-xs text-muted-foreground">Builds to process</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent className="pt-4">
                        <div className="flex items-center gap-3">
                            <div className="rounded-lg bg-emerald-100 p-2 text-emerald-600 dark:bg-emerald-900/50">
                                <CheckCircle2 className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold">{selectedFeatures.size}</p>
                                <p className="text-xs text-muted-foreground">Features selected</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent className="pt-4">
                        <div className="flex items-center gap-3">
                            <div className="rounded-lg bg-amber-100 p-2 text-amber-600 dark:bg-amber-900/50">
                                <Clock className="h-5 w-5" />
                            </div>
                            <div>
                                <p className="text-2xl font-bold">{estimateProcessingTime()}</p>
                                <p className="text-xs text-muted-foreground">Estimated time</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Extraction Pipeline */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Extraction Pipeline</CardTitle>
                    <CardDescription>Data sources that will be used</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-2 flex-wrap">
                        {enabledSourcesList.map((sourceType, index) => {
                            const info = SOURCE_INFO[sourceType];
                            return (
                                <div key={sourceType} className="flex items-center gap-2">
                                    <div className="flex items-center gap-2 rounded-lg border px-3 py-2 bg-slate-50 dark:bg-slate-900">
                                        <span className={info?.color || "text-slate-600"}>
                                            {info?.icon || <Database className="h-4 w-4" />}
                                        </span>
                                        <span className="text-sm font-medium">
                                            {info?.name || sourceType}
                                        </span>
                                    </div>
                                    {index < enabledSourcesList.length - 1 && (
                                        <span className="text-muted-foreground">→</span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </CardContent>
            </Card>

            {/* Repositories */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Repositories ({uniqueRepos.length})</CardTitle>
                    <CardDescription>Repositories from your dataset</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-2">
                        {uniqueRepos.slice(0, 10).map((repo) => (
                            <Badge key={repo} variant="secondary" className="text-xs">
                                {repo}
                            </Badge>
                        ))}
                        {uniqueRepos.length > 10 && (
                            <Badge variant="outline" className="text-xs">
                                +{uniqueRepos.length - 10} more
                            </Badge>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Selected Features */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Selected Features ({selectedFeatures.size})</CardTitle>
                    <CardDescription>Features that will be extracted</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {Object.entries(featuresByCategory).map(([category, featureNames]) => (
                            <div key={category}>
                                <p className="text-xs font-medium text-muted-foreground uppercase mb-1">
                                    {category}
                                </p>
                                <div className="flex flex-wrap gap-1">
                                    {featureNames.slice(0, 5).map((name) => (
                                        <Badge key={name} variant="outline" className="text-xs">
                                            {name}
                                        </Badge>
                                    ))}
                                    {featureNames.length > 5 && (
                                        <Badge variant="secondary" className="text-xs">
                                            +{featureNames.length - 5}
                                        </Badge>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* Warnings/Notes */}
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
                <div className="flex items-start gap-3">
                    <Info className="h-5 w-5 text-blue-600 mt-0.5" />
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                        <p className="font-medium mb-1">Before you continue:</p>
                        <ul className="list-disc list-inside space-y-1 text-xs">
                            <li>Repositories not in the system will be auto-imported</li>
                            <li>Build logs will be fetched from GitHub Actions</li>
                            <li>Processing runs in the background - you can close this modal</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
}
