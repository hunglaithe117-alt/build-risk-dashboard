/**
 * Shared feature components.
 *
 * Usage:
 * import { FeatureDAGVisualization, useFeatureSelector } from "@/components/features";
 * import { GraphView, ListView, SelectedFeaturesPanel } from "@/components/features/selection";
 * import { FeatureConfigForm, RepoConfigSection } from "@/components/features/config";
 */

// DAG visualization
export { FeatureDAGVisualization } from "./dag";
export type { FeatureDAGData } from "./dag";

// Types
export type {
    DAGNode,
    DAGEdge,
    ExecutionLevel,
    FeatureDefinition,
    NodeInfo,
    FeaturesByNodeResponse,
} from "./types";

// Hooks
export { useFeatureSelector } from "./hooks/useFeatureSelector";
export type { UseFeatureSelectorReturn } from "./hooks/useFeatureSelector";
