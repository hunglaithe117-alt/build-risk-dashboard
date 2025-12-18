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
  jobs_count: number;
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
}

export interface BuildDetail extends Build {
  // Additional RawBuildRun fields
  commit_message?: string;
  commit_author?: string;
  started_at?: string;
  jobs_metadata: Array<Record<string, unknown>>;
  provider: string;

  // Training features
  features: Record<string, unknown>;
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
  source_languages?: string[];
  test_frameworks?: string[];
  preview: DatasetPreviewRow[];
  created_at?: string;
  updated_at?: string | null;
  // Build validation fields (Step 3)
  validation_status?: "pending" | "validating" | "completed" | "failed" | "cancelled";
  validation_task_id?: string;
  validation_started_at?: string;
  validation_completed_at?: string;
  validation_progress?: number;
  validation_error?: string;
  validation_stats?: ValidationStats;
  // Repo validation fields (during upload, before Step 2)
  repo_validation_status?: "pending" | "validating" | "completed" | "failed";
  repo_validation_task_id?: string;
  repo_validation_error?: string;
  // Setup progress tracking (1=uploaded, 2=configured, 3=validated)
  setup_step?: number;
  // Aggregated enrichment info (computed from enrichment_jobs)
  enrichment_jobs_count?: number;
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
  total_builds_imported: number;
  total_builds_processed: number;
  total_builds_failed: number;
  last_sync_error?: string;
  notes?: string;
  import_status: "queued" | "importing" | "imported" | "failed";
  // Lazy Sync
  last_synced_at?: string;
  last_sync_status?: string;
  last_remote_check_at?: string;
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
  test_frameworks?: string[];
  source_languages?: string[];
  ci_provider?: string;
  /** @deprecated TravisTorrent features are now always applied server-side */
  feature_names?: string[];
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

export interface PipelineRun {
  id: string;
  build_sample_id: string;
  repo_id: string;
  workflow_run_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  feature_count: number;
  nodes_executed: number;
  nodes_failed: number;
  nodes_skipped: number;
  total_retries: number;
  dag_version?: string | null;
  errors: string[];
  warnings: string[];
  created_at: string;
}

export interface PipelineRunDetail extends PipelineRun {
  features_extracted: string[];
  node_results: NodeExecutionResult[];
}

export interface PipelineRunListResponse {
  items: PipelineRun[];
  total: number;
  skip: number;
  limit: number;
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
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total_rows: number;
  processed_rows: number;
  enriched_rows: number;
  failed_rows: number;
  skipped_rows: number;
  progress_percent: number;
  selected_features: string[];
  repos_auto_imported: string[];
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
  processed_rows: number;
  total_rows: number;
  enriched_rows: number;
  failed_rows: number;
  repos_auto_imported: string[];
  error?: string;
  output_file?: string;
  estimated_time_remaining_seconds?: number;
}

// WebSocket event types
export interface EnrichmentProgressEvent {
  type: "progress";
  job_id: string;
  processed_rows: number;
  total_rows: number;
  enriched_rows: number;
  failed_rows: number;
  progress_percent: number;
  current_repo?: string;
}

export interface EnrichmentCompleteEvent {
  type: "complete";
  job_id: string;
  status: string;
  total_rows: number;
  enriched_rows: number;
  failed_rows: number;
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

export interface ValidationStats {
  repos_total: number;
  repos_valid: number;
  repos_invalid: number;
  repos_not_found: number;
  builds_total: number;
  builds_found: number;
  builds_not_found: number;
}

export interface IngestionStats {
  repos_total: number;
  repos_ingested: number;
  repos_failed: number;
  builds_total: number;
  worktrees_created: number;
  logs_downloaded: number;
}

export interface DatasetValidationStatus {
  dataset_id: string;
  status: "pending" | "validating" | "completed" | "failed" | "cancelled";
  progress: number;
  task_id?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  stats?: ValidationStats;
}

export interface RepoValidationResultNew {
  id: string;
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
  enabled: boolean;
  base_url: string;
  token?: string | null;
}

export interface TravisCISettings {
  enabled: boolean;
  base_url: string;
  token?: string | null;
}

export interface SonarQubeSettings {
  enabled: boolean;
  host_url: string;
  token?: string | null;
  default_project_key: string;
  webhook_secret?: string | null;
  webhook_public_url?: string | null;
  enabled_metrics: string[];
}

export interface TrivySettings {
  enabled: boolean;
  severity: string;
  timeout: number;
  skip_dirs: string;
  async_threshold: number;
  enabled_metrics: string[];
}

export interface NotificationSettings {
  email_enabled: boolean;
  email_recipients: string;
  slack_enabled: boolean;
  slack_webhook_url?: string | null;
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
  | "scan_completed"
  | "scan_vulnerabilities_found"
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
}

export interface UnreadCountResponse {
  count: number;
}
