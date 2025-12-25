/**
 * API client for dataset comparison endpoints.
 */

import api from './axios';

// =============================================================================
// Types
// =============================================================================

export interface ComparableVersion {
    version_id: string;
    version_name: string;
    total_rows: number;
    feature_count: number;
}

export interface ComparableDataset {
    dataset_id: string;
    dataset_name: string;
    versions: ComparableVersion[];
}

export interface CompareInternalRequest {
    base_dataset_id: string;
    base_version_id: string;
    target_dataset_id: string;
    target_version_id: string;
}

export interface VersionSummary {
    dataset_id: string;
    dataset_name: string;
    version_id: string;
    version_name: string;
    total_rows: number;
    total_features: number;
    selected_features: string[];
    enriched_rows: number;
    completeness_pct: number;
}

export interface ExternalDatasetSummary {
    filename: string;
    total_rows: number;
    total_columns: number;
    columns: string[];
}

export interface FeatureComparison {
    common_features: string[];
    base_only_features: string[];
    target_only_features: string[];
    feature_details: Array<{
        feature_name: string;
        in_base: boolean;
        in_target: boolean;
        base_null_pct?: number;
        target_null_pct?: number;
    }>;
}

export interface QualityComparison {
    base_completeness_pct: number;
    target_completeness_pct: number;
    base_avg_null_pct: number;
    target_avg_null_pct: number;
    completeness_diff: number;
}

export interface RowOverlap {
    base_total_rows: number;
    target_total_rows: number;
    overlapping_rows: number;
    overlap_pct: number;
    base_only_rows: number;
    target_only_rows: number;
}

export interface CompareResponse {
    comparison_type: 'internal';
    base: VersionSummary;
    target: VersionSummary;
    feature_comparison: FeatureComparison;
    quality_comparison: QualityComparison;
    row_overlap: RowOverlap;
}

export interface CompareExternalResponse {
    comparison_type: 'external';
    base: VersionSummary;
    external_target: ExternalDatasetSummary;
    feature_comparison: FeatureComparison;
    quality_comparison: QualityComparison;
}

// =============================================================================
// API Client
// =============================================================================

export const comparisonApi = {
    /**
     * Get list of datasets and versions available for comparison.
     */
    getComparableDatasets: async (): Promise<{ datasets: ComparableDataset[] }> => {
        const response = await api.get<{ datasets: ComparableDataset[] }>('/comparison/datasets');
        return response.data;
    },

    /**
     * Compare two internal dataset versions.
     */
    compareInternal: async (request: CompareInternalRequest): Promise<CompareResponse> => {
        const response = await api.post<CompareResponse>('/comparison/compare', request);
        return response.data;
    },

    /**
     * Compare an internal version with an uploaded external CSV.
     */
    compareExternal: async (
        datasetId: string,
        versionId: string,
        file: File
    ): Promise<CompareExternalResponse> => {
        const formData = new FormData();
        formData.append('dataset_id', datasetId);
        formData.append('version_id', versionId);
        formData.append('file', file);

        const response = await api.post<CompareExternalResponse>(
            '/comparison/compare-external',
            formData,
            {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }
        );
        return response.data;
    },
};
