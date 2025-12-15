"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

interface FeatureDefinition {
    name: string;
    display_name: string;
    description: string;
    data_type: string;
    is_active: boolean;
    depends_on_features: string[];
    depends_on_resources: string[];
    node: string;
}

export interface NodeInfo {
    name: string;
    display_name: string;
    description: string;
    group: string;
    is_configured: boolean;
    requires_resources: string[];
    features: FeatureDefinition[];
    feature_count: number;
}

interface FeaturesByNodeResponse {
    nodes: Record<string, NodeInfo>;
}

interface DAGNode {
    id: string;
    type: "extractor" | "resource";
    label: string;
    features: string[];
    feature_count: number;
    requires_resources: string[];
    requires_features: string[];
    level: number;
}

interface DAGEdge {
    id: string;
    source: string;
    target: string;
    type: "feature_dependency" | "resource_dependency";
}

interface ExecutionLevel {
    level: number;
    nodes: string[];
}

export interface FeatureDAGData {
    nodes: DAGNode[];
    edges: DAGEdge[];
    execution_levels: ExecutionLevel[];
    total_features: number;
    total_nodes: number;
}

export interface UseFeatureSelectorReturn {
    // Data
    extractorNodes: NodeInfo[];
    dagData: FeatureDAGData | null;
    allFeatures: FeatureDefinition[];
    loading: boolean;
    error: string | null;

    // Selection state
    selectedFeatures: Set<string>;
    expandedNodes: Set<string>;
    searchQuery: string;

    // Actions
    toggleFeature: (featureName: string) => void;
    toggleNode: (nodeName: string, features: string[]) => void;
    toggleNodeExpand: (nodeName: string) => void;
    selectAllAvailable: () => void;
    clearSelection: () => void;
    setSearchQuery: (query: string) => void;
    applyTemplate: (featureNames: string[]) => void;

    // Computed
    selectedCount: number;
    selectedNodes: string[];
    filteredNodes: NodeInfo[];
    getFeatureDescription: (featureName: string) => string;
}

export function useFeatureSelector(): UseFeatureSelectorReturn {
    // State
    const [extractorNodes, setExtractorNodes] = useState<NodeInfo[]>([]);
    const [dagData, setDagData] = useState<FeatureDAGData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set());
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(
        new Set(["git_commit_info", "git_diff_features", "job_metadata", "test_log_parser"])
    );
    const [searchQuery, setSearchQuery] = useState("");

    // Load features on mount
    useEffect(() => {
        async function loadData() {
            try {
                setLoading(true);
                const [nodesRes, dagRes] = await Promise.all([
                    api.get<FeaturesByNodeResponse>("/features/by-node"),
                    api.get<FeatureDAGData>("/features/dag"),
                ]);

                const nodes = Object.values(nodesRes.data.nodes);
                setExtractorNodes(nodes);
                setDagData(dagRes.data);
                setError(null);
            } catch (err) {
                console.error("Failed to load features:", err);
                setError("Failed to load features");
            } finally {
                setLoading(false);
            }
        }
        loadData();
    }, []);

    // All features flattened (with node info)
    const allFeatures = useMemo(() => {
        const features: FeatureDefinition[] = [];
        extractorNodes.forEach((nodeInfo) => {
            nodeInfo.features.forEach((f) => {
                features.push({
                    ...f,
                    node: nodeInfo.name,
                });
            });
        });
        return features;
    }, [extractorNodes]);

    // Toggle single feature
    const toggleFeature = useCallback((featureName: string) => {
        setSelectedFeatures((prev) => {
            const next = new Set(prev);
            if (next.has(featureName)) {
                next.delete(featureName);
            } else {
                next.add(featureName);
            }
            return next;
        });
    }, []);

    // Toggle all features in a node
    const toggleNode = useCallback((nodeName: string, features: string[]) => {
        setSelectedFeatures((prev) => {
            const next = new Set(prev);
            const allSelected = features.every((f) => prev.has(f));

            if (allSelected) {
                // Deselect all
                features.forEach((f) => next.delete(f));
            } else {
                // Select all
                features.forEach((f) => next.add(f));
            }
            return next;
        });
    }, []);

    // Expand/collapse helpers
    const toggleNodeExpand = useCallback((nodeName: string) => {
        setExpandedNodes((prev) => {
            const next = new Set(prev);
            if (next.has(nodeName)) {
                next.delete(nodeName);
            } else {
                next.add(nodeName);
            }
            return next;
        });
    }, []);

    // Select all available (configured) features
    const selectAllAvailable = useCallback(() => {
        const allAvailable: string[] = [];
        extractorNodes.forEach((node) => {
            if (node.is_configured) {
                node.features.forEach((f) => allAvailable.push(f.name));
            }
        });
        setSelectedFeatures(new Set(allAvailable));
    }, [extractorNodes]);

    // Clear all selections
    const clearSelection = useCallback(() => {
        setSelectedFeatures(new Set());
    }, []);

    // Apply template features (filters to only valid features)
    const applyTemplate = useCallback(
        (featureNames: string[]) => {
            const validFeatureNames = new Set(allFeatures.map((f) => f.name));
            const filtered = featureNames.filter((name) => validFeatureNames.has(name));
            setSelectedFeatures(new Set(filtered));
        },
        [allFeatures]
    );

    // Get feature description
    const getFeatureDescription = useCallback(
        (featureName: string): string => {
            const feature = allFeatures.find((f) => f.name === featureName);
            return feature?.description || "";
        },
        [allFeatures]
    );

    // Computed values
    const selectedCount = selectedFeatures.size;

    const selectedNodes = useMemo(() => {
        const nodes = new Set<string>();
        selectedFeatures.forEach((featureName) => {
            const feature = allFeatures.find((f) => f.name === featureName);
            if (feature?.node) {
                nodes.add(feature.node);
            }
        });
        return Array.from(nodes);
    }, [selectedFeatures, allFeatures]);

    // Filter nodes by search
    const filteredNodes = useMemo(() => {
        if (!searchQuery.trim()) return extractorNodes;

        const query = searchQuery.toLowerCase();
        return extractorNodes
            .map((node) => {
                const filteredFeatures = node.features.filter(
                    (f) =>
                        f.name.toLowerCase().includes(query) ||
                        f.display_name.toLowerCase().includes(query) ||
                        f.description.toLowerCase().includes(query)
                );

                if (filteredFeatures.length === 0) return null;

                return {
                    ...node,
                    features: filteredFeatures,
                    feature_count: filteredFeatures.length,
                };
            })
            .filter((n): n is NodeInfo => n !== null);
    }, [extractorNodes, searchQuery]);

    return {
        // Data
        extractorNodes,
        dagData,
        allFeatures,
        loading,
        error,

        // Selection state
        selectedFeatures,
        expandedNodes,
        searchQuery,

        // Actions
        toggleFeature,
        toggleNode,
        toggleNodeExpand,
        selectAllAvailable,
        clearSelection,
        setSearchQuery,
        applyTemplate,

        // Computed
        selectedCount,
        selectedNodes,
        filteredNodes,
        getFeatureDescription,
    };
}
