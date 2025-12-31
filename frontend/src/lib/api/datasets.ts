import type {
    DatasetCreatePayload,
    DatasetListResponse,
    DatasetRecord,
    DatasetTemplateListResponse,
    DatasetTemplateRecord,
    DatasetUpdatePayload,
} from "@/types";
import { api } from "./client";

export const datasetsApi = {
    list: async (params?: { skip?: number; limit?: number; q?: string }) => {
        const response = await api.get<DatasetListResponse>("/datasets", { params });
        return response.data;
    },
    listTemplates: async () => {
        const response = await api.get<DatasetTemplateListResponse>("/templates");
        return response.data;
    },
    getTemplateByName: async (name: string) => {
        const response = await api.get<DatasetTemplateRecord>(`/templates/by-name/${encodeURIComponent(name)}`);
        return response.data;
    },
    get: async (datasetId: string) => {
        const response = await api.get<DatasetRecord>(`/datasets/${datasetId}`);
        return response.data;
    },
    create: async (payload: DatasetCreatePayload) => {
        const response = await api.post<DatasetRecord>("/datasets", payload);
        return response.data;
    },
    upload: async (file: File, payload?: { name?: string; description?: string }) => {
        const formData = new FormData();
        formData.append("file", file);
        if (payload?.name) formData.append("name", payload.name);
        if (payload?.description) formData.append("description", payload.description);

        const response = await api.post<DatasetRecord>("/datasets/upload", formData, {
            headers: { "Content-Type": "multipart/form-data" },
        });
        return response.data;
    },
    delete: async (datasetId: string) => {
        await api.delete(`/datasets/${datasetId}`);
    },
    update: async (datasetId: string, payload: DatasetUpdatePayload) => {
        const response = await api.patch<DatasetRecord>(`/datasets/${datasetId}`, payload);
        return response.data;
    },
    startValidation: async (datasetId: string) => {
        const response = await api.post<{ task_id: string; message: string }>(
            `/datasets/${datasetId}/validate`
        );
        return response.data;
    },
    getValidationSummary: async (datasetId: string) => {
        const response = await api.get<{
            dataset_id: string;
            status: string;
            stats: Record<string, number>;
            repos: Array<{
                id: string;
                raw_repo_id: string;
                github_repo_id?: number;  // Needed for per-repo scan config
                full_name: string;
                ci_provider: string;
                validation_status: string;
                validation_error?: string | null;
                builds_total: number;
                builds_found: number;
                builds_not_found: number;
            }>;
        }>(`/datasets/${datasetId}/validation-summary`);
        return response.data;
    },
    getRepoStats: async (
        datasetId: string,
        params?: { skip?: number; limit?: number; q?: string }
    ) => {
        const response = await api.get<{
            items: Array<{
                id: string;
                raw_repo_id: string;
                full_name: string;
                is_valid: boolean;
                validation_status: string;
                validation_error?: string;
                builds_total: number;
                builds_found: number;
                builds_not_found: number;
                builds_filtered: number;
            }>;
            total: number;
            skip: number;
            limit: number;
        }>(`/datasets/${datasetId}/repos`, { params });
        return response.data;
    },
    listVersions: async (datasetId: string, params?: { skip?: number; limit?: number }) => {
        const response = await api.get<{
            versions: Array<{
                id: string;
                status: string;
                // Add other fields as needed
                [key: string]: unknown;
            }>;
            total: number;
        }>(`/datasets/${datasetId}/versions`, { params });
        return response.data;
    },
    createVersion: async (datasetId: string, payload: {
        selected_features: string[];
        feature_configs?: Record<string, unknown>;
        scan_config?: {
            metrics?: { sonarqube?: string[]; trivy?: string[] };
            config?: unknown;
        };
        name?: string;
    }) => {
        const response = await api.post(`/datasets/${datasetId}/versions`, payload);
        return response.data;
    },
};
