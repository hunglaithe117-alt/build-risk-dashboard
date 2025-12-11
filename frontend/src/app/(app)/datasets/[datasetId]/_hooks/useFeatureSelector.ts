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
}

interface ExtractorInfo {
    name: string;
    display_name: string;
    features: FeatureDefinition[];
    feature_count: number;
}

interface SourceInfo {
    source: string;
    display_name: string;
    description: string;
    icon: string;
    is_configured: boolean;
    extractors: Record<string, ExtractorInfo>;
    total_features: number;
}

interface FeaturesBySourceResponse {
    sources: Record<string, SourceInfo>;
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
    dataSources: SourceInfo[];
    dagData: FeatureDAGData | null;
    allFeatures: FeatureDefinition[];
    loading: boolean;
    error: string | null;

    // Selection state
    selectedFeatures: Set<string>;
    expandedSources: Set<string>;
    expandedExtractors: Set<string>;
    searchQuery: string;

    // Actions
    toggleFeature: (featureName: string) => void;
    toggleExtractor: (extractorName: string, features: string[]) => void;
    toggleSource: (sourceName: string) => void;
    toggleSourceExpand: (sourceName: string) => void;
    toggleExtractorExpand: (extractorName: string) => void;
    selectAllAvailable: () => void;
    clearSelection: () => void;
    setSearchQuery: (query: string) => void;
    applyTemplate: (featureNames: string[]) => void;

    // Computed
    selectedCount: number;
    selectedSources: string[];
    filteredSources: SourceInfo[];
    getFeatureDescription: (featureName: string) => string;
}

export function useFeatureSelector(): UseFeatureSelectorReturn {
    // State
    const [dataSources, setDataSources] = useState<SourceInfo[]>([]);
    const [dagData, setDagData] = useState<FeatureDAGData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set());
    const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set(["git", "build_log"]));
    const [expandedExtractors, setExpandedExtractors] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState("");

    // Load features on mount
    useEffect(() => {
        async function loadData() {
            try {
                setLoading(true);
                const [sourcesRes, dagRes] = await Promise.all([
                    api.get<FeaturesBySourceResponse>("/features/by-source"),
                    api.get<FeatureDAGData>("/features/dag"),
                ]);

                const sources = Object.values(sourcesRes.data.sources);
                setDataSources(sources);
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

    // All features flattened
    const allFeatures = useMemo(() => {
        const features: FeatureDefinition[] = [];
        dataSources.forEach((source) => {
            Object.values(source.extractors).forEach((extractor) => {
                features.push(...extractor.features);
            });
        });
        return features;
    }, [dataSources]);

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

    // Toggle all features in an extractor
    const toggleExtractor = useCallback((extractorName: string, features: string[]) => {
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

    // Toggle all features in a source
    const toggleSource = useCallback(
        (sourceName: string) => {
            const source = dataSources.find((s) => s.source === sourceName);
            if (!source || !source.is_configured) return;

            const allSourceFeatures: string[] = [];
            Object.values(source.extractors).forEach((ext) => {
                ext.features.forEach((f) => allSourceFeatures.push(f.name));
            });

            setSelectedFeatures((prev) => {
                const next = new Set(prev);
                const allSelected = allSourceFeatures.every((f) => prev.has(f));

                if (allSelected) {
                    allSourceFeatures.forEach((f) => next.delete(f));
                } else {
                    allSourceFeatures.forEach((f) => next.add(f));
                }
                return next;
            });
        },
        [dataSources]
    );

    // Expand/collapse helpers
    const toggleSourceExpand = useCallback((sourceName: string) => {
        setExpandedSources((prev) => {
            const next = new Set(prev);
            if (next.has(sourceName)) {
                next.delete(sourceName);
            } else {
                next.add(sourceName);
            }
            return next;
        });
    }, []);

    const toggleExtractorExpand = useCallback((extractorName: string) => {
        setExpandedExtractors((prev) => {
            const next = new Set(prev);
            if (next.has(extractorName)) {
                next.delete(extractorName);
            } else {
                next.add(extractorName);
            }
            return next;
        });
    }, []);

    // Select all available (configured) features
    const selectAllAvailable = useCallback(() => {
        const allAvailable: string[] = [];
        dataSources.forEach((source) => {
            if (source.is_configured) {
                Object.values(source.extractors).forEach((ext) => {
                    ext.features.forEach((f) => allAvailable.push(f.name));
                });
            }
        });
        setSelectedFeatures(new Set(allAvailable));
    }, [dataSources]);

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

    const selectedSources = useMemo(() => {
        const sources = new Set<string>();
        selectedFeatures.forEach((f) => {
            if (f.startsWith("git_")) sources.add("git");
            else if (f.startsWith("gh_")) sources.add("github");
            else if (f.startsWith("tr_log_")) sources.add("build_log");
            else if (f.startsWith("tr_")) sources.add("repo");
            else if (f.startsWith("sonar_")) sources.add("sonarqube");
            else if (f.startsWith("trivy_")) sources.add("trivy");
        });
        return Array.from(sources);
    }, [selectedFeatures]);

    // Filter sources by search
    const filteredSources = useMemo(() => {
        if (!searchQuery.trim()) return dataSources;

        const query = searchQuery.toLowerCase();
        return dataSources
            .map((source) => {
                // Filter extractors and features
                const filteredExtractors: Record<string, ExtractorInfo> = {};
                let totalFiltered = 0;

                Object.entries(source.extractors).forEach(([name, ext]) => {
                    const filteredFeatures = ext.features.filter(
                        (f) =>
                            f.name.toLowerCase().includes(query) ||
                            f.display_name.toLowerCase().includes(query) ||
                            f.description.toLowerCase().includes(query)
                    );

                    if (filteredFeatures.length > 0) {
                        filteredExtractors[name] = {
                            ...ext,
                            features: filteredFeatures,
                            feature_count: filteredFeatures.length,
                        };
                        totalFiltered += filteredFeatures.length;
                    }
                });

                if (totalFiltered === 0) return null;

                return {
                    ...source,
                    extractors: filteredExtractors,
                    total_features: totalFiltered,
                };
            })
            .filter((s): s is SourceInfo => s !== null);
    }, [dataSources, searchQuery]);

    return {
        // Data
        dataSources,
        dagData,
        allFeatures,
        loading,
        error,

        // Selection state
        selectedFeatures,
        expandedSources,
        expandedExtractors,
        searchQuery,

        // Actions
        toggleFeature,
        toggleExtractor,
        toggleSource,
        toggleSourceExpand,
        toggleExtractorExpand,
        selectAllAvailable,
        clearSelection,
        setSearchQuery,
        applyTemplate,

        // Computed
        selectedCount,
        selectedSources,
        filteredSources,
        getFeatureDescription,
    };
}
