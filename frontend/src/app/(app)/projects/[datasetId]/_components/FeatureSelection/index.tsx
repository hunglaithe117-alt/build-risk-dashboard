"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Loader2, Sparkles, Zap } from "lucide-react";
import { useFeatureSelector } from "@/components/features";
import {
    GraphView,
    ListView,
    SelectedFeaturesPanel,
    ViewToggle,
    TemplateSelector,
} from "@/components/features/FeatureSelection";

interface FeatureSelectionCardProps {
    datasetId: string;
    rowCount: number;
    onCreateVersion: (features: string[], name?: string) => Promise<void>;
    isCreating: boolean;
    hasActiveVersion: boolean;
}

export function FeatureSelectionCard({
    datasetId,
    rowCount,
    onCreateVersion,
    isCreating,
    hasActiveVersion,
}: FeatureSelectionCardProps) {
    const [viewMode, setViewMode] = useState<"graph" | "list">("graph");
    const [versionName, setVersionName] = useState("");

    const {
        extractorNodes,
        dagData,
        allFeatures,
        loading,
        selectedFeatures,
        expandedNodes,
        searchQuery,
        toggleFeature,
        toggleNode,
        toggleNodeExpand,
        clearSelection,
        setSearchQuery,
        filteredNodes,
        applyTemplate,
    } = useFeatureSelector();

    // Handle features change from graph view (converts array to Set operations)
    const handleGraphFeaturesChange = useCallback(
        (features: string[]) => {
            const newSet = new Set(features);
            const currentSet = selectedFeatures;

            // Find what was added and what was removed
            features.forEach((f) => {
                if (!currentSet.has(f)) toggleFeature(f);
            });
            currentSet.forEach((f) => {
                if (!newSet.has(f)) toggleFeature(f);
            });
        },
        [selectedFeatures, toggleFeature]
    );

    // Handle create version
    const handleCreateVersion = async () => {
        if (selectedFeatures.size === 0) return;
        await onCreateVersion(Array.from(selectedFeatures), versionName || undefined);
        setVersionName("");
    };

    const isDisabled = isCreating || hasActiveVersion || selectedFeatures.size === 0;

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            <Sparkles className="h-5 w-5" />
                            Create New Version
                        </CardTitle>
                        <CardDescription>
                            Select features to include in the enriched dataset
                        </CardDescription>
                    </div>
                    <ViewToggle value={viewMode} onChange={setViewMode} />
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Template Selector */}
                <TemplateSelector
                    onApplyTemplate={applyTemplate}
                    disabled={isCreating || hasActiveVersion}
                />

                {/* Graph or List View */}
                {viewMode === "graph" ? (
                    <GraphView
                        dagData={dagData}
                        selectedFeatures={selectedFeatures}
                        onFeaturesChange={handleGraphFeaturesChange}
                        isLoading={loading}
                    />
                ) : (
                    <ListView
                        nodes={filteredNodes}
                        selectedFeatures={selectedFeatures}
                        expandedNodes={expandedNodes}
                        onToggleFeature={toggleFeature}
                        onToggleNode={toggleNode}
                        onToggleNodeExpand={toggleNodeExpand}
                        searchQuery={searchQuery}
                        onSearchChange={setSearchQuery}
                        isLoading={loading}
                    />
                )}

                {/* Selected Features Panel */}
                <SelectedFeaturesPanel
                    selectedFeatures={selectedFeatures}
                    allFeatures={allFeatures}
                    nodes={extractorNodes}
                    onRemoveFeature={toggleFeature}
                    onClearAll={clearSelection}
                    rowCount={rowCount}
                />

                {/* Version Name and Create Button */}
                <div className="flex items-center gap-4 border-t pt-4">
                    <Input
                        placeholder="Version name (optional, e.g., 'v3 - Git + Build Logs')"
                        value={versionName}
                        onChange={(e) => setVersionName(e.target.value)}
                        className="flex-1"
                        disabled={isDisabled}
                    />
                    <Button
                        onClick={handleCreateVersion}
                        disabled={isDisabled}
                        className="gap-2"
                    >
                        {isCreating ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Creating...
                            </>
                        ) : (
                            <>
                                <Zap className="h-4 w-4" />
                                Create Version
                            </>
                        )}
                    </Button>
                </div>

                {hasActiveVersion && (
                    <p className="text-center text-sm text-amber-600 dark:text-amber-400">
                        ⏳ A version is currently processing. Wait for it to complete or cancel it.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
