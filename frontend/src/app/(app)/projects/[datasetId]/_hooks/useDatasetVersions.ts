"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export interface DatasetVersion {
    id: string;
    dataset_id: string;
    version_number: number;
    name: string;
    description: string | null;
    selected_features: string[];
    status: "pending" | "ingesting" | "processing" | "completed" | "failed" | "cancelled";
    total_rows: number;
    processed_rows: number;
    enriched_rows: number;
    failed_rows: number;
    skipped_rows: number;
    progress_percent: number;
    file_name: string | null;
    file_size_bytes: number | null;
    started_at: string | null;
    completed_at: string | null;
    error_message: string | null;
    created_at: string;
}

interface VersionListResponse {
    versions: DatasetVersion[];
    total: number;
    skip: number;
    limit: number;
}

interface CreateVersionRequest {
    selected_features: string[];
    feature_configs?: Record<string, unknown>;
    scan_metrics?: {
        sonarqube: string[];
        trivy: string[];
    };
    scan_config?: {
        sonarqube?: {
            projectKey?: string;
            sonarToken?: string;
            sonarUrl?: string;
            extraProperties?: string;
        };
        trivy?: {
            severity?: string;
            scanners?: string;
            extraArgs?: string;
        };
    };
    name?: string;
    description?: string;
}



export interface UseDatasetVersionsReturn {
    versions: DatasetVersion[];
    activeVersion: DatasetVersion | null;
    loading: boolean;
    creating: boolean;
    error: string | null;

    // Pagination
    total: number;
    skip: number;
    limit: number;
    hasMore: boolean;

    // Actions
    refresh: () => Promise<void>;
    loadMore: () => Promise<void>;
    createVersion: (request: CreateVersionRequest) => Promise<DatasetVersion | null>;
    cancelVersion: (versionId: string) => Promise<void>;
    deleteVersion: (versionId: string) => Promise<void>;
    downloadVersion: (versionId: string, format?: "csv" | "json") => void;
}

export function useDatasetVersions(datasetId: string): UseDatasetVersionsReturn {
    const [versions, setVersions] = useState<DatasetVersion[]>([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Pagination state
    const [total, setTotal] = useState(0);
    const [skip, setSkip] = useState(0);
    const [limit] = useState(10);

    // Find active (processing) version
    const activeVersion = versions.find(
        (v) => v.status === "pending" || v.status === "ingesting" || v.status === "processing"
    ) || null;

    const hasMore = skip + versions.length < total;

    // Load versions (reset to first page)
    const refresh = useCallback(async () => {
        try {
            const response = await api.get<VersionListResponse>(
                `/datasets/${datasetId}/versions?skip=0&limit=${limit}`
            );
            setVersions(response.data.versions);
            setTotal(response.data.total);
            setSkip(0);
            setError(null);
        } catch (err: unknown) {
            console.error("Failed to load versions:", err);
            const message = err instanceof Error ? err.message : "Failed to load versions";
            setError(message);
        }
    }, [datasetId, limit]);

    // Load more versions (append to list)
    const loadMore = useCallback(async () => {
        if (!hasMore) return;
        try {
            const newSkip = skip + limit;
            const response = await api.get<VersionListResponse>(
                `/datasets/${datasetId}/versions?skip=${newSkip}&limit=${limit}`
            );
            setVersions((prev) => [...prev, ...response.data.versions]);
            setSkip(newSkip);
            setTotal(response.data.total);
        } catch (err: unknown) {
            console.error("Failed to load more versions:", err);
        }
    }, [datasetId, skip, limit, hasMore]);

    // Initial load
    useEffect(() => {
        async function load() {
            setLoading(true);
            await refresh();
            setLoading(false);
        }
        load();
    }, [refresh]);

    // Poll for progress when active version exists (fallback when WebSocket not used)
    useEffect(() => {
        if (!activeVersion) return;

        const interval = setInterval(async () => {
            await refresh();
        }, 5000); // Poll every 5 seconds as fallback

        return () => clearInterval(interval);
    }, [activeVersion?.id, refresh]);

    // Create a new version
    const createVersion = useCallback(
        async (request: CreateVersionRequest): Promise<DatasetVersion | null> => {
            try {
                setCreating(true);
                setError(null);

                const response = await api.post<DatasetVersion>(
                    `/datasets/${datasetId}/versions`,
                    request
                );

                // Add to list
                setVersions((prev) => [response.data, ...prev]);
                return response.data;
            } catch (err: unknown) {
                console.error("Failed to create version:", err);
                const message = err instanceof Error ? err.message : "Failed to create version";
                setError(message);
                return null;
            } finally {
                setCreating(false);
            }
        },
        [datasetId]
    );

    // Cancel a version
    const cancelVersion = useCallback(
        async (versionId: string) => {
            try {
                await api.post(`/datasets/${datasetId}/versions/${versionId}/cancel`);
                await refresh();
            } catch (err: unknown) {
                console.error("Failed to cancel version:", err);
                const message = err instanceof Error ? err.message : "Failed to cancel version";
                setError(message);
            }
        },
        [datasetId, refresh]
    );

    // Delete a version
    const deleteVersion = useCallback(
        async (versionId: string) => {
            try {
                await api.delete(`/datasets/${datasetId}/versions/${versionId}`);
                setVersions((prev) => prev.filter((v) => v.id !== versionId));
            } catch (err: unknown) {
                console.error("Failed to delete version:", err);
                const message = err instanceof Error ? err.message : "Failed to delete version";
                setError(message);
            }
        },
        [datasetId]
    );

    // Download a version in specified format
    const downloadVersion = useCallback(
        async (versionId: string, format: "csv" | "json" = "csv") => {
            try {
                const response = await api.get(
                    `/datasets/${datasetId}/versions/${versionId}/export?format=${format}`,
                    { responseType: "blob" }
                );

                // Get filename from Content-Disposition header or use default
                const contentDisposition = response.headers["content-disposition"];
                let filename = `enriched_v${versionId}.${format}`;
                if (contentDisposition) {
                    const match = contentDisposition.match(/filename="?(.+?)"?$/);
                    if (match) {
                        filename = match[1];
                    }
                }

                // Create download link
                const blob = new Blob([response.data]);
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
            } catch (err) {
                console.error("Failed to download version:", err);
                setError(err instanceof Error ? err.message : "Download failed");
            }
        },
        [datasetId]
    );

    return {
        versions,
        activeVersion,
        loading,
        creating,
        error,

        // Pagination
        total,
        skip,
        limit,
        hasMore,

        // Actions
        refresh,
        loadMore,
        createVersion,
        cancelVersion,
        deleteVersion,
        downloadVersion,
    };
}


// Scan status types
export interface ScanStatusCounts {
    pending: number;
    scanning: number;
    completed: number;
    failed: number;
    skipped: number;
}

export interface ScanStatus {
    total: number;
    status_counts: ScanStatusCounts;
    has_pending: boolean;
}

// Helper functions for scan status (used by VersionHistory component)
export async function getScanStatus(datasetId: string, versionId: string): Promise<ScanStatus | null> {
    try {
        const response = await api.get<ScanStatus>(
            `/datasets/${datasetId}/versions/${versionId}/scan-status`
        );
        return response.data;
    } catch (err) {
        console.error("Failed to get scan status:", err);
        return null;
    }
}

export async function retryScan(datasetId: string, versionId: string): Promise<{ status: string; task_id?: string } | null> {
    try {
        const response = await api.post<{ status: string; task_id?: string; message?: string }>(
            `/datasets/${datasetId}/versions/${versionId}/retry-scan`
        );
        return response.data;
    } catch (err) {
        console.error("Failed to retry scan:", err);
        return null;
    }
}

