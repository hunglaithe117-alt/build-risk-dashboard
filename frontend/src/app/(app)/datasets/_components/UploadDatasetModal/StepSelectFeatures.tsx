"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { Loader2, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { DatasetTemplateRecord } from "@/types";
import type { StepSelectFeaturesProps } from "./types";
import { TemplateSelector } from "./TemplateSelector";
import { FeatureDAGVisualization } from "@/app/(app)/admin/repos/_components/FeatureDAGVisualization";
import { SelectedFeaturesPanel } from "@/app/(app)/admin/repos/_components/SelectedFeaturesPanel";
import { ExtractionPlanTimeline } from "@/app/(app)/admin/repos/_components/ExtractionPlanTimeline";

export function StepSelectFeatures({
    features,
    templates,
    selectedFeatures,
    featureSearch,
    featuresLoading,
    collapsedCategories,
    onFeatureSearchChange,
    onToggleFeature,
    onToggleCategory,
    onApplyTemplate,
    onClearAll,
    dagData,
    dagLoading,
    onLoadDAG,
    onSetSelectedFeatures,
}: StepSelectFeaturesProps) {
    const [selectedTemplate, setSelectedTemplate] = useState<DatasetTemplateRecord | null>(null);
    const [viewMode, setViewMode] = useState<"list" | "dag">("dag");

    // Load DAG when switching to DAG view
    useEffect(() => {
        if (viewMode === "dag" && !dagData && !dagLoading) {
            onLoadDAG();
        }
    }, [viewMode, dagData, dagLoading, onLoadDAG]);

    const filteredFeatures = useMemo(() => {
        if (!featureSearch) return features;
        const lower = featureSearch.toLowerCase();
        return features.map(group => ({
            ...group,
            features: group.features.filter(f =>
                f.name.toLowerCase().includes(lower) ||
                f.display_name.toLowerCase().includes(lower)
            ),
        })).filter(g => g.features.length > 0);
    }, [features, featureSearch]);

    // Convert Set to Array for DAG component
    const selectedFeaturesArray = useMemo(() => Array.from(selectedFeatures), [selectedFeatures]);

    // Create feature labels mapping (feature name -> display name)
    const featureLabels = useMemo(() => {
        const labels: Record<string, string> = {};
        features.forEach(group => {
            group.features.forEach(feat => {
                labels[feat.name] = feat.display_name || feat.name;
            });
        });
        return labels;
    }, [features]);

    // Create feature descriptions mapping (feature name -> description)
    const featureDescriptions = useMemo(() => {
        const descriptions: Record<string, string> = {};
        features.forEach(group => {
            group.features.forEach(feat => {
                if (feat.description) {
                    descriptions[feat.name] = feat.description;
                }
            });
        });
        return descriptions;
    }, [features]);

    // Get node labels from DAG data
    const nodeLabels = useMemo(() => {
        const labels: Record<string, string> = {};
        dagData?.nodes.forEach((node) => {
            labels[node.id] = node.label;
        });
        return labels;
    }, [dagData]);

    // Get active (selected) nodes based on selected features
    const activeNodes = useMemo((): Set<string> => {
        if (!dagData) return new Set();
        const selectedSet = selectedFeatures;
        const active = new Set<string>();
        dagData.nodes.forEach((node) => {
            // Check if ANY of the feature names in the node are selected
            if (node.features.some((f) => selectedSet.has(f))) {
                active.add(node.id);
            }
        });
        return active;
    }, [dagData, selectedFeatures]);

    // Handle removing a single feature
    const handleRemoveFeature = useCallback((featureName: string) => {
        onToggleFeature(featureName);
    }, [onToggleFeature]);

    if (featuresLoading) {
        return (
            <div className="flex flex-col items-center justify-center gap-4 py-12">
                <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
                <p className="text-muted-foreground">Loading features...</p>
            </div>
        );
    }

    return (
        <>
            {/* Header with count and view toggle */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-semibold">Select Features</h3>
                    <p className="text-sm text-muted-foreground">
                        Choose features to extract from your dataset builds
                    </p>
                    <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                        ℹ️ <code className="bg-blue-50 dark:bg-blue-900/30 px-1 rounded">tr_build_id</code> and <code className="bg-blue-50 dark:bg-blue-900/30 px-1 rounded">gh_project_name</code> are always included automatically
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="text-sm">
                        {selectedFeatures.size} selected
                    </Badge>
                    {/* View Mode Toggle */}
                    <div className="flex items-center gap-1 rounded-lg border p-1 bg-slate-50 dark:bg-slate-800">
                        <button
                            type="button"
                            onClick={() => setViewMode("dag")}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === "dag"
                                ? "bg-blue-500 text-white shadow-sm"
                                : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                                }`}
                        >
                            <span className="flex items-center gap-1.5">
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                                Graph
                            </span>
                        </button>
                        <button
                            type="button"
                            onClick={() => setViewMode("list")}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === "list"
                                ? "bg-blue-500 text-white shadow-sm"
                                : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
                                }`}
                        >
                            <span className="flex items-center gap-1.5">
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                                </svg>
                                List
                            </span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Template Selection */}
            <TemplateSelector
                templates={templates}
                selectedTemplate={selectedTemplate}
                onSelectTemplate={setSelectedTemplate}
                onApplyTemplate={() => {
                    if (selectedTemplate) {
                        onApplyTemplate(selectedTemplate);
                    }
                }}
            />

            {/* DAG View */}
            {viewMode === "dag" && (
                <div className="space-y-4">
                    <FeatureDAGVisualization
                        dagData={dagData}
                        selectedFeatures={selectedFeaturesArray}
                        onFeaturesChange={onSetSelectedFeatures}
                        isLoading={dagLoading}
                        className="h-[300px]"
                    />

                    {/* Selected Features Panel */}
                    <SelectedFeaturesPanel
                        selectedFeatures={selectedFeaturesArray}
                        featureLabels={featureLabels}
                        featureDescriptions={featureDescriptions}
                        onRemove={handleRemoveFeature}
                        onClear={onClearAll}
                    />

                    {/* Extraction Plan Timeline */}
                    {dagData && (
                        <ExtractionPlanTimeline
                            executionLevels={dagData.execution_levels}
                            nodeLabels={nodeLabels}
                            activeNodes={activeNodes}
                        />
                    )}
                </div>
            )}

            {/* List View */}
            {viewMode === "list" && (
                <>
                    {/* Search and Clear */}
                    <div className="flex items-center gap-2">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                placeholder="Search features..."
                                value={featureSearch}
                                onChange={(e) => onFeatureSearchChange(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={onClearAll}
                            className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                            disabled={selectedFeatures.size === 0}
                        >
                            <X className="h-4 w-4 mr-1" />
                            Clear All
                        </Button>
                    </div>

                    {/* Feature Categories - Collapsible */}
                    <ScrollArea className="h-[320px]">
                        <div className="space-y-3">
                            {filteredFeatures.length === 0 ? (
                                <div className="text-sm text-muted-foreground text-center py-8">
                                    No features match your search.
                                </div>
                            ) : (
                                filteredFeatures.map((group) => {
                                    const isCollapsed = collapsedCategories.has(group.category);
                                    const selectedInGroup = group.features.filter(f => selectedFeatures.has(f.name)).length;

                                    return (
                                        <div key={group.category} className="space-y-2">
                                            <div className="flex items-center justify-between">
                                                <div className="text-xs uppercase text-muted-foreground font-semibold">
                                                    {group.display_name || group.category.replace(/_/g, " ")}
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Badge variant={selectedInGroup > 0 ? "default" : "secondary"}>
                                                        {selectedInGroup}/{group.features.length}
                                                    </Badge>
                                                    <Button
                                                        type="button"
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => onToggleCategory(group.category)}
                                                        className="h-7 px-2 text-xs"
                                                    >
                                                        {isCollapsed ? "Expand" : "Collapse"}
                                                    </Button>
                                                </div>
                                            </div>
                                            {!isCollapsed && (
                                                <div className="grid gap-2 sm:grid-cols-2">
                                                    {group.features.map((feat) => (
                                                        <label
                                                            key={feat.name}
                                                            className={cn(
                                                                "flex items-start gap-2 rounded-lg border p-2 cursor-pointer transition",
                                                                selectedFeatures.has(feat.name)
                                                                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                                                                    : "border-transparent hover:border-slate-200 dark:hover:border-slate-800"
                                                            )}
                                                        >
                                                            <Checkbox
                                                                checked={selectedFeatures.has(feat.name)}
                                                                onCheckedChange={() => onToggleFeature(feat.name)}
                                                                className="mt-0.5"
                                                            />
                                                            <div className="space-y-1 min-w-0">
                                                                <div className="flex items-center gap-2">
                                                                    <span className="text-sm font-medium">{feat.display_name || feat.name}</span>
                                                                    <Badge variant="outline" className="text-[10px]">{feat.data_type}</Badge>
                                                                </div>
                                                                {feat.description && (
                                                                    <p className="text-xs text-muted-foreground line-clamp-2">{feat.description}</p>
                                                                )}
                                                            </div>
                                                        </label>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </ScrollArea>
                </>
            )}
        </>
    );
}
