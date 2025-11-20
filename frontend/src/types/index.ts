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
  import_status?: "queued" | "importing" | "imported" | "failed";
}

export interface RepoDetail extends RepositoryRecord {
  metadata?: Record<string, any>;
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

export interface RepoImportPayload {
  full_name: string;
  provider?: string;
  user_id?: string;
  installation_id?: string;
  test_frameworks?: string[];
  source_languages?: string[];
  ci_provider?: string;
}

export interface RepoUpdatePayload {
  ci_provider?: string;
  test_frameworks?: string[];
  source_languages?: string[];
  default_branch?: string;
  notes?: string;
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
