import type {
    EnrichmentJob,
    EnrichmentStartRequest,
    EnrichmentStartResponse,
    EnrichmentStatusResponse,
    EnrichmentValidateResponse,
} from "@/types";
import { api } from "./client";

export const enrichmentApi = {
    validate: async (datasetId: string): Promise<EnrichmentValidateResponse> => {
        const response = await api.post<EnrichmentValidateResponse>(
            `/datasets/${datasetId}/validate-enrichment`
        );
        return response.data;
    },

    start: async (
        datasetId: string,
        request: EnrichmentStartRequest
    ): Promise<EnrichmentStartResponse> => {
        const response = await api.post<EnrichmentStartResponse>(
            `/datasets/${datasetId}/enrich`,
            request
        );
        return response.data;
    },

    getStatus: async (datasetId: string): Promise<EnrichmentStatusResponse> => {
        const response = await api.get<EnrichmentStatusResponse>(
            `/datasets/${datasetId}/enrich/status`
        );
        return response.data;
    },

    listJobs: async (datasetId: string): Promise<EnrichmentJob[]> => {
        const response = await api.get<EnrichmentJob[]>(
            `/datasets/${datasetId}/enrich/jobs`
        );
        return response.data;
    },

    download: async (datasetId: string): Promise<Blob> => {
        const response = await api.get(`/datasets/${datasetId}/download`, {
            responseType: "blob",
        });
        return response.data;
    },

    getWebSocketUrl: (jobId: string): string => {
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = process.env.NEXT_PUBLIC_API_URL
            ?.replace(/^https?:\/\//, "")
            ?.replace(/\/api\/?$/, "") || "localhost:8000";
        return `${wsProtocol}//${host}/api/ws/enrichment/${jobId}`;
    },
};
