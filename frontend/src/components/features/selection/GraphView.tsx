"use client";

import { memo } from "react";
import {
    FeatureDAGVisualization,
    type FeatureDAGData,
} from "@/components/features";

interface GraphViewProps {
    dagData: FeatureDAGData | null;
    selectedFeatures: Set<string>;
    onFeaturesChange: (features: string[]) => void;
    isLoading?: boolean;
}

export const GraphView = memo(function GraphView({
    dagData,
    selectedFeatures,
    onFeaturesChange,
    isLoading = false,
}: GraphViewProps) {
    // Convert Set to array for the DAG component
    const selectedArray = Array.from(selectedFeatures);

    return (
        <div className="space-y-3">
            <FeatureDAGVisualization
                dagData={dagData}
                selectedFeatures={selectedArray}
                onFeaturesChange={onFeaturesChange}
                isLoading={isLoading}
                className="h-[450px]"
            />
            <p className="text-center text-xs text-muted-foreground">
                💡 Click on an extractor node to select/deselect all its features.
                Drag to pan, scroll to zoom.
            </p>
        </div>
    );
});
