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
