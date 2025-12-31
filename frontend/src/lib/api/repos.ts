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
            status: string;
            // Checkpoint info
            checkpoint: {
                has_checkpoint: boolean;
                last_checkpoint_at: string | null;
                accepted_failed: number;
                stats: Record<string, number>;
            };
            // Total import builds (all batches)
            import_builds: {
                pending: number;
                fetched: number;
                ingesting: number;
                ingested: number;
                missing_resource: number;
                total: number;
            };
            resource_status: Record<string, Record<string, number>>;
            training_builds: {
                pending: number;
                completed: number;
                partial: number;
                failed: number;
                total: number;
                with_prediction: number;
                pending_prediction: number;
                prediction_failed: number;
            };
            summary: {
                builds_fetched: number;
                builds_completed: number;
                builds_missing_resource: number;
                builds_processing_failed: number;
            };
        }>(`/repos/${repoId}/import-progress`);
        return response.data;
    },
    getFailedImportBuilds: async (repoId: string, limit: number = 50) => {
        const response = await api.get<{
            repo_id: string;
            total: number;
            missing_resource_builds: Array<{
                id: string;
                ci_run_id: string;
                commit_sha: string;
                ingestion_error?: string;
                resource_errors: Record<string, string>;
                fetched_at?: string;
            }>;
        }>(`/repos/${repoId}/import-progress/failed`, {
            params: { limit },
        });
        return response.data;
    },
};
