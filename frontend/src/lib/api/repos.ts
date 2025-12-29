import type {
    RepoDetail,
    RepoImportPayload,
    RepoListResponse,
    RepoSearchResponse,
    RepoSuggestionResponse,
    RepositoryRecord,
} from "@/types";
import { api } from "./client";

export const reposApi = {
    list: async (params?: { skip?: number; limit?: number; q?: string }) => {
        const response = await api.get<RepoListResponse>("/repos/", { params });
        return response.data;
    },
    get: async (repoId: string) => {
        const response = await api.get<RepoDetail>(`/repos/${repoId}`);
        return response.data;
    },
    importBulk: async (payloads: RepoImportPayload[]) => {
        const response = await api.post<RepositoryRecord[]>("/repos/import/bulk", payloads);
        return response.data;
    },
    discover: async (query?: string, limit: number = 50) => {
        const response = await api.get<RepoSuggestionResponse>("/repos/available", {
            params: { q: query, limit },
        });
        return response.data;
    },
    search: async (query?: string) => {
        const response = await api.get<RepoSearchResponse>("/repos/search", {
            params: { q: query },
        });
        return response.data;
    },
    triggerLazySync: async (repoId: string) => {
        const response = await api.post<{ status: string }>(`/repos/${repoId}/sync-run`);
        return response.data;
    },
    reprocessFailed: async (repoId: string) => {
        const response = await api.post<{ status: string; message?: string }>(
            `/repos/${repoId}/reprocess-failed`
        );
        return response.data;
    },
    reingestFailed: async (repoId: string) => {
        const response = await api.post<{ status: string; message?: string }>(
            `/repos/${repoId}/reingest-failed`
        );
        return response.data;
    },
    startProcessing: async (repoId: string) => {
        const response = await api.post<{ status: string; message?: string }>(
            `/repos/${repoId}/start-processing`
        );
        return response.data;
    },
    detectLanguages: async (fullName: string) => {
        const response = await api.get<{ languages: string[] }>(`/repos/languages`, {
            params: { full_name: fullName },
        });
        return response.data;
    },
    delete: async (repoId: string) => {
        await api.delete(`/repos/${repoId}`);
    },
    getImportProgress: async (repoId: string) => {
        const response = await api.get<{
            repo_id: string;
            import_status: string;
            import_version: number;
            import_builds: {
                pending: number;
                fetched: number;
                ingesting: number;
                ingested: number;
                failed: number;
                total: number;
            };
            training_builds: {
                pending: number;
                completed: number;
                partial: number;
                failed: number;
                total: number;
            };
            summary: {
                total_builds_imported: number;
                total_builds_processed: number;
                total_builds_failed: number;
            };
        }>(`/repos/${repoId}/import-progress`);
        return response.data;
    },
    retryPredictions: async (repoId: string) => {
        const response = await api.post<{ status: string; message?: string }>(
            `/repos/${repoId}/retry-predictions`
        );
        return response.data;
    },
};
