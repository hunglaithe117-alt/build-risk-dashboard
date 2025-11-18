export interface Build {
  id: number;
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
  user_id: number;
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

export interface SystemSettings {
  auto_rescan_enabled: boolean;
  updated_at: string;
  updated_by: string;
}

export interface SystemSettingsUpdateRequest {
  auto_rescan_enabled?: boolean;
  updated_by?: string;
}

export interface ActivityLogEntry {
  _id: string;
  action: string;
  actor: string;
  scope: string;
  message: string;
  created_at: string;
  metadata: Record<string, string>;
}

export interface ActivityLogListResponse {
  logs: ActivityLogEntry[];
}

export interface NotificationPolicy {
  channels: string[];
  muted_repositories: string[];
  last_updated_at: string;
  last_updated_by: string;
}

export interface NotificationItem {
  _id: string;
  build_id: number;
  repository: string;
  branch: string;
  status: "new" | "sent" | "acknowledged";
  created_at: string;
  message: string;
}

export interface NotificationListResponse {
  notifications: NotificationItem[];
}

export interface NotificationPolicyUpdateRequest {
  channels?: string[];
  muted_repositories?: string[];
  updated_by: string;
}

export interface UserRoleDefinition {
  role: string;
  description: string;
  permissions: string[];
  admin_only: boolean;
}

export interface RoleListResponse {
  roles: UserRoleDefinition[];
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
