export interface SonarConfig {
  content: string;
}

export interface ScanResult {
  id: string;
  repo_id: string;
  job_id: string;
  sonar_project_key: string;
  metrics: Record<string, string | number>;
  created_at: string;
  updated_at: string;
}

export interface FailedScan {
  id: string;
  repo_id: string;
  build_id: string;
  job_id: string;
  commit_sha: string;
  reason: string;
  error_type: string;
  status: string;
  config_override?: string;
  config_source?: string;
  retry_count: number;
  resolved_at?: string;
  created_at: string;
  updated_at: string;
}

export interface Build {
  // Identity - using RawBuildRun._id
  id: string;

  // From RawBuildRun - always available after ingestion
  build_number?: number;
  build_id: string; // CI provider's build ID
  conclusion: string; // success, failure, cancelled, etc.
  commit_sha: string;
  branch: string;
  created_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  web_url?: string;

  // Logs info
  logs_available?: boolean;
  logs_expired: boolean;

  // Training enrichment from ModelTrainingBuild (optional)
  has_training_data: boolean;
  training_build_id?: string;
  extraction_status?: string; // pending, completed, failed, partial
  feature_count: number;
  extraction_error?: string;
  missing_resources?: string[];  // Resources unavailable during extraction
  skipped_features?: string[];   // Features skipped due to missing resources

  // Prediction
  predicted_label?: string;
  prediction_confidence?: number;
}

export interface BuildDetail extends Build {
  // Additional RawBuildRun fields
  commit_message?: string;
  commit_author?: string;
  provider: string;

  // Training features
  features: Record<string, unknown>;

  // Prediction results
  predicted_label?: string;
  prediction_confidence?: number;
  prediction_uncertainty?: number;
  predicted_at?: string;
  prediction_status?: string;
  prediction_error?: string;
}

export interface DatasetMapping {
  build_id?: string | null;
  repo_name?: string | null;
  commit_sha?: string | null;
}

export interface DatasetStats {
  missing_rate: number;
  duplicate_rate: number;
  build_coverage: number;
}

export type DatasetPreviewRow = Record<string, string | number>;

export interface BuildValidationFilters {
  exclude_bots: boolean;
  only_completed: boolean;
  allowed_conclusions: string[];
}

// Available build conclusions for multi-select
export const BUILD_CONCLUSION_OPTIONS = [
  { value: "success", label: "Success", description: "Build passed" },
  { value: "failure", label: "Failure", description: "Build failed" },
  { value: "cancelled", label: "Cancelled", description: "Build was cancelled" },
  { value: "skipped", label: "Skipped", description: "Build was skipped" },
  { value: "timed_out", label: "Timed Out", description: "Build timed out" },
  { value: "neutral", label: "Neutral", description: "No clear pass/fail" },
] as const;

export interface DatasetRecord {
  id: string;
  user_id?: string | null;
  name: string;
  description?: string | null;
  file_name: string;
  file_path?: string | null;
  source: string;
  rows: number;
  size_bytes: number;
  columns: string[];
  mapped_fields: DatasetMapping;
  stats: DatasetStats;
  ci_provider?: string | null;
  build_filters?: BuildValidationFilters;
  source_languages?: string[];
  test_frameworks?: string[];
  preview: DatasetPreviewRow[];
  created_at?: string;
  updated_at?: string | null;
  // Validation fields
  validation_status?: "pending" | "validating" | "completed" | "failed";
  validation_task_id?: string;
  validation_started_at?: string;
  validation_completed_at?: string;
  validation_progress?: number;
  validation_error?: string;
  validation_stats?: ValidationStats;
  setup_step?: number;
  versions_count?: number;
}

export interface DatasetListResponse {
  total: number;
  skip: number;
  limit: number;
  items: DatasetRecord[];
}

export interface RepoValidationItem {
  repo_name: string;
  status: "exists" | "not_found" | "error" | "invalid_format";
  build_count: number;
  message?: string | null;
}

export interface RepoValidationResponse {
  total_repos: number;
  valid_repos: number;
  invalid_repos: number;
  repos: RepoValidationItem[];
}

export interface DatasetRepoConfigDto {
  id: string;
  dataset_id: string;
  raw_repo_id?: string;
  normalized_full_name: string;
  repo_name_from_csv: string;
  validation_status: "pending" | "valid" | "not_found" | "error";
  validation_error?: string;
  source_languages: string[];
  test_frameworks: string[];
  ci_provider: string;
  default_branch?: string;
  builds_in_csv?: number;
  builds_found?: number;
  builds_not_found?: number;
}

export interface DatasetTemplateRecord {
  id: string;
  name: string;
  description?: string | null;
  feature_names: string[];
  tags: string[];
  source: string;
  created_at: string;
  updated_at?: string | null;
}

export interface DatasetTemplateListResponse {
  total: number;
  items: DatasetTemplateRecord[];
}

export interface DatasetCreatePayload {
  name: string;
  file_name: string;
  rows: number;
  size_bytes: number;
  columns: string[];
  description?: string | null;
  source?: string;
  mapped_fields?: DatasetMapping;
  stats?: DatasetStats;
  preview?: DatasetPreviewRow[];
}

export interface DatasetUpdatePayload {
  name?: string;
  description?: string | null;
  mapped_fields?: DatasetMapping;
  stats?: DatasetStats;
  ci_provider?: string | null;
  build_filters?: BuildValidationFilters;
  source_languages?: string[];
  test_frameworks?: string[];
  setup_step?: number;
}

export interface BuildListResponse {
  items: Build[];
  total: number;
  page: number;
  size: number;
}

// ============================================================================
// Import Build Types (Ingestion Phase)
// ============================================================================

export interface ResourceStatus {
  status: string; // pending, in_progress, completed, failed, skipped
  error?: string;
}

export interface ImportBuild {
  id: string;
  // Build basics from RawBuildRun
  build_number?: number;
  build_id: string;
  commit_sha: string;
  branch: string;
  conclusion: string;
  created_at?: string;
  web_url?: string;
  commit_message?: string;
  commit_author?: string;
  duration_seconds?: number;
  // Ingestion status from ModelImportBuild
  status: string; // pending, fetched, ingesting, ingested, missing_resource
  ingestion_started_at?: string;
  ingested_at?: string;
  // Resource status breakdown
  resource_status: Record<string, ResourceStatus>;
  required_resources: string[];
}

export interface ImportBuildListResponse {
  items: ImportBuild[];
  total: number;
  page: number;
  size: number;
}

// ============================================================================
// Training Build Types (Processing Phase)
// ============================================================================

export interface TrainingBuild {
  id: string;
  // Build basics
  build_number?: number;
  build_id: string;
  commit_sha: string;
  branch: string;
  conclusion: string;
  created_at?: string;
  web_url?: string;
  // Extraction status
  extraction_status: string; // pending, completed, failed, partial
  extraction_error?: string;
  extracted_at?: string;
  feature_count: number;
  skipped_features: string[];
  missing_resources: string[];
  // Prediction results
  predicted_label?: string;
  prediction_confidence?: number;
  prediction_uncertainty?: number;
  predicted_at?: string;
  prediction_status?: string;
  prediction_error?: string;
}

export interface TrainingBuildListResponse {
  items: TrainingBuild[];
  total: number;
  page: number;
  size: number;
}

// ============================================================================
// Unified Build Types (Combined Ingestion + Processing View)
// ============================================================================

export interface UnifiedBuild {
  // Identity - using ModelImportBuild._id
  model_import_build_id: string;
  // Build basics from RawBuildRun
  build_number?: number;
  ci_run_id?: string;
  commit_sha: string;
  branch: string;
  ci_conclusion: string;
  created_at?: string;
  web_url?: string;
  commit_message?: string;
  commit_author?: string;
  // Phase 2: Ingestion
  ingestion_status: string;
  resource_status: Record<string, ResourceStatus>;
  required_resources: string[];
  // Phase 3: Extraction (optional)
  training_build_id?: string;
  extraction_status?: string;
  feature_count: number;
  extraction_error?: string;
  // Phase 4: Prediction (optional)
  prediction_status?: string;
  predicted_label?: string;
  prediction_confidence?: number;
  prediction_uncertainty?: number;
}

export interface UnifiedBuildListResponse {
  items: UnifiedBuild[];
  total: number;
  page: number;
  size: number;
}

export interface DashboardMetrics {
  total_builds: number;
  success_rate: number;
  average_duration_minutes: number;
}

export interface DashboardTrendPoint {
  date: string;
  builds: number;
  failures: number;
}

export interface RepoDistributionEntry {
  id: string;
  repository: string;
  builds: number;
}


export interface RepositoryRecord {
  id: string;
  user_id?: string;
  provider: string;
  full_name: string;
  default_branch?: string;
  is_private: boolean;
  main_lang?: string;
  github_repo_id?: number;
  created_at: string;
  last_scanned_at?: string;
  ci_provider: string;
  test_frameworks: string[];
  source_languages: string[];
  // Stats
  builds_fetched: number;
  builds_ingested: number;
  builds_completed: number;
  builds_missing_resource: number;  // Ingestion phase failures
  builds_processing_failed: number; // Processing phase failures
  // Status
  status: "queued" | "fetching" | "ingesting" | "ingestion_complete" | "ingestion_partial" | "processing" | "imported" | "partial" | "failed";
  error_message?: string;
  last_synced_at?: string;
  notes?: string;
}

export interface RepoDetail extends RepositoryRecord {
  description?: string;
  html_url?: string;
  sonar_config?: string;
  metadata?: Record<string, any>;
}

export enum ScanJobStatus {
  PENDING = "pending",
  RUNNING = "running",
  SUCCESS = "success",
  FAILED = "failed",
}

export enum TestFramework {
  // Python
  PYTEST = "pytest",
  UNITTEST = "unittest",
  // Ruby
  RSPEC = "rspec",
  MINITEST = "minitest",
  TESTUNIT = "testunit",
  CUCUMBER = "cucumber",
  // Java
  JUNIT = "junit",
  TESTNG = "testng",
  // JavaScript/TypeScript
  JEST = "jest",
  MOCHA = "mocha",
  JASMINE = "jasmine",
  VITEST = "vitest",
  // Go
  GOTEST = "gotest",
  GOTESTSUM = "gotestsum",
  // C/C++
  GTEST = "gtest",
  CATCH2 = "catch2",
  CTEST = "ctest",
}

export type SourceLanguage = string;

export const SOURCE_LANGUAGE_PRESETS: SourceLanguage[] = [
  "python",
  "ruby",
  "java",
  "javascript",
  "typescript",
  "go",
  "php",
  "c++",
  "c#",
];

export enum CIProvider {
  GITHUB_ACTIONS = "github_actions",
  GITLAB_CI = "gitlab_ci",
  CIRCLECI = "circleci",
  TRAVIS_CI = "travis_ci",
}

// Human-readable labels for CI providers
export const CIProviderLabels: Record<CIProvider, string> = {
  [CIProvider.GITHUB_ACTIONS]: "GitHub Actions",
  [CIProvider.GITLAB_CI]: "GitLab CI",
  [CIProvider.CIRCLECI]: "CircleCI",
  [CIProvider.TRAVIS_CI]: "Travis CI",
};

// Interface for CI provider dropdown options
export interface CIProviderOption {
  value: string;
  label: string;
}

// Dropdown options for CI provider selection (single source of truth)
export const CI_PROVIDER_OPTIONS: CIProviderOption[] = [
  { value: CIProvider.GITHUB_ACTIONS, label: CIProviderLabels[CIProvider.GITHUB_ACTIONS] },
  { value: CIProvider.CIRCLECI, label: CIProviderLabels[CIProvider.CIRCLECI] },
  { value: CIProvider.TRAVIS_CI, label: CIProviderLabels[CIProvider.TRAVIS_CI] },
];

export interface ScanJob {
  id: string;
  repo_id: string;
  build_id: string;
  commit_sha: string;
  status: ScanJobStatus;
  worker_id?: string;
  started_at?: string;
  finished_at?: string;
  sonar_component_key?: string;
  error_message?: string;
  logs?: string;
  created_at: string;
  updated_at: string;
}

export interface RepoListResponse {
  total: number;
  skip: number;
  limit: number;
  items: RepositoryRecord[];
}

export interface RepoSuggestion {
  full_name: string;
  description?: string;
  default_branch?: string;
  private: boolean;
  owner?: string;
  html_url?: string;
  github_repo_id?: number;
}

export interface RepoSuggestionResponse {
  items: RepoSuggestion[];
}

export interface RepoSearchResponse {
  private_matches: RepoSuggestion[];
  public_matches: RepoSuggestion[];
}

export interface LazySyncPreviewResponse {
  has_updates: boolean;
  new_runs_count?: number;
  last_synced_at?: string;
  last_remote_check_at?: string;
  last_sync_status?: string;
}

export interface RepoImportPayload {
  full_name: string;
  provider?: string;
  user_id?: string;
  ci_provider?: string;
  feature_configs?: Record<string, unknown>;
  max_builds?: number | null;
  since_days?: number | null;
  only_with_logs?: boolean;
}

export interface RepoUpdatePayload {
  ci_provider?: string;
  test_frameworks?: string[];
  source_languages?: string[];
  default_branch?: string;
  notes?: string;
  feature_ids?: string[];
  max_builds?: number | null;
}

export interface FeatureDefinitionSummary {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  source: string;
  extractor_node: string;
  depends_on_features: string[];
  depends_on_resources: string[];
  data_type: string;
  nullable: boolean;
  is_active: boolean;
  is_deprecated: boolean;
  example_value?: string | null;
  unit?: string | null;
}

export interface FeatureListResponse {
  total: number;
  items: FeatureDefinitionSummary[];
}

// DAG Visualization Types
export interface DAGNode {
  id: string;
  type: "extractor" | "resource";
  label: string;
  features: string[];
  feature_count: number;
  requires_resources: string[];
  requires_features: string[];
  level: number;
}

export interface DAGEdge {
  id: string;
  source: string;
  target: string;
  type: "feature_dependency" | "resource_dependency";
}

export interface ExecutionLevel {
  level: number;
  nodes: string[];
}

export interface FeatureDAGResponse {
  nodes: DAGNode[];
  edges: DAGEdge[];
  execution_levels: ExecutionLevel[];
  total_features: number;
  total_nodes: number;
}

export interface DashboardSummaryResponse {
  metrics: DashboardMetrics;
  trends: DashboardTrendPoint[];
  repo_distribution: RepoDistributionEntry[];
  dataset_count: number;
}

export interface GithubAuthorizeResponse {
  authorize_url: string;
  state: string;
}

export interface UserAccount {
  id: string;
  email: string;
  name?: string | null;
  role: "admin" | "user";
  notification_email?: string | null;
  created_at: string;
  github?: {
    connected: boolean;
    login?: string;
    name?: string;
    avatar_url?: string;
    token_status?: string;
  };
}

export interface AuthVerifyResponse {
  authenticated: boolean;
  github_connected?: boolean;
  reason?: string;
  user?: {
    id: string;
    email: string;
    name?: string;
    role?: string;
    github_accessible_repos?: string[];
  };
  github?: {
    login?: string;
    name?: string;
    avatar_url?: string;
    scopes?: string;
  };
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type GithubTokenStatus = 'active' | 'rate_limited' | 'invalid' | 'disabled';

export interface GithubToken {
  id: string;
  masked_token: string;
  label: string;
  status: GithubTokenStatus;
  rate_limit_remaining: number | null;
  rate_limit_limit: number | null;
  rate_limit_reset_at: string | null;
  last_used_at: string | null;
  total_requests: number;
  created_at: string | null;
  last_validated_at: string | null;
  validation_error: string | null;
}

export interface TokenPoolStatus {
  total_tokens: number;
  active_tokens: number;
  rate_limited_tokens: number;
  invalid_tokens: number;
  disabled_tokens: number;
  estimated_requests_available: number;
  next_reset_at: string | null;
  pool_healthy: boolean;
}

export interface TokenListResponse {
  items: GithubToken[];
  total: number;
}

export interface TokenCreatePayload {
  token: string;
  label?: string;
}

export interface TokenUpdatePayload {
  label?: string;
  status?: 'active' | 'disabled';
}

export interface TokenVerifyResponse {
  valid: boolean;
  error?: string;
  rate_limit_remaining?: number;
  rate_limit_limit?: number;
}

// ============================================================================
// Pipeline Monitoring Types
// ============================================================================

export interface NodeExecutionResult {
  node_name: string;
  status: 'success' | 'failed' | 'skipped';
  duration_ms: number;
  features_extracted: string[];
  error?: string | null;
  warning?: string | null;
  retry_count: number;
}

export interface PipelineStats {
  total_runs: number;
  completed: number;
  failed: number;
  success_rate: number;
  avg_duration_ms: number;
  total_features: number;
  total_retries: number;
  avg_nodes_executed: number;
  period_days: number;
}

export interface DAGInfo {
  version: string;
  node_count: number;
  feature_count: number;
  nodes: string[];
  groups: string[];
}

// ============================================================================
// ENRICHMENT TYPES
// ============================================================================

export interface EnrichmentValidateResponse {
  valid: boolean;
  total_rows: number;
  enrichable_rows: number;
  repos_found: string[];
  repos_missing: string[];
  repos_invalid: string[];
  mapping_complete: boolean;
  missing_mappings: string[];
  errors: string[];
}

export interface EnrichmentStartRequest {
  selected_features: string[];
  auto_import_repos?: boolean;
  skip_existing?: boolean;
}

export interface EnrichmentStartResponse {
  job_id: string;
  status: string;
  message: string;
  websocket_url?: string;
}

export interface EnrichmentJob {
  id: string;
  dataset_id: string;
  status: "queued" | "ingesting" | "processing" | "ingested" | "processed" | "failed";
  builds_total: number;
  builds_ingested: number;
  builds_missing_resource: number;
  builds_processed: number;
  builds_processing_failed: number;
  progress_percent: number;
  selected_features: string[];
  started_at?: string;
  completed_at?: string;
  error?: string;
  output_file?: string;
  created_at?: string;
}

export interface EnrichmentStatusResponse {
  job_id: string;
  status: string;
  progress_percent: number;
  builds_processed: number;
  builds_total: number;
  builds_ingested: number;
  builds_missing_resource: number;
  error?: string;
  output_file?: string;
  estimated_time_remaining_seconds?: number;
}

// WebSocket event types
export interface EnrichmentProgressEvent {
  type: "progress";
  job_id: string;
  builds_processed: number;
  builds_total: number;
  builds_ingested: number;
  builds_missing_resource: number;
  progress_percent: number;
  current_repo?: string;
}

export interface EnrichmentCompleteEvent {
  type: "complete";
  job_id: string;
  status: string;
  builds_total: number;
  builds_processed: number;
  builds_processing_failed: number;
  output_file?: string;
  duration_seconds?: number;
}

export interface EnrichmentErrorEvent {
  type: "error";
  job_id: string;
  message: string;
  row_index?: number;
}

export type EnrichmentWebSocketEvent =
  | EnrichmentProgressEvent
  | EnrichmentCompleteEvent
  | EnrichmentErrorEvent
  | { type: "connected"; job_id: string }
  | { type: "heartbeat" };

export interface RepoValidationStats {
  full_name: string;
  ci_provider?: string;
  builds_total: number;
  builds_found: number;
  builds_not_found: number;
  builds_filtered: number;
  is_valid: boolean;
  error?: string;
}

export interface ValidationStats {
  repos_total: number;
  repos_valid: number;
  repos_invalid: number;
  repos_not_found: number;
  builds_total: number;
  builds_found: number;
  builds_not_found: number;
  builds_filtered?: number;
  repo_stats?: RepoValidationStats[];
}

export interface IngestionStats {
  builds_total: number;
  builds_ingested: number;
  builds_missing_resource: number;
  worktrees_created: number;
  logs_downloaded: number;
}

export interface DatasetValidationStatus {
  dataset_id: string;
  status: "pending" | "validating" | "completed" | "failed";
  progress: number;
  task_id?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  stats?: ValidationStats;
}

export interface RepoValidationResultNew {
  id: string;
  raw_repo_id?: string;
  github_repo_id?: number;  // Needed for per-repo scan config
  full_name: string;
  validation_status: "pending" | "valid" | "invalid" | "not_found" | "error";
  validation_error?: string;
  default_branch?: string;
  is_private: boolean;
  builds_found?: number;
  builds_not_found?: number;
}

export interface ValidationSummary {
  dataset_id: string;
  status: string;
  stats: ValidationStats;
  repos: RepoValidationResultNew[];
}

export interface StartValidationResponse {
  task_id: string;
  message: string;
}

// Settings types
export interface CircleCISettings {
  base_url: string;
  token?: string | null;
}

export interface TravisCISettings {
  base_url: string;
  token?: string | null;
}

export interface SonarQubeSettings {
  host_url: string;
  token?: string | null;
  webhook_secret?: string | null;
  default_config?: string | null;
}

export interface TrivySettings {
  server_url?: string | null;
  default_config?: string | null;
}

export interface EmailNotificationTypeToggles {
  pipeline_completed: boolean;
  pipeline_failed: boolean;
  dataset_validation_completed: boolean;
  dataset_enrichment_completed: boolean;
  rate_limit_warning: boolean;
  rate_limit_exhausted: boolean;
  system_alerts: boolean;
}

export interface NotificationSettings {
  email_enabled: boolean;
  email_recipients: string;
  email_type_toggles: EmailNotificationTypeToggles;
}

export interface ApplicationSettings {
  circleci: CircleCISettings;
  travis: TravisCISettings;
  sonarqube: SonarQubeSettings;
  trivy: TrivySettings;
  notifications: NotificationSettings;
}

// Dashboard Layout Types
export interface WidgetConfig {
  widget_id: string;
  widget_type: string;
  title: string;
  enabled: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayoutResponse {
  widgets: WidgetConfig[];
}

export interface DashboardLayoutUpdateRequest {
  widgets: WidgetConfig[];
}

export interface WidgetDefinition {
  widget_id: string;
  widget_type: string;
  title: string;
  description: string;
  default_w: number;
  default_h: number;
}

// ============================================================================
// Notification Types
// ============================================================================

export type NotificationType =
  | "pipeline_completed"
  | "pipeline_failed"
  | "dataset_import_completed"
  | "dataset_validation_completed"
  | "dataset_enrichment_completed"
  | "rate_limit_warning"
  | "rate_limit_exhausted"
  | "system";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  is_read: boolean;
  link?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  next_cursor?: string | null;
}

export interface UnreadCountResponse {
  count: number;
}
