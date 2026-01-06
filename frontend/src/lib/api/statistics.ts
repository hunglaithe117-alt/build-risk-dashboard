import { api } from "./client";

// Types
export interface VersionStatistics {
    total_builds: number;
    enriched_builds: number;
    failed_builds: number;
    partial_builds: number;
    enrichment_rate: number;
    success_rate: number;
    total_features_selected: number;
    avg_features_per_build: number;
    total_feature_values_extracted: number;
    quality_score?: number;
    completeness_score?: number;
    validity_score?: number;
    consistency_score?: number;
    coverage_score?: number;
    processing_duration_seconds?: number;
}

export interface BuildStatusBreakdown {
    status: string;
    count: number;
    percentage: number;
}

export interface FeatureCompleteness {
    feature_name: string;
    non_null_count: number;
    null_count: number;
    completeness_pct: number;
    data_type: string;
}

export interface VersionStatisticsResponse {
    version_id: string;
    dataset_id: string;
    version_name: string;
    status: string;
    statistics: VersionStatistics;
    build_status_breakdown: BuildStatusBreakdown[];
    feature_completeness: FeatureCompleteness[];
    started_at?: string;
    completed_at?: string;
    evaluated_at?: string;
}

export interface HistogramBin {
    min_value: number;
    max_value: number;
    count: number;
    percentage: number;
}

export interface NumericStats {
    min: number;
    max: number;
    mean: number;
    median: number;
    std: number;
    q1: number;
    q3: number;
    iqr: number;
}

export interface NumericDistribution {
    feature_name: string;
    data_type: string;
    total_count: number;
    null_count: number;
    bins: HistogramBin[];
    stats?: NumericStats;
}

export interface CategoricalValue {
    value: string;
    count: number;
    percentage: number;
}

export interface CategoricalDistribution {
    feature_name: string;
    data_type: string;
    total_count: number;
    null_count: number;
    unique_count: number;
    values: CategoricalValue[];
    truncated: boolean;
}

export interface FeatureDistributionResponse {
    version_id: string;
    distributions: Record<string, NumericDistribution | CategoricalDistribution>;
}

export interface CorrelationPair {
    feature_1: string;
    feature_2: string;
    correlation: number;
    strength: string;
}

export interface CorrelationMatrixResponse {
    version_id: string;
    features: string[];
    matrix: (number | null)[][];
    significant_pairs: CorrelationPair[];
}

export interface NodeExecutionResult {
    node_name: string;
    status: string;
    started_at?: string;
    completed_at?: string;
    duration_ms: number;
    features_extracted: string[];
    feature_values: Record<string, unknown>;
    resources_used: string[];
    error?: string;
    warning?: string;
    skip_reason?: string;
}

export interface FeatureAuditLogDto {
    id: string;
    correlation_id?: string;
    category: string;
    raw_repo_id: string;
    raw_build_run_id: string;
    enrichment_build_id?: string;
    status: string;
    started_at?: string;
    completed_at?: string;
    duration_ms?: number;
    node_results: NodeExecutionResult[];
    feature_count: number;
    features_extracted: string[];
    errors: string[];
    warnings: string[];
    nodes_executed: number;
    nodes_succeeded: number;
    nodes_failed: number;
    nodes_skipped: number;
    total_retries: number;
}

export interface AuditLogListResponse {
    items: FeatureAuditLogDto[];
    total: number;
    skip: number;
    limit: number;
}

// Scan Metrics Types
export interface MetricSummary {
    sum: number;
    avg: number;
    max: number;
    min: number;
    count: number;
}

export interface TrivySummary {
    vuln_total: MetricSummary;
    vuln_critical: MetricSummary;
    vuln_high: MetricSummary;
    vuln_medium: MetricSummary;
    vuln_low: MetricSummary;
    misconfig_total: MetricSummary;
    misconfig_critical: MetricSummary;
    misconfig_high: MetricSummary;
    misconfig_medium: MetricSummary;
    misconfig_low: MetricSummary;
    secrets_count: MetricSummary;
    scan_duration_ms: MetricSummary;
    has_critical_count: number;
    has_high_count: number;
    total_scans: number;
}

export interface SonarSummary {
    bugs: MetricSummary;
    code_smells: MetricSummary;
    vulnerabilities: MetricSummary;
    security_hotspots: MetricSummary;
    complexity: MetricSummary;
    cognitive_complexity: MetricSummary;
    duplicated_lines_density: MetricSummary;
    ncloc: MetricSummary;
    reliability_rating_avg: number | null;
    security_rating_avg: number | null;
    maintainability_rating_avg: number | null;
    alert_status_ok_count: number;
    alert_status_error_count: number;
    total_scans: number;
}

export interface ScanSummary {
    total_builds: number;
    builds_with_trivy: number;
    builds_with_sonar: number;
    builds_with_any_scan: number;
    trivy_coverage_pct: number;
    sonar_coverage_pct: number;
}

export interface ScanMetricsStatisticsResponse {
    version_id: string;
    dataset_id: string;
    scan_summary: ScanSummary;
    trivy_summary: TrivySummary;
    sonar_summary: SonarSummary;
}

export const statisticsApi = {
    getVersionStatistics: async (
        datasetId: string,
        versionId: string
    ): Promise<VersionStatisticsResponse> => {
        const response = await api.get<VersionStatisticsResponse>(
            `/datasets/${datasetId}/versions/${versionId}/statistics`
        );
        return response.data;
    },

    getDistributions: async (
        datasetId: string,
        versionId: string,
        options?: {
            features?: string[];
            bins?: number;
            top_n?: number;
        }
    ): Promise<FeatureDistributionResponse> => {
        const response = await api.get<FeatureDistributionResponse>(
            `/datasets/${datasetId}/versions/${versionId}/statistics/distributions`,
            {
                params: {
                    features: options?.features?.join(","),
                    bins: options?.bins,
                    top_n: options?.top_n,
                },
            }
        );
        return response.data;
    },

    getCorrelation: async (
        datasetId: string,
        versionId: string,
        features?: string[]
    ): Promise<CorrelationMatrixResponse> => {
        const response = await api.get<CorrelationMatrixResponse>(
            `/datasets/${datasetId}/versions/${versionId}/statistics/correlation`,
            {
                params: features ? { features: features.join(",") } : undefined,
            }
        );
        return response.data;
    },

    getScanMetrics: async (
        datasetId: string,
        versionId: string
    ): Promise<ScanMetricsStatisticsResponse> => {
        const response = await api.get<ScanMetricsStatisticsResponse>(
            `/datasets/${datasetId}/versions/${versionId}/statistics/scans`
        );
        return response.data;
    },
};

export const enrichmentLogsApi = {
    getAuditLogs: async (
        datasetId: string,
        versionId: string,
        options?: { skip?: number; limit?: number; status?: string }
    ): Promise<AuditLogListResponse> => {
        const response = await api.get<AuditLogListResponse>(
            `/datasets/${datasetId}/versions/${versionId}/audit-logs`,
            {
                params: {
                    skip: options?.skip,
                    limit: options?.limit,
                    status: options?.status,
                },
            }
        );
        return response.data;
    },

    getBuildAuditLog: async (
        datasetId: string,
        versionId: string,
        buildId: string
    ): Promise<FeatureAuditLogDto> => {
        const response = await api.get<FeatureAuditLogDto>(
            `/datasets/${datasetId}/versions/${versionId}/builds/${buildId}/audit-log`
        );
        return response.data;
    },
};
