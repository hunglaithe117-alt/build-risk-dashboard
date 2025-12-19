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
    status: "pending" | "processing" | "completed" | "failed" | "cancelled";
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
}

interface CreateVersionRequest {
    selected_features: string[];
    name?: string;
    description?: string;
}

export interface UseDatasetVersionsReturn {
    versions: DatasetVersion[];
    activeVersion: DatasetVersion | null;
    loading: boolean;
    creating: boolean;
    error: string | null;

    // Actions
    refresh: () => Promise<void>;
    createVersion: (request: CreateVersionRequest) => Promise<DatasetVersion | null>;
    cancelVersion: (versionId: string) => Promise<void>;
    deleteVersion: (versionId: string) => Promise<void>;
    downloadVersion: (versionId: string, format?: "csv" | "json" | "parquet") => void;
}

export function useDatasetVersions(datasetId: string): UseDatasetVersionsReturn {
    const [versions, setVersions] = useState<DatasetVersion[]>([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Find active (processing) version
    const activeVersion = versions.find(
        (v) => v.status === "pending" || v.status === "processing"
    ) || null;

    // Load versions
    const refresh = useCallback(async () => {
        try {
            const response = await api.get<VersionListResponse>(
                `/datasets/${datasetId}/versions`
            );
            setVersions(response.data.versions);
            setError(null);
        } catch (err: unknown) {
            console.error("Failed to load versions:", err);
            const message = err instanceof Error ? err.message : "Failed to load versions";
            setError(message);
        }
    }, [datasetId]);

    // Initial load
    useEffect(() => {
        async function load() {
            setLoading(true);
            await refresh();
            setLoading(false);
        }
        load();
    }, [refresh]);

    // Poll for progress when active version exists
    useEffect(() => {
        if (!activeVersion) return;

        const interval = setInterval(async () => {
            await refresh();
        }, 2000); // Poll every 2 seconds

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
        async (versionId: string, format: "csv" | "json" | "parquet" = "csv") => {
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
        refresh,
        createVersion,
        cancelVersion,
        deleteVersion,
        downloadVersion,
    };
}
