"use client";

import { memo, useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    AlertCircle,
    Check,
    ChevronDown,
    ChevronRight,
    FileText,
    GitBranch,
    Search,
    Settings,
    Shield,
    Github,
    Database,
    Box,
} from "lucide-react";
import type { NodeInfo } from "../types";

interface ListViewProps {
    nodes: NodeInfo[];
    selectedFeatures: Set<string>;
    expandedNodes: Set<string>;
    onToggleFeature: (featureName: string) => void;
    onToggleNode: (nodeName: string, features: string[]) => void;
    onToggleNodeExpand: (nodeName: string) => void;
    searchQuery: string;
    onSearchChange: (query: string) => void;
    isLoading?: boolean;
}

const groupIcons: Record<string, typeof GitBranch> = {
    git: GitBranch,
    github: Github,
    build_log: FileText,
    sonar: Settings,
    security: Shield,
    repo: Database,
};

export const ListView = memo(function ListView({
    nodes,
    selectedFeatures,
    expandedNodes,
    onToggleFeature,
    onToggleNode,
    onToggleNodeExpand,
    searchQuery,
    onSearchChange,
    isLoading = false,
}: ListViewProps) {
    if (isLoading) {
        return (
            <div className="flex h-[400px] items-center justify-center">
                <div className="text-muted-foreground">Loading features...</div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    placeholder="Search features..."
                    value={searchQuery}
                    onChange={(e) => onSearchChange(e.target.value)}
                    className="pl-10"
                />
            </div>

            {/* Nodes */}
            <div className="max-h-[400px] space-y-3 overflow-y-auto pr-2">
                {nodes.map((node) => (
                    <NodeCard
                        key={node.name}
                        node={node}
                        selectedFeatures={selectedFeatures}
                        isExpanded={expandedNodes.has(node.name)}
                        onToggleNode={() =>
                            onToggleNode(
                                node.name,
                                node.features.map((f) => f.name)
                            )
                        }
                        onToggleExpand={() => onToggleNodeExpand(node.name)}
                        onToggleFeature={onToggleFeature}
                    />
                ))}
            </div>

            {nodes.length === 0 && (
                <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                    No features match your search
                </div>
            )}
        </div>
    );
});

interface NodeCardProps {
    node: NodeInfo;
    selectedFeatures: Set<string>;
    isExpanded: boolean;
    onToggleNode: () => void;
    onToggleExpand: () => void;
    onToggleFeature: (featureName: string) => void;
}

function NodeCard({
    node,
    selectedFeatures,
    isExpanded,
    onToggleNode,
    onToggleExpand,
    onToggleFeature,
}: NodeCardProps) {
    const Icon = groupIcons[node.group] || Box;

    const selectedCount = node.features.filter((f) =>
        selectedFeatures.has(f.name)
    ).length;
    const allSelected = selectedCount === node.features.length && node.features.length > 0;
    const someSelected = selectedCount > 0 && selectedCount < node.features.length;

    return (
        <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
            <div
                className={`rounded-lg border ${node.is_configured
                    ? "border-slate-200 dark:border-slate-700"
                    : "border-dashed border-slate-300 opacity-75 dark:border-slate-600"
                    }`}
            >
                {/* Node Header */}
                <CollapsibleTrigger asChild>
                    <div
                        className={`flex cursor-pointer items-center justify-between p-3 ${node.is_configured ? "hover:bg-slate-50 dark:hover:bg-slate-800/50" : ""
                            }`}
                    >
                        <div className="flex items-center gap-3">
                            <div
                                className={`rounded-lg p-2 ${node.is_configured
                                    ? "bg-slate-100 dark:bg-slate-800"
                                    : "bg-slate-50 dark:bg-slate-900"
                                    }`}
                            >
                                <Icon
                                    className={`h-4 w-4 ${node.is_configured
                                        ? "text-slate-600 dark:text-slate-400"
                                        : "text-slate-400"
                                        }`}
                                />
                            </div>
                            <div>
                                <div className="flex items-center gap-2">
                                    <Checkbox
                                        checked={allSelected}
                                        className={someSelected ? "data-[state=checked]:bg-yellow-500" : ""}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onToggleNode();
                                        }}
                                    />
                                    <span className="font-medium">{node.display_name}</span>
                                    {node.is_configured ? (
                                        <Badge variant="outline" className="text-xs border-green-500 text-green-600">
                                            <Check className="mr-1 h-2.5 w-2.5" />
                                            Available
                                        </Badge>
                                    ) : (
                                        <Badge variant="outline" className="text-xs">
                                            <AlertCircle className="mr-1 h-2.5 w-2.5" />
                                            Not Configured
                                        </Badge>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground">{node.description}</p>
                            </div>
                        </div>

                        <div className="flex items-center gap-2">
                            <Badge
                                variant={allSelected ? "default" : someSelected ? "secondary" : "outline"}
                                className="text-xs"
                            >
                                {selectedCount}/{node.feature_count}
                            </Badge>
                            {isExpanded ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            )}
                        </div>
                    </div>
                </CollapsibleTrigger>

                {/* Features */}
                <CollapsibleContent>
                    {node.is_configured && (
                        <div className="border-t p-3 pt-2">
                            <div className="space-y-1">
                                {node.features.map((feature) => (
                                    <label
                                        key={feature.name}
                                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-700"
                                    >
                                        <Checkbox
                                            checked={selectedFeatures.has(feature.name)}
                                            onCheckedChange={() => onToggleFeature(feature.name)}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <span className="text-sm font-mono">{feature.name}</span>
                                            <p className="truncate text-xs text-muted-foreground">
                                                {feature.description}
                                            </p>
                                        </div>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}
                </CollapsibleContent>
            </div>
        </Collapsible>
    );
}
