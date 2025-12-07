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
  id: string;
  build_number: number;
  status: string; // GitHub workflow status: "success", "failure", etc.
  extraction_status: string; // Feature extraction process status: "pending", "completed", "failed"
  commit_sha: string;
  created_at?: string;
  duration?: number;
  num_jobs?: number;
  num_tests?: number;
  workflow_run_id: number;
  error_message?: string;
  is_missing_commit?: boolean;
}

export interface BuildDetail extends Build {
  git_diff_src_churn?: number;
  git_diff_test_churn?: number;
  gh_diff_files_added?: number;
  gh_diff_files_deleted?: number;
  gh_diff_files_modified?: number;
  gh_diff_tests_added?: number;
  gh_diff_tests_deleted?: number;
  gh_repo_age?: number;
  gh_repo_num_commits?: number;
  gh_sloc?: number;
  error_message?: string;
  // New Git Features
  git_prev_commit_resolution_status?: string;
  git_prev_built_commit?: string;
  tr_prev_build?: number;
  gh_team_size?: number;
  git_num_all_built_commits?: number;
  gh_by_core_team_member?: boolean;
  gh_num_commits_on_files_touched?: number;
}

export interface DatasetMapping {
  build_id?: string | null;
  commit_sha?: string | null;
  repo_name?: string | null;
  timestamp?: string | null;
}

export interface DatasetStats {
  coverage: number;
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
  source: string;
  rows: number;
  size_mb: number;
  columns: string[];
  mapped_fields: DatasetMapping;
  stats: DatasetStats;
  tags: string[];
  selected_template?: string | null;
  selected_features: string[];
  preview: DatasetPreviewRow[];
  created_at?: string;
  updated_at?: string | null;
}

export interface DatasetListResponse {
  total: number;
  skip: number;
  limit: number;
  items: DatasetRecord[];
}

export interface DatasetTemplateRecord {
  id: string;
  name: string;
  description?: string | null;
  file_name: string;
  source: string;
  rows: number;
  size_mb: number;
  columns: string[];
  mapped_fields: DatasetMapping;
  stats: DatasetStats;
  tags: string[];
  selected_template?: string | null;
  selected_features: string[];
  preview: DatasetPreviewRow[];
  created_at?: string;
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
  size_mb: number;
  columns: string[];
  description?: string | null;
  source?: string;
  mapped_fields?: DatasetMapping;
  stats?: DatasetStats;
  tags?: string[];
  selected_template?: string | null;
  selected_features?: string[];
  preview?: DatasetPreviewRow[];
}

export interface DatasetUpdatePayload {
  name?: string;
  description?: string | null;
  mapped_fields?: DatasetMapping;
  stats?: DatasetStats;
  tags?: string[];
  selected_template?: string | null;
  selected_features?: string[];
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
  installation_id?: string;
  ci_provider: string;
  test_frameworks: string[];
  source_languages: string[];
  total_builds_imported: number;
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
  PYTEST = "pytest",
  UNITTEST = "unittest",
  RSPEC = "rspec",
  MINITEST = "minitest",
  TESTUNIT = "testunit",
  CUCUMBER = "cucumber",
  JUNIT = "junit",
  TESTNG = "testng",
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
  TRAVIS_CI = "travis_ci",
}

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
  installation_id?: string;
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
  installation_id?: string;
  test_frameworks?: string[];
  source_languages?: string[];
  ci_provider?: string;
  feature_ids?: string[];
  max_builds?: number | null;
  ingest_start_date?: string | null;
  ingest_end_date?: string | null;
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
  created_at: string;
  github?: {
    connected: boolean;
    login?: string;
    name?: string;
    avatar_url?: string;
    token_status?: string;
  };
}

export interface GithubInstallation {
  id: string;
  installation_id: string;
  account_login?: string;
  account_type?: string; // "User" or "Organization"
  installed_at: string;
  revoked_at?: string | null;
  uninstalled_at?: string | null;
  suspended_at?: string | null;
  created_at: string;
}

export interface GithubInstallationListResponse {
  installations: GithubInstallation[];
}

export interface AuthVerifyResponse {
  authenticated: boolean;
  github_connected?: boolean;
  app_installed?: boolean;
  reason?: string;
  user?: {
    id: string;
    email: string;
    name?: string;
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
