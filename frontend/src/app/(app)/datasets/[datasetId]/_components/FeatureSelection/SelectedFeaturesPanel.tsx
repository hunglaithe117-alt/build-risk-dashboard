"use client";

import { memo, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    ChevronDown,
    ChevronRight,
    Copy,
    FileText,
    GitBranch,
    Github,
    Trash2,
    Database,
    Settings,
    Shield,
    X,
} from "lucide-react";

interface FeatureDefinition {
    name: string;
    display_name: string;
    description: string;
}

interface SelectedFeaturesPanelProps {
    selectedFeatures: Set<string>;
    allFeatures: FeatureDefinition[];
    onRemoveFeature: (featureName: string) => void;
    onClearAll: () => void;
    rowCount: number;
}

const sourceIcons: Record<string, typeof GitBranch> = {
    git: GitBranch,
    github: Github,
    build_log: FileText,
    sonarqube: Settings,
    trivy: Shield,
    repo: Database,
};

const sourceDisplayNames: Record<string, string> = {
    git: "Git Repository",
    github: "GitHub API",
    build_log: "Build Logs",
    sonarqube: "SonarQube",
    trivy: "Trivy Scanner",
    repo: "Repository Metadata",
};

function getSourceFromFeature(featureName: string): string {
    if (featureName.startsWith("git_")) return "git";
    if (featureName.startsWith("gh_")) return "github";
    if (featureName.startsWith("tr_log_")) return "build_log";
    if (featureName.startsWith("tr_")) return "repo";
    if (featureName.startsWith("sonar_")) return "sonarqube";
    if (featureName.startsWith("trivy_")) return "trivy";
    return "other";
}

export const SelectedFeaturesPanel = memo(function SelectedFeaturesPanel({
    selectedFeatures,
    allFeatures,
    onRemoveFeature,
    onClearAll,
    rowCount,
}: SelectedFeaturesPanelProps) {
    const [expandedSources, setExpandedSources] = useState<Set<string>>(
        new Set(["git", "build_log"])
    );

    // Group selected features by source
    const groupedFeatures = useMemo(() => {
        const groups: Record<string, FeatureDefinition[]> = {};

        selectedFeatures.forEach((featureName) => {
            const source = getSourceFromFeature(featureName);
            if (!groups[source]) groups[source] = [];

            const featureDef = allFeatures.find((f) => f.name === featureName);
            groups[source].push(
                featureDef || {
                    name: featureName,
                    display_name: featureName,
                    description: "",
                }
            );
        });

        // Sort features within each group
        Object.values(groups).forEach((features) => {
            features.sort((a, b) => a.name.localeCompare(b.name));
        });

        return groups;
    }, [selectedFeatures, allFeatures]);

    // Copy feature names to clipboard
    const handleCopy = () => {
        const featureNames = Array.from(selectedFeatures).sort().join(",");
        navigator.clipboard.writeText(featureNames);
    };

    // Toggle source expansion
    const toggleSource = (source: string) => {
        setExpandedSources((prev) => {
            const next = new Set(prev);
            if (next.has(source)) {
                next.delete(source);
            } else {
                next.add(source);
            }
            return next;
        });
    };

    if (selectedFeatures.size === 0) {
        return (
            <Card className="border-dashed">
                <CardContent className="flex items-center justify-center py-8 text-muted-foreground">
                    No features selected. Click on extractors or features above to select them.
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border-dashed">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base">
                        Selected Features ({selectedFeatures.size})
                    </CardTitle>
                    <div className="flex gap-1">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleCopy}
                            className="h-7 gap-1 px-2"
                        >
                            <Copy className="h-3.5 w-3.5" />
                            Copy
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={onClearAll}
                            className="h-7 gap-1 px-2 text-destructive hover:text-destructive"
                        >
                            <Trash2 className="h-3.5 w-3.5" />
                            Clear
                        </Button>
                    </div>
                </div>
            </CardHeader>

            <CardContent className="max-h-[200px] space-y-2 overflow-y-auto pb-2">
                {Object.entries(groupedFeatures).map(([source, features]) => {
                    const Icon = sourceIcons[source] || Database;
                    const isExpanded = expandedSources.has(source);

                    return (
                        <Collapsible
                            key={source}
                            open={isExpanded}
                            onOpenChange={() => toggleSource(source)}
                        >
                            <CollapsibleTrigger asChild>
                                <div className="flex cursor-pointer items-center gap-2 rounded-md bg-slate-50 px-3 py-2 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700">
                                    <Icon className="h-4 w-4 text-muted-foreground" />
                                    <span className="flex-1 text-sm font-medium">
                                        {sourceDisplayNames[source] || source}
                                    </span>
                                    <Badge variant="secondary" className="text-xs">
                                        {features.length}
                                    </Badge>
                                    {isExpanded ? (
                                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                    ) : (
                                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                    )}
                                </div>
                            </CollapsibleTrigger>

                            <CollapsibleContent>
                                <div className="mt-1 space-y-0.5 pl-6">
                                    {features.map((feature) => (
                                        <div
                                            key={feature.name}
                                            className="group flex items-center justify-between rounded px-2 py-1 hover:bg-slate-50 dark:hover:bg-slate-800"
                                        >
                                            <div className="min-w-0 flex-1">
                                                <span className="font-mono text-xs">
                                                    {feature.name}
                                                </span>
                                                {feature.description && (
                                                    <span className="ml-2 text-xs text-muted-foreground">
                                                        {feature.description}
                                                    </span>
                                                )}
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => onRemoveFeature(feature.name)}
                                                className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100"
                                            >
                                                <X className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </CollapsibleContent>
                        </Collapsible>
                    );
                })}
            </CardContent>
        </Card>
    );
});
