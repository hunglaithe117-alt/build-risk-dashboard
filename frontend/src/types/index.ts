export interface Build {
  id: string;
  repository: string;
  branch: string;
  commit_sha: string;
  build_number: string;
  workflow_name?: string;
  status: string;
  conclusion?: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  author_name?: string;
  author_email?: string;
  url?: string;
  logs_url?: string;
  created_at: string;
  updated_at?: string;
  features?: Record<string, any>;
}

export interface BuildDetail extends Build {
  // extends base with related analytics
}

export interface BuildListResponse {
  total: number;
  skip: number;
  limit: number;
  builds: BuildDetail[];
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
  repository: string;
  builds: number;
}

export type RepoSyncStatus = "healthy" | "error" | "disabled";

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
  monitoring_enabled: boolean;
  sync_status: RepoSyncStatus;
  webhook_status: "active" | "inactive";
  ci_token_status: "valid" | "missing";
  tracked_branches: string[];
  total_builds_imported: number;
  last_sync_error?: string;
  notes?: string;
}

export interface RepoDetail extends RepositoryRecord {
  metadata?: Record<string, any>;
}

export interface RepoSuggestion {
  full_name: string;
  description?: string;
  default_branch?: string;
  private: boolean;
  owner?: string;
  installed: boolean;
  requires_installation: boolean;
  source: "owned" | "search";
}

export interface RepoSuggestionResponse {
  items: RepoSuggestion[];
}

export interface RepoImportPayload {
  full_name: string;
  provider?: string;
  user_id?: string;
  installation_id?: string;
}

export interface RepoUpdatePayload {
  ci_provider?: string;
  monitoring_enabled?: boolean;
  sync_status?: RepoSyncStatus;
  tracked_branches?: string[];
  webhook_status?: "active" | "inactive";
  ci_token_status?: "valid" | "missing";
  default_branch?: string;
  notes?: string;
}

export interface DashboardSummaryResponse {
  metrics: DashboardMetrics;
  trends: DashboardTrendPoint[];
  repo_distribution: RepoDistributionEntry[];
}

export interface GithubIntegrationRepository {
  name: string;
  lastSync: string | null;
  buildCount: number;
  status: "healthy" | "degraded" | "attention";
}

export interface GithubIntegrationStatus {
  connected: boolean;
  organization?: string | null;
  connectedAt?: string | null;
  scopes: string[];
  repositories: GithubIntegrationRepository[];
  lastSyncStatus: "success" | "warning" | "error";
  lastSyncMessage?: string | null;
  accountLogin?: string;
  accountName?: string;
  accountAvatarUrl?: string;
}

export interface GithubAuthorizeResponse {
  authorize_url: string;
  state: string;
}

export interface PipelineStage {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "blocked";
  percent_complete: number;
  duration_seconds?: number;
  items_processed?: number;
  started_at?: string;
  completed_at?: string;
  notes?: string;
  issues: string[];
}

export interface PipelineStatus {
  last_run: string;
  next_run: string;
  normalized_features: number;
  pending_repositories: number;
  anomalies_detected: number;
  stages: PipelineStage[];
}

export interface GithubImportJob {
  id: string;
  repository: string;
  branch: string;
  user_id?: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  builds_imported: number;
  commits_analyzed: number;
  tests_collected: number;
  initiated_by: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  last_error?: string;
  notes?: string;
}

export interface UserAccount {
  id: string;
  email: string;
  name?: string | null;
  role: "admin" | "user";
  created_at: string;
}

export interface GithubInstallation {
  _id: string;
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
