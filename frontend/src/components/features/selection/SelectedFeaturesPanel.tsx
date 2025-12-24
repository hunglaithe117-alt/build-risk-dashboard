"use client";

import { memo, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
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
    Box,
} from "lucide-react";
import type { NodeInfo } from "../types";

// Local interface for feature display (subset of full FeatureDefinition)
interface DisplayFeature {
    name: string;
    display_name: string;
    description: string;
    node: string;
}

interface SelectedFeaturesPanelProps {
    selectedFeatures: Set<string>;
    allFeatures: DisplayFeature[];
    nodes: NodeInfo[];
    onRemoveFeature: (featureName: string) => void;
    onClearAll: () => void;
    rowCount: number;
}

const groupIcons: Record<string, typeof GitBranch> = {
    git: GitBranch,
    github: Github,
    build_log: FileText,
    sonar: Settings,
    security: Shield,
    repo: Database,
};

export const SelectedFeaturesPanel = memo(function SelectedFeaturesPanel({
    selectedFeatures,
    allFeatures,
    nodes,
    onRemoveFeature,
    onClearAll,
    rowCount,
}: SelectedFeaturesPanelProps) {
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(
        new Set(["git_commit_info", "git_diff_features", "job_metadata"])
    );

    // Build node display name map from API data
    const nodeDisplayNames = useMemo(() => {
        const map: Record<string, string> = {};
        nodes.forEach((n) => {
            map[n.name] = n.display_name;
        });
        return map;
    }, [nodes]);

    // Build node to group map
    const nodeGroups = useMemo(() => {
        const map: Record<string, string> = {};
        nodes.forEach((n) => {
            map[n.name] = n.group;
        });
        return map;
    }, [nodes]);

    // Group selected features by node (using node from feature data)
    const groupedFeatures = useMemo(() => {
        const groups: Record<string, DisplayFeature[]> = {};

        selectedFeatures.forEach((featureName) => {
            const featureDef = allFeatures.find((f) => f.name === featureName);
            const node = featureDef?.node || "other";

            if (!groups[node]) groups[node] = [];

            groups[node].push(
                featureDef || {
                    name: featureName,
                    display_name: featureName,
                    description: "",
                    node: "other",
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

    // Toggle node expansion
    const toggleNode = (nodeName: string) => {
        setExpandedNodes((prev) => {
            const next = new Set(prev);
            if (next.has(nodeName)) {
                next.delete(nodeName);
            } else {
                next.add(nodeName);
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
                {Object.entries(groupedFeatures).map(([nodeName, features]) => {
                    const group = nodeGroups[nodeName] || "other";
                    const Icon = groupIcons[group] || Box;
                    const isExpanded = expandedNodes.has(nodeName);

                    return (
                        <Collapsible
                            key={nodeName}
                            open={isExpanded}
                            onOpenChange={() => toggleNode(nodeName)}
                        >
                            <CollapsibleTrigger asChild>
                                <div className="flex cursor-pointer items-center gap-2 rounded-md bg-slate-50 px-3 py-2 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700">
                                    <Icon className="h-4 w-4 text-muted-foreground" />
                                    <span className="flex-1 text-sm font-medium">
                                        {nodeDisplayNames[nodeName] || nodeName}
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
