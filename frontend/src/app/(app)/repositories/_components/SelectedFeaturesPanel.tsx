"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { X, Trash2 } from "lucide-react";

interface SelectedFeaturesPanelProps {
    selectedFeatures: string[];
    featureLabels?: Record<string, string>;
    featureDescriptions?: Record<string, string>;
    onRemove: (featureName: string) => void;
    onClear: () => void;
}

export function SelectedFeaturesPanel({
    selectedFeatures,
    featureLabels = {},
    featureDescriptions = {},
    onRemove,
    onClear,
}: SelectedFeaturesPanelProps) {
    if (selectedFeatures.length === 0) {
        return (
            <div className="rounded-xl border border-dashed bg-slate-50/50 dark:bg-slate-900/20 p-4">
                <p className="text-sm text-muted-foreground text-center">
                    No features selected. Click on nodes in the graph to select features.
                </p>
            </div>
        );
    }

    return (
        <TooltipProvider delayDuration={200}>
            <div className="rounded-xl border bg-white dark:bg-slate-900 p-4 space-y-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold">Selected Features</span>
                        <Badge variant="secondary">{selectedFeatures.length}</Badge>
                    </div>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={onClear}
                        className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Clear All
                    </Button>
                </div>

                <div className="flex flex-wrap gap-2 max-h-[200px] overflow-y-auto">
                    {selectedFeatures.map((feature) => {
                        const label = featureLabels[feature] || feature;
                        const description = featureDescriptions[feature];

                        return (
                            <Tooltip key={feature}>
                                <TooltipTrigger asChild>
                                    <Badge
                                        variant="secondary"
                                        className="flex items-center gap-1 pr-1 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-help"
                                    >
                                        <span className="text-xs">{label}</span>
                                        <button
                                            type="button"
                                            className="p-0.5 rounded-full hover:bg-slate-300 dark:hover:bg-slate-600"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onRemove(feature);
                                            }}
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </Badge>
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-xs">
                                    <div className="space-y-1">
                                        <p className="font-mono text-xs text-muted-foreground">{feature}</p>
                                        {description && (
                                            <p className="text-sm">{description}</p>
                                        )}
                                        {!description && (
                                            <p className="text-sm text-muted-foreground italic">No description available</p>
                                        )}
                                    </div>
                                </TooltipContent>
                            </Tooltip>
                        );
                    })}
                </div>
            </div>
        </TooltipProvider>
    );
}
