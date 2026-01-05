import { api } from "./client";

// Types
export interface ScanResultItem {
    id: string;
    commit_sha: string;
    repo_full_name: string;
    row_indices: number[];
    status: string;
    results: Record<string, unknown>;
    error_message?: string | null;
    scan_duration_ms?: number | null;
}

export interface ScanResultsResponse {
    results: ScanResultItem[];
    total: number;
}

export interface ScanSummaryResponse {
    scan_id: string;
    tool_type: string;
    status: string;
    progress: number;
    total_commits: number;
    status_counts: Record<string, number>;
    aggregated_metrics: Record<string, number | string>;
}

export interface EnrichedBuildData {
    id: string;
    raw_build_run_id: string;
    ci_run_id: string;
    repo_full_name: string;
    repo_url?: string;
    provider?: string;
    web_url?: string;
    extraction_status: string;
    feature_count: number;
    expected_feature_count: number;
    missing_resources: string[];
    created_at: string | null;
    enriched_at: string | null;
    features: Record<string, unknown>;
}

/**
 * Import build item for ingestion phase.
 * Extended with RawBuildRun info for detailed view.
 */
export interface ImportBuildItem {
    id: string;
    build_id: string;
    build_number?: number;
    repo_name: string;
    commit_sha: string;
    branch: string;
    conclusion: string;
    created_at: string | null;
    web_url?: string;
    status: "pending" | "ingesting" | "ingested" | "missing_resource" | "failed";
    ingested_at: string | null;
    resource_status: Record<string, { status: string; error?: string }>;
    required_resources: string[];

    // RawBuildRun fields for detailed view
    commit_message?: string;
    commit_author?: string;
    duration_seconds?: number;
    started_at?: string | null;
    completed_at?: string | null;
    provider?: string;
    logs_available?: boolean;
    logs_expired?: boolean;
    ingestion_error?: string | null;
}


export interface VersionDataResponse {
    version: {
        id: string;
        name: string;
        version_number: number;
        status: string;
        builds_total: number;
        builds_ingested: number;
        builds_missing_resource: number;
        builds_ingestion_failed: number;
        builds_processed: number;
        builds_processing_failed: number;
        selected_features: string[];
        scan_metrics?: {
            trivy?: string[];
            sonarqube?: string[];
        };
        created_at: string | null;
        completed_at: string | null;
    };
    builds: EnrichedBuildData[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
    column_stats?: Record<string, unknown>;
}

export interface VersionIngestionProgress {
    total: number;
    status_counts: Record<string, number>;
    resource_status?: Record<string, Record<string, number>>;
}

export const datasetScanApi = {
    getResults: async (
        datasetId: string,
        scanId: string,
        skip = 0,
        limit = 50
    ): Promise<ScanResultsResponse> => {
        const response = await api.get<ScanResultsResponse>(
            `/integrations/datasets/${datasetId}/scans/${scanId}/results`,
            { params: { skip, limit } }
        );
        return response.data;
    },

    getSummary: async (
        datasetId: string,
        scanId: string
    ): Promise<ScanSummaryResponse> => {
        const response = await api.get<ScanSummaryResponse>(
            `/integrations/datasets/${datasetId}/scans/${scanId}/summary`
        );
        return response.data;
    },

    exportResults: async (datasetId: string, scanId: string): Promise<void> => {
        const response = await api.get(
            `/integrations/datasets/${datasetId}/scans/${scanId}/results`,
            { params: { skip: 0, limit: 1000 } }
        );

        const results = response.data.results as ScanResultItem[];
        if (results.length === 0) {
            alert("No results to export");
            return;
        }

        const headers = ["commit_sha", "repo_full_name", "status", "error_message", ...Object.keys(results[0]?.results || {})];
        const csvRows = [headers.join(",")];

        for (const r of results) {
            const row = [
                r.commit_sha,
                r.repo_full_name,
                r.status,
                r.error_message || "",
                ...Object.values(r.results || {}).map(v => String(v ?? "")),
            ];
            csvRows.push(row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(","));
        }

        const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `scan_${scanId}_results.csv`;
        a.click();
        URL.revokeObjectURL(url);
    },
};

export const datasetVersionApi = {
    getVersionData: async (
        datasetId: string,
        versionId: string,
        page: number = 1,
        pageSize: number = 20,
        includeStats: boolean = true
    ): Promise<VersionDataResponse> => {
        const response = await api.get<VersionDataResponse>(
            `/datasets/${datasetId}/versions/${versionId}/data`,
            { params: { page, page_size: pageSize, include_stats: includeStats } }
        );
        return response.data;
    },

    /**
     * Get import builds for ingestion phase.
     */
    getImportBuilds: async (
        datasetId: string,
        versionId: string,
        skip: number = 0,
        limit: number = 20,
        status?: string
    ): Promise<{
        items: ImportBuildItem[];
        total: number;
        page: number;
        size: number;
    }> => {
        const response = await api.get(
            `/datasets/${datasetId}/versions/${versionId}/import-builds`,
            { params: { skip, limit, status } }
        );
        return response.data;
    },

    /**
     * Get enrichment builds for processing phase.
     */
    getEnrichmentBuilds: async (
        datasetId: string,
        versionId: string,
        skip: number = 0,
        limit: number = 20,
        extractionStatus?: string
    ): Promise<{
        items: EnrichedBuildData[];
        total: number;
        page: number;
        size: number;
    }> => {
        const response = await api.get(
            `/datasets/${datasetId}/versions/${versionId}/enrichment-builds`,
            { params: { skip, limit, extraction_status: extractionStatus } }
        );
        return response.data;
    },

    getExportPreview: async (datasetId: string, versionId: string) => {
        const response = await api.get<{
            total_rows: number;
            use_async_recommended: boolean;
            sample_features: string[];
        }>(`/datasets/${datasetId}/versions/${versionId}/preview`);
        return response.data;
    },

    getExportUrl: (
        datasetId: string,
        versionId: string,
        format: "csv" | "json" = "csv"
    ): string => {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
        return `${baseUrl}/datasets/${datasetId}/versions/${versionId}/export?format=${format}`;
    },

    downloadExport: async (
        datasetId: string,
        versionId: string,
        format: "csv" | "json" = "csv"
    ): Promise<Blob> => {
        const response = await api.get(
            `/datasets/${datasetId}/versions/${versionId}/export`,
            { params: { format }, responseType: "blob" }
        );
        return response.data;
    },

    createExportJob: async (
        datasetId: string,
        versionId: string,
        format: "csv" | "json" = "csv"
    ): Promise<{ job_id: string; status: string; total_rows: number }> => {
        const response = await api.post(
            `/datasets/${datasetId}/versions/${versionId}/export/async`,
            null,
            { params: { format } }
        );
        return response.data;
    },

    getExportJobStatus: async (datasetId: string, jobId: string): Promise<{
        id: string;
        status: "pending" | "processing" | "completed" | "failed";
        progress: number;
        error_message?: string;
    }> => {
        const response = await api.get<{
            id: string;
            status: string;
            format: string;
            total_rows: number;
            processed_rows: number;
            progress: number;
            file_path?: string;
            file_size?: number;
            error_message?: string;
            created_at?: string;
            completed_at?: string;
        }>(`/datasets/${datasetId}/versions/export/jobs/${jobId}`);
        return {
            id: response.data.id,
            status: response.data.status as "pending" | "processing" | "completed" | "failed",
            progress: response.data.progress,
            error_message: response.data.error_message,
        };
    },

    listExportJobs: async (datasetId: string, versionId: string) => {
        const response = await api.get<Array<{
            id: string;
            status: string;
            format: string;
            total_rows: number;
            processed_rows: number;
            file_size?: number;
            created_at?: string;
            completed_at?: string;
        }>>(`/datasets/${datasetId}/versions/${versionId}/export/jobs`);
        return response.data;
    },

    downloadExportJob: async (datasetId: string, jobId: string): Promise<Blob> => {
        const response = await api.get(
            `/datasets/${datasetId}/versions/export/jobs/${jobId}/download`,
            { responseType: "blob" }
        );
        return response.data;
    },

    getBuildDetail: async (
        datasetId: string,
        versionId: string,
        buildId: string
    ): Promise<EnrichmentBuildDetailResponse> => {
        const response = await api.get<EnrichmentBuildDetailResponse>(
            `/datasets/${datasetId}/versions/${versionId}/builds/${buildId}`
        );
        return response.data;
    },

    getIngestionProgress: async (
        datasetId: string,
        versionId: string
    ): Promise<VersionIngestionProgress> => {
        const response = await api.get<VersionIngestionProgress>(
            `/datasets/${datasetId}/versions/${versionId}/ingestion-progress`
        );
        return response.data;
    },

    // Processing Phase Control
    startProcessing: async (
        datasetId: string,
        versionId: string
    ): Promise<{ status: string; task_id: string; message: string }> => {
        const response = await api.post(
            `/datasets/${datasetId}/versions/${versionId}/start-processing`
        );
        return response.data;
    },

    retryIngestion: async (
        datasetId: string,
        versionId: string
    ): Promise<{ status: string; task_id: string; message: string }> => {
        const response = await api.post(
            `/datasets/${datasetId}/versions/${versionId}/retry-ingestion`
        );
        return response.data;
    },

    retryProcessing: async (
        datasetId: string,
        versionId: string
    ): Promise<{ status: string; task_id: string; message: string }> => {
        const response = await api.post(
            `/datasets/${datasetId}/versions/${versionId}/retry-processing`
        );
        return response.data;
    },
};

// =============================================================================
// Build Detail Types
// =============================================================================

export interface NodeExecutionDetail {
    node_name: string;
    status: string; // success, failed, skipped
    started_at: string | null;
    completed_at: string | null;
    duration_ms: number;
    features_extracted: string[];
    resources_used: string[];
    error: string | null;
    warning: string | null;
    skip_reason: string | null;
    retry_count: number;
}

export interface AuditLogDetail {
    id: string;
    correlation_id: string | null;
    started_at: string | null;
    completed_at: string | null;
    duration_ms: number | null;
    nodes_executed: number;
    nodes_succeeded: number;
    nodes_failed: number;
    nodes_skipped: number;
    total_retries: number;
    feature_count: number;
    features_extracted: string[];
    errors: string[];
    warnings: string[];
    node_results: NodeExecutionDetail[];
}

export interface RawBuildRunDetail {
    id: string;
    ci_run_id: string;
    build_number: number | null;
    repo_name: string;
    branch: string;
    commit_sha: string;
    commit_message: string | null;
    commit_author: string | null;
    status: string;
    conclusion: string;
    created_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    duration_seconds: number | null;
    web_url: string | null;
    provider: string;
    logs_available: boolean | null;
    logs_expired: boolean;
    is_bot_commit: boolean | null;
}

export interface EnrichmentBuildDetail {
    id: string;
    extraction_status: string;
    extraction_error: string | null;
    missing_resources: string[];
    skipped_features: string[];
    feature_count: number;
    expected_feature_count: number;
    features: Record<string, unknown>;
    scan_metrics: Record<string, unknown>;
    created_at: string | null;
    enriched_at: string | null;
}

export interface EnrichmentBuildDetailResponse {
    raw_build_run: RawBuildRunDetail;
    enrichment_build: EnrichmentBuildDetail;
    audit_log: AuditLogDetail | null;
}
