/**
 * Unified API module - Re-exports all API clients from their respective modules.
 * 
 * Usage:
 *   import { buildApi, reposApi, ... } from '@/lib/api';
 * 
 * Or import specific modules:
 *   import { buildApi } from '@/lib/api/builds';
 */

// Core client and utilities
export { api, ApiError, getApiErrorMessage, getValidationErrors } from './client';

// Domain-specific APIs
export { buildApi } from './builds';
export { dashboardApi } from './dashboard';
export { integrationApi, usersApi } from './auth';
export { reposApi } from './repos';
export { datasetsApi } from './datasets';
export { tokensApi } from './tokens';
export { featuresApi, sonarApi } from './features';
export { adminUsersApi, adminReposApi } from './admin';
export { enrichmentApi } from './enrichment';
export { exportApi } from './export';
export { datasetValidationApi } from './validation';
export { settingsApi, notificationsApi } from './settings';
export { datasetScanApi, datasetVersionApi } from './versions';
export { qualityApi, userSettingsApi } from './quality';
export { statisticsApi, enrichmentLogsApi } from './statistics';
export { preprocessingApi } from './preprocessing';

export type {
    NormalizationMethod,
    NormalizationPreviewRequest,
    FeatureStats,
    FeaturePreview,
    NormalizationPreviewResponse,
} from './preprocessing';

export type {
    UserListResponse,
    UserCreatePayload,
    UserUpdatePayload,
    UserRoleUpdatePayload,
    RepoAccessSummary,
    RepoAccessListResponse,
    RepoAccessResponse,
} from './admin';

export type {
    ExportPreviewResponse,
    ExportJobResponse,
    ExportAsyncResponse,
    ExportJobListItem,
} from './export';

export type {
    ScanResultItem,
    ScanResultsResponse,
    ScanSummaryResponse,
    EnrichedBuildData,
    ImportBuildItem,
    VersionDataResponse,
    NodeExecutionDetail,
    AuditLogDetail,
    RawBuildRunDetail,
    EnrichmentBuildDetail,
    EnrichmentBuildDetailResponse,
} from './versions';


export type {
    QualityIssue,
    QualityMetric,
    QualityReport,
    EvaluateQualityResponse,
    UserSettingsResponse,
    UpdateUserSettingsRequest,
} from './quality';

export type {
    VersionStatistics,
    BuildStatusBreakdown,
    FeatureCompleteness,
    VersionStatisticsResponse,
    HistogramBin,
    NumericStats,
    NumericDistribution,
    CategoricalValue,
    CategoricalDistribution,
    FeatureDistributionResponse,
    CorrelationPair,
    CorrelationMatrixResponse,
    NodeExecutionResult,
    FeatureAuditLogDto,
    AuditLogListResponse,
    MetricSummary,
    TrivySummary,
    SonarSummary,
    ScanSummary,
    ScanMetricsStatisticsResponse,
} from './statistics';

