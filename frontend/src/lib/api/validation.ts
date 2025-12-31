import type {
    DatasetValidationStatus,
    StartValidationResponse,
    ValidationSummary,
} from "@/types";
import { api } from "./client";

export const datasetValidationApi = {
    saveRepos: async (datasetId: string, repos: Array<{
        full_name: string;
        ci_provider: string;
        source_languages: string[];
        test_frameworks: string[];
        validation_status: string;
    }>): Promise<{ saved: number; message: string }> => {
        const response = await api.post<{ saved: number; message: string }>(
            `/datasets/${datasetId}/repos`,
            { repos }
        );
        return response.data;
    },

    start: async (datasetId: string): Promise<StartValidationResponse> => {
        const response = await api.post<StartValidationResponse>(
            `/datasets/${datasetId}/validate`
        );
        return response.data;
    },

    getStatus: async (datasetId: string): Promise<DatasetValidationStatus> => {
        const response = await api.get<DatasetValidationStatus>(
            `/datasets/${datasetId}/validation-status`
        );
        return response.data;
    },

    getSummary: async (datasetId: string): Promise<ValidationSummary> => {
        const response = await api.get<ValidationSummary>(
            `/datasets/${datasetId}/validation-summary`
        );
        return response.data;
    },

    resetValidation: async (datasetId: string): Promise<{ message: string }> => {
        const response = await api.post<{ message: string }>(
            `/datasets/${datasetId}/reset-validation`
        );
        return response.data;
    },

    resetStep2: async (datasetId: string): Promise<{ message: string }> => {
        const response = await api.post<{ message: string }>(
            `/datasets/${datasetId}/reset-step2`
        );
        return response.data;
    },
};
