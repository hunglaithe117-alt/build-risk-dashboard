/**
 * Build Sources API Client
 * 
 * Handles CSV uploads and validation for training data sources.
 */

import { api } from "./client";

// =============================================================================
// Types
// =============================================================================

export interface SourceMapping {
    build_id: string | null;
    repo_name: string | null;
    ci_provider: string | null;
}

export interface ValidationStats {
    repos_total: number;
    repos_valid: number;
    repos_invalid: number;
    repos_not_found: number;
    builds_total: number;
    builds_found: number;
    builds_not_found: number;
    builds_filtered: number;
}

export type ValidationStatus = "pending" | "validating" | "completed" | "failed";

export interface BuildSourceRecord {
    id: string;
    name: string;
    description: string | null;

    // Upload info
    file_name: string | null;
    rows: number;
    size_bytes: number;
    columns: string[];
    mapped_fields: SourceMapping;
    preview: Record<string, string>[];

    // CI Provider
    ci_provider: string | null;

    // Validation status
    validation_status: ValidationStatus;
    validation_progress: number;
    validation_stats: ValidationStats;
    validation_error: string | null;

    // Timestamps
    created_at: string | null;
    updated_at: string | null;
    validation_started_at: string | null;
    validation_completed_at: string | null;

    // Setup step
    setup_step: number;
}

export interface BuildSourceListResponse {
    items: BuildSourceRecord[];
    total: number;
    skip: number;
    limit: number;
}

export interface SourceBuildRecord {
    id: string;
    source_id: string;
    build_id_from_source: string;
    repo_name_from_source: string;
    status: string;
    validation_error: string | null;
    validated_at: string | null;
    raw_repo_id: string | null;
    raw_run_id: string | null;
}

export interface SourceRepoStatsRecord {
    id: string;
    source_id: string;
    raw_repo_id: string;
    full_name: string;
    ci_provider: string;
    builds_total: number;
    builds_found: number;
    builds_not_found: number;
    builds_filtered: number;
    is_valid: boolean;
    validation_error: string | null;
}

// =============================================================================
// API Client
// =============================================================================

export const buildSourcesApi = {
    /**
     * Upload a CSV file to create a new build source.
     */
    async upload(
        file: File,
        options: { name: string; description?: string }
    ): Promise<BuildSourceRecord> {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("name", options.name);
        if (options.description) {
            formData.append("description", options.description);
        }

        const response = await api.post<BuildSourceRecord>("/build-sources", formData, {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        });

        return response.data;
    },

    /**
     * List build sources for the current user.
     */
    async list(params?: {
        skip?: number;
        limit?: number;
        q?: string;
    }): Promise<BuildSourceListResponse> {
        const queryParams = new URLSearchParams();
        if (params?.skip) queryParams.append("skip", String(params.skip));
        if (params?.limit) queryParams.append("limit", String(params.limit));
        if (params?.q) queryParams.append("q", params.q);

        const url = `/build-sources${queryParams.toString() ? `?${queryParams}` : ""}`;
        const response = await api.get<BuildSourceListResponse>(url);
        return response.data;
    },

    /**
     * Get a specific build source.
     */
    async get(sourceId: string): Promise<BuildSourceRecord> {
        const response = await api.get<BuildSourceRecord>(`/build-sources/${sourceId}`);
        return response.data;
    },

    /**
     * Update a build source.
     */
    async update(
        sourceId: string,
        data: {
            name?: string;
            description?: string;
            mapped_fields?: Partial<SourceMapping>;
            ci_provider?: string | null;
        }
    ): Promise<BuildSourceRecord> {
        const response = await api.patch<BuildSourceRecord>(`/build-sources/${sourceId}`, data);
        return response.data;
    },

    /**
     * Delete a build source and all related data.
     */
    async delete(sourceId: string): Promise<{ status: string }> {
        const response = await api.delete<{ status: string }>(`/build-sources/${sourceId}`);
        return response.data;
    },

    /**
     * Start validation for a build source.
     */
    async startValidation(
        sourceId: string
    ): Promise<{ status: string; task_id: string }> {
        const response = await api.post<{ status: string; task_id: string }>(`/build-sources/${sourceId}/validate`, {});
        return response.data;
    },

    /**
     * Get repository stats for a source.
     */
    async getRepoStats(sourceId: string): Promise<SourceRepoStatsRecord[]> {
        const response = await api.get<SourceRepoStatsRecord[]>(`/build-sources/${sourceId}/repos`);
        return response.data;
    },

    /**
     * Get builds for a source.
     */
    async getBuilds(
        sourceId: string,
        params?: { status?: string; skip?: number; limit?: number }
    ): Promise<SourceBuildRecord[]> {
        const queryParams = new URLSearchParams();
        if (params?.status) queryParams.append("status", params.status);
        if (params?.skip) queryParams.append("skip", String(params.skip));
        if (params?.limit) queryParams.append("limit", String(params.limit));

        const url = `/build-sources/${sourceId}/builds${queryParams.toString() ? `?${queryParams}` : ""}`;
        const response = await api.get<SourceBuildRecord[]>(url);
        return response.data;
    },
};
