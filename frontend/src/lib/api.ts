import type {
  // Settings types
  ApplicationSettings,
  AuthVerifyResponse,
  Build,
  BuildDetail,
  BuildListResponse,
  DashboardSummaryResponse,
  DatasetCreatePayload,
  DatasetListResponse,
  DatasetRecord,
  DatasetRepoConfigDto,
  DatasetTemplateListResponse,
  DatasetTemplateRecord,
  DatasetUpdatePayload,
  FeatureDAGResponse,
  FeatureListResponse,
  GithubAuthorizeResponse,
  GoogleAuthorizeResponse,
  GithubToken,
  RefreshTokenResponse,
  RepoDetail,
  RepoImportPayload,
  RepoListResponse,
  RepoSearchResponse,
  RepoSuggestionResponse,
  RepoUpdatePayload,
  RepositoryRecord,
  TokenCreatePayload,
  TokenListResponse,
  TokenPoolStatus,
  TokenUpdatePayload,
  TokenVerifyResponse,
  UserAccount
} from "@/types";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

// Token refresh flag to prevent multiple refresh attempts
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: any) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Types for standardized API response format
interface ApiSuccessResponse<T = any> {
  success: true;
  data: T;
  meta?: {
    request_id?: string;
    duration_ms?: number;
  };
}

interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Array<{
      field: string;
      message: string;
      type: string;
    }>;
    request_id?: string;
  };
  timestamp: string;
}

type ApiResponse<T = any> = ApiSuccessResponse<T> | ApiErrorResponse;

// Custom error class for API errors
export class ApiError extends Error {
  code: string;
  details?: Array<{ field: string; message: string; type: string }>;
  requestId?: string;
  statusCode?: number;

  constructor(
    message: string,
    code: string,
    details?: Array<{ field: string; message: string; type: string }>,
    requestId?: string,
    statusCode?: number
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.requestId = requestId;
    this.statusCode = statusCode;
  }
}

// Response interceptor to unwrap standardized response format
api.interceptors.response.use(
  (response) => {
    // Check if response is in new wrapped format
    const data = response.data;
    if (data && typeof data === "object" && "success" in data) {
      if (data.success === true && "data" in data) {
        // Unwrap successful response
        response.data = data.data;
      }
      // If success is false, it should have been caught by error interceptor
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    // Handle new standardized error format
    if (error.response?.data?.success === false && error.response?.data?.error) {
      const errorData = error.response.data as ApiErrorResponse;
      const apiError = new ApiError(
        errorData.error.message,
        errorData.error.code,
        errorData.error.details,
        errorData.error.request_id,
        error.response.status
      );
      error.apiError = apiError;
    }

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("/auth/refresh")
    ) {
      const authError = error.response?.headers?.["x-auth-error"];

      // Handle GitHub token errors - redirect to re-authenticate
      if (
        authError === "github_token_expired" ||
        authError === "github_token_revoked" ||
        authError === "github_not_connected"
      ) {
        // Don't retry, let the component handle re-authentication
        return Promise.reject(error);
      }

      // Handle JWT token expiration - try to refresh
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then(() => {
            return api(originalRequest);
          })
          .catch((err) => {
            return Promise.reject(err);
          });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Attempt to refresh the token
        await api.post<RefreshTokenResponse>("/auth/refresh");
        processQueue(null);
        isRefreshing = false;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        isRefreshing = false;
        // Redirect to login page
        if (typeof window !== "undefined" && window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Helper to extract error message from API error
export function getApiErrorMessage(error: any): string {
  // Check for new ApiError format
  if (error.apiError instanceof ApiError) {
    return error.apiError.message;
  }
  // Check for standardized error response
  if (error.response?.data?.error?.message) {
    return error.response.data.error.message;
  }
  // Fallback to axios error detail
  if (error.response?.data?.detail) {
    return error.response.data.detail;
  }
  // Generic message
  if (error.message) {
    return error.message;
  }
  return "An unexpected error occurred";
}

// Helper to get field-level validation errors
export function getValidationErrors(
  error: any
): Array<{ field: string; message: string }> | null {
  if (error.apiError instanceof ApiError && error.apiError.details) {
    return error.apiError.details.map((d: { field: string; message: string }) => ({
      field: d.field,
      message: d.message,
    }));
  }
  if (error.response?.data?.error?.details) {
    return error.response.data.error.details.map((d: any) => ({
      field: d.field,
      message: d.message,
    }));
  }
  return null;
}

export const buildApi = {
  getByRepo: async (
    repoId: string,
    params?: {
      skip?: number;
      limit?: number;
      q?: string;
    }
  ) => {
    const response = await api.get<BuildListResponse>(`/repos/${repoId}/builds`, {
      params,
    });
    return response.data;
  },

  getById: async (repoId: string, buildId: string) => {
    const response = await api.get<BuildDetail>(
      `/repos/${repoId}/builds/${buildId}`
    );
    return response.data;
  },

  reprocess: async (repoId: string, buildId: string) => {
    const response = await api.post<{ status: string; build_id: string; message: string }>(
      `/repos/${repoId}/builds/${buildId}/reprocess`
    );
    return response.data;
  },
};

export const reposApi = {
  list: async (params?: { skip?: number; limit?: number; q?: string }) => {
    const response = await api.get<RepoListResponse>("/repos/", { params });
    return response.data;
  },
  get: async (repoId: string) => {
    const response = await api.get<RepoDetail>(`/repos/${repoId}`);
    return response.data;
  },
  update: async (repoId: string, payload: RepoUpdatePayload) => {
    const response = await api.patch<RepoDetail>(`/repos/${repoId}`, payload);
    return response.data;
  },
  importBulk: async (payloads: RepoImportPayload[]) => {
    const response = await api.post<RepositoryRecord[]>("/repos/import/bulk", payloads);
    return response.data;
  },
  discover: async (query?: string, limit: number = 50) => {
    const response = await api.get<RepoSuggestionResponse>("/repos/available", {
      params: {
        q: query,
        limit,
      },
    });
    return response.data;
  },
  search: async (query?: string) => {
    const response = await api.get<RepoSearchResponse>("/repos/search", {
      params: { q: query },
    });
    return response.data;
  },

  triggerLazySync: async (repoId: string) => {
    const response = await api.post<{ status: string }>(
      `/repos/${repoId}/sync-run`
    );
    return response.data;
  },
  reprocessFeatures: async (repoId: string) => {
    const response = await api.post<{ status: string; message?: string }>(
      `/repos/${repoId}/reprocess-features`
    );
    return response.data;
  },
  // Note: triggerScan removed - scanning now done via pipeline SonarMeasuresNode
  detectLanguages: async (fullName: string) => {
    const response = await api.get<{ languages: string[] }>(`/repos/languages`, {
      params: { full_name: fullName },
    });
    return response.data;
  },
  delete: async (repoId: string) => {
    await api.delete(`/repos/${repoId}`);
  },
};

export const datasetsApi = {
  list: async (params?: { skip?: number; limit?: number; q?: string }) => {
    const response = await api.get<DatasetListResponse>("/datasets", { params });
    return response.data;
  },
  listTemplates: async () => {
    const response = await api.get<DatasetTemplateListResponse>("/templates");
    return response.data;
  },
  getTemplateByName: async (name: string) => {
    const response = await api.get<DatasetTemplateRecord>(`/templates/by-name/${encodeURIComponent(name)}`);
    return response.data;
  },
  get: async (datasetId: string) => {
    const response = await api.get<DatasetRecord>(`/datasets/${datasetId}`);
    return response.data;
  },
  create: async (payload: DatasetCreatePayload) => {
    const response = await api.post<DatasetRecord>("/datasets", payload);
    return response.data;
  },
  update: async (datasetId: string, payload: DatasetUpdatePayload) => {
    const response = await api.patch<DatasetRecord>(`/datasets/${datasetId}`, payload);
    return response.data;
  },
  upload: async (file: File, payload?: { name?: string; description?: string; }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (payload?.name) formData.append("name", payload.name);
    if (payload?.description) formData.append("description", payload.description);

    const response = await api.post<DatasetRecord>("/datasets/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },
  delete: async (datasetId: string) => {
    await api.delete(`/datasets/${datasetId}`);
  },
  listRepoConfigs: async (datasetId: string): Promise<DatasetRepoConfigDto[]> => {
    const response = await api.get<{ items: DatasetRepoConfigDto[]; total: number }>(`/datasets/${datasetId}/repos`);
    return response.data.items;
  },
};

export const featuresApi = {
  list: async (params?: {
    category?: string;
    source?: string;
    extractor_node?: string;
    is_active?: boolean;
  }) => {
    const response = await api.get<FeatureListResponse>("/features", { params });
    return response.data;
  },
  getDAG: async (selectedFeatures?: string[]) => {
    const params = selectedFeatures?.length
      ? { selected_features: selectedFeatures.join(",") }
      : undefined;
    const response = await api.get<FeatureDAGResponse>("/features/dag", { params });
    return response.data;
  },
  getConfig: async () => {
    const response = await api.get<{
      languages: string[];
      frameworks: string[];
      frameworks_by_language: Record<string, string[]>;
    }>("/features/config");
    return response.data;
  },
};

export const sonarApi = {
  // Deprecated stubs - scanning now done via pipeline
  listFailedScans: async (_repoId: string): Promise<{ items: [] }> => ({ items: [] }),
  updateFailedScanConfig: async (_scanId: string, _config: string): Promise<void> => { },
  listResults: async (_repoId: string): Promise<{ items: [] }> => ({ items: [] }),
  getConfig: async (_repoId: string): Promise<{ content: string }> => ({ content: '' }),
  updateConfig: async (_repoId: string, _content: string): Promise<void> => { },
};

export const dashboardApi = {
  getSummary: async () => {
    const response = await api.get<DashboardSummaryResponse>(
      "/dashboard/summary"
    );
    return response.data;
  },
  getRecentBuilds: async (limit: number = 10) => {
    const response = await api.get<Build[]>("/dashboard/recent-builds", {
      params: { limit },
    });
    return response.data;
  },
  // Dashboard layout methods
  getLayout: async (): Promise<DashboardLayoutResponse> => {
    const response = await api.get<DashboardLayoutResponse>("/dashboard/layout");
    return response.data;
  },
  saveLayout: async (layout: DashboardLayoutUpdateRequest): Promise<DashboardLayoutResponse> => {
    const response = await api.put<DashboardLayoutResponse>("/dashboard/layout", layout);
    return response.data;
  },
  getAvailableWidgets: async (): Promise<WidgetDefinition[]> => {
    const response = await api.get<WidgetDefinition[]>("/dashboard/available-widgets");
    return response.data;
  },
};

export const integrationApi = {
  verifyAuth: async () => {
    const response = await api.get<AuthVerifyResponse>("/auth/verify");
    return response.data;
  },
  startGithubOAuth: async (redirectPath?: string) => {
    const response = await api.post<GithubAuthorizeResponse>(
      "/auth/github/login",
      {
        redirect_path: redirectPath,
      }
    );
    return response.data;
  },
  startGoogleOAuth: async () => {
    const response = await api.post<GoogleAuthorizeResponse>(
      "/auth/google/login"
    );
    return response.data;
  },
  revokeGithubToken: async () => {
    await api.post("/auth/github/revoke");
  },
  logout: async () => {
    await api.post("/auth/logout");
  },
  refreshToken: async () => {
    const response = await api.post<RefreshTokenResponse>("/auth/refresh");
    return response.data;
  },
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>("/auth/me");
    return response.data;
  },

  // Removed GithubInstallation methods as we rely on backend config

};

export const usersApi = {
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>("/users/me");
    return response.data;
  },
  updateCurrentUser: async (payload: { name?: string; notification_email?: string | null }) => {
    const response = await api.patch<UserAccount>("/users/me", payload);
    return response.data;
  },
};

// Admin User Management API
export interface UserListResponse {
  items: UserAccount[];
  total: number;
}

export interface UserCreatePayload {
  email: string;
  name?: string;
  role?: "admin" | "user";
}

export interface UserUpdatePayload {
  email?: string;
  name?: string;
}

export interface UserRoleUpdatePayload {
  role: "admin" | "user";
}

export const adminUsersApi = {
  list: async (q?: string): Promise<UserListResponse> => {
    const response = await api.get<UserListResponse>("/admin/users", {
      params: q ? { q } : undefined,
    });
    return response.data;
  },
  create: async (payload: UserCreatePayload): Promise<UserAccount> => {
    const response = await api.post<UserAccount>("/admin/users", payload);
    return response.data;
  },
  get: async (userId: string): Promise<UserAccount> => {
    const response = await api.get<UserAccount>(`/admin/users/${userId}`);
    return response.data;
  },
  update: async (userId: string, payload: UserUpdatePayload): Promise<UserAccount> => {
    const response = await api.patch<UserAccount>(`/admin/users/${userId}`, payload);
    return response.data;
  },
  updateRole: async (userId: string, role: "admin" | "user"): Promise<UserAccount> => {
    const response = await api.patch<UserAccount>(`/admin/users/${userId}/role`, { role });
    return response.data;
  },
  delete: async (userId: string): Promise<void> => {
    await api.delete(`/admin/users/${userId}`);
  },
};

// Admin Invitations API
export interface Invitation {
  id: string;
  email: string;
  github_username?: string | null;
  status: "pending" | "accepted" | "expired" | "revoked";
  role: "admin" | "user";
  invited_by: string;
  expires_at: string;
  accepted_at?: string | null;
  created_at: string;
}

export interface InvitationListResponse {
  items: Invitation[];
  total: number;
}

export interface InvitationCreatePayload {
  email: string;
  github_username?: string;
  role?: "admin" | "user" | "guest";
}

export const adminInvitationsApi = {
  list: async (status?: string): Promise<InvitationListResponse> => {
    const response = await api.get<InvitationListResponse>("/admin/invitations", {
      params: status ? { status } : undefined,
    });
    return response.data;
  },
  create: async (payload: InvitationCreatePayload): Promise<Invitation> => {
    const response = await api.post<Invitation>("/admin/invitations", payload);
    return response.data;
  },
  get: async (invitationId: string): Promise<Invitation> => {
    const response = await api.get<Invitation>(`/admin/invitations/${invitationId}`);
    return response.data;
  },
  revoke: async (invitationId: string): Promise<Invitation> => {
    const response = await api.delete<Invitation>(`/admin/invitations/${invitationId}`);
    return response.data;
  },
};

// Admin Repository Access API
export interface RepoAccessSummary {
  id: string;
  full_name: string;
  visibility: string;
  granted_user_count: number;
  owner_id: string;
}

export interface RepoAccessListResponse {
  items: RepoAccessSummary[];
  total: number;
}

export interface RepoAccessResponse {
  repo_id: string;
  full_name: string;
  visibility: string;
  granted_users: UserAccount[];
}

export const adminReposApi = {
  list: async (params?: { skip?: number; limit?: number; visibility?: string }): Promise<RepoAccessListResponse> => {
    const response = await api.get<RepoAccessListResponse>("/admin/repos", { params });
    return response.data;
  },
  getAccess: async (repoId: string): Promise<RepoAccessResponse> => {
    const response = await api.get<RepoAccessResponse>(`/admin/repos/${repoId}/access`);
    return response.data;
  },
  grantAccess: async (repoId: string, userIds: string[]): Promise<RepoAccessResponse> => {
    const response = await api.post<RepoAccessResponse>(`/admin/repos/${repoId}/grant`, { user_ids: userIds });
    return response.data;
  },
  revokeAccess: async (repoId: string, userIds: string[]): Promise<RepoAccessResponse> => {
    const response = await api.post<RepoAccessResponse>(`/admin/repos/${repoId}/revoke`, { user_ids: userIds });
    return response.data;
  },
  updateVisibility: async (repoId: string, visibility: "public" | "private"): Promise<RepoAccessResponse> => {
    const response = await api.patch<RepoAccessResponse>(`/admin/repos/${repoId}/visibility`, { visibility });
    return response.data;
  },
};

export const tokensApi = {
  list: async (includeDisabled = false) => {
    const response = await api.get<TokenListResponse>("/tokens/", {
      params: { include_disabled: includeDisabled },
    });
    return response.data;
  },
  getStatus: async () => {
    const response = await api.get<TokenPoolStatus>("/tokens/status");
    return response.data;
  },
  create: async (payload: TokenCreatePayload) => {
    const response = await api.post<GithubToken>("/tokens/", payload);
    return response.data;
  },
  update: async (tokenId: string, payload: TokenUpdatePayload) => {
    const response = await api.patch<GithubToken>(`/tokens/${tokenId}`, payload);
    return response.data;
  },
  delete: async (tokenId: string) => {
    await api.delete(`/tokens/${tokenId}`);
  },
  verify: async (tokenId: string, rawToken: string) => {
    const response = await api.post<TokenVerifyResponse>(`/tokens/${tokenId}/verify`, {
      raw_token: rawToken,
    });
    return response.data;
  },
  refreshAll: async () => {
    const response = await api.post<{
      refreshed: number;
      failed: number;
      results: Array<{
        id: string;
        success: boolean;
        remaining?: number;
        limit?: number;
        error?: string;
      }>;
    }>("/tokens/refresh-all");
    return response.data;
  },
};

import type {
  EnrichmentJob,
  EnrichmentStartRequest,
  EnrichmentStartResponse,
  EnrichmentStatusResponse,
  EnrichmentValidateResponse,
} from "@/types";

export const enrichmentApi = {
  // Validate dataset for enrichment
  validate: async (datasetId: string): Promise<EnrichmentValidateResponse> => {
    const response = await api.post<EnrichmentValidateResponse>(
      `/datasets/${datasetId}/validate-enrichment`
    );
    return response.data;
  },

  start: async (
    datasetId: string,
    request: EnrichmentStartRequest
  ): Promise<EnrichmentStartResponse> => {
    const response = await api.post<EnrichmentStartResponse>(
      `/datasets/${datasetId}/enrich`,
      request
    );
    return response.data;
  },

  getStatus: async (datasetId: string): Promise<EnrichmentStatusResponse> => {
    const response = await api.get<EnrichmentStatusResponse>(
      `/datasets/${datasetId}/enrich/status`
    );
    return response.data;
  },

  cancel: async (datasetId: string): Promise<EnrichmentJob> => {
    const response = await api.post<EnrichmentJob>(
      `/datasets/${datasetId}/enrich/cancel`
    );
    return response.data;
  },

  listJobs: async (datasetId: string): Promise<EnrichmentJob[]> => {
    const response = await api.get<EnrichmentJob[]>(
      `/datasets/${datasetId}/enrich/jobs`
    );
    return response.data;
  },

  download: async (datasetId: string): Promise<Blob> => {
    const response = await api.get(`/datasets/${datasetId}/download`, {
      responseType: "blob",
    });
    return response.data;
  },

  getWebSocketUrl: (jobId: string): string => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    // Remove protocol and /api suffix to get just host:port
    const host = process.env.NEXT_PUBLIC_API_URL
      ?.replace(/^https?:\/\//, "")
      ?.replace(/\/api\/?$/, "") || "localhost:8000";
    return `${wsProtocol}//${host}/api/ws/enrichment/${jobId}`;
  },
};

export interface ExportPreviewResponse {
  total_rows: number;
  use_async_recommended: boolean;
  async_threshold: number;
  sample_rows: Record<string, any>[];
  available_features: string[];
  feature_count: number;
}

export interface ExportJobResponse {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  format: "csv" | "json";
  total_rows: number;
  processed_rows: number;
  progress_percent: number;
  file_size?: number;
  file_size_mb?: number;
  error_message?: string;
  created_at: string;
  completed_at?: string;
  download_url?: string;
}

export interface ExportAsyncResponse {
  job_id: string;
  status: string;
  estimated_rows: number;
  format: string;
  poll_url: string;
  message: string;
}

export interface ExportJobListItem {
  job_id: string;
  status: string;
  format: string;
  total_rows: number;
  file_size: number | null;
  created_at: string;
  completed_at: string | null;
  download_url: string | null;
}

export const exportApi = {
  preview: async (
    repoId: string,
    params?: {
      features?: string;
      start_date?: string;
      end_date?: string;
      build_status?: string;
    }
  ): Promise<ExportPreviewResponse> => {
    const response = await api.get<ExportPreviewResponse>(
      `/export/repos/${repoId}/preview`,
      { params }
    );
    return response.data;
  },

  // Stream export (for small datasets)
  // Returns a URL for downloading
  getStreamUrl: (
    repoId: string,
    format: "csv" | "json" = "csv",
    params?: {
      features?: string;
      start_date?: string;
      end_date?: string;
      build_status?: string;
    }
  ): string => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    const searchParams = new URLSearchParams();
    searchParams.set("format", format);
    if (params?.features) searchParams.set("features", params.features);
    if (params?.start_date) searchParams.set("start_date", params.start_date);
    if (params?.end_date) searchParams.set("end_date", params.end_date);
    if (params?.build_status) searchParams.set("build_status", params.build_status);
    return `${baseUrl}/export/repos/${repoId}?${searchParams.toString()}`;
  },

  // Download export via blob (for stream download with auth)
  downloadStream: async (
    repoId: string,
    format: "csv" | "json" = "csv",
    params?: {
      features?: string;
      start_date?: string;
      end_date?: string;
      build_status?: string;
    }
  ): Promise<Blob> => {
    const response = await api.get(`/export/repos/${repoId}`, {
      params: { format, ...params },
      responseType: "blob",
    });
    return response.data;
  },

  // Create async export job (for large datasets)
  createAsyncJob: async (
    repoId: string,
    format: "csv" | "json" = "csv",
    params?: {
      features?: string;
      start_date?: string;
      end_date?: string;
      build_status?: string;
    }
  ): Promise<ExportAsyncResponse> => {
    const response = await api.post<ExportAsyncResponse>(
      `/export/repos/${repoId}/async`,
      null,
      { params: { format, ...params } }
    );
    return response.data;
  },

  // Get job status
  getJobStatus: async (jobId: string): Promise<ExportJobResponse> => {
    const response = await api.get<ExportJobResponse>(`/export/jobs/${jobId}`);
    return response.data;
  },

  // Download completed export
  downloadJob: async (jobId: string): Promise<Blob> => {
    const response = await api.get(`/export/jobs/${jobId}/download`, {
      responseType: "blob",
    });
    return response.data;
  },

  // List export jobs for a repo
  listJobs: async (
    repoId: string,
    limit: number = 10
  ): Promise<{ items: ExportJobListItem[]; count: number }> => {
    const response = await api.get<{ items: ExportJobListItem[]; count: number }>(
      `/export/repos/${repoId}/jobs`,
      { params: { limit } }
    );
    return response.data;
  },
};


import type {
  DatasetValidationStatus,
  StartValidationResponse,
  ValidationSummary,
} from "@/types";

export const datasetValidationApi = {
  saveRepos: async (datasetId: string, repos: Array<{
    full_name: string;
    ci_provider: string;
    source_languages: string[];
    test_frameworks: string[];
    validation_status: string;
  }>): Promise<{ saved: number; message: string }> => {
    const response = await api.post<{ saved: number; message: string }>(
      `/datasets/${datasetId}/repos`,
      { repos }
    );
    return response.data;
  },

  start: async (datasetId: string): Promise<StartValidationResponse> => {
    const response = await api.post<StartValidationResponse>(
      `/datasets/${datasetId}/validate`
    );
    return response.data;
  },

  getStatus: async (datasetId: string): Promise<DatasetValidationStatus> => {
    const response = await api.get<DatasetValidationStatus>(
      `/datasets/${datasetId}/validation-status`
    );
    return response.data;
  },

  // Cancel ongoing validation
  cancel: async (datasetId: string): Promise<{ message: string }> => {
    const response = await api.delete<{ message: string }>(
      `/datasets/${datasetId}/validation`
    );
    return response.data;
  },

  // Get validation summary (after completion)
  getSummary: async (datasetId: string): Promise<ValidationSummary> => {
    const response = await api.get<ValidationSummary>(
      `/datasets/${datasetId}/validation-summary`
    );
    return response.data;
  },

  // Reset validation to allow re-running
  resetValidation: async (datasetId: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>(
      `/datasets/${datasetId}/reset-validation`
    );
    return response.data;
  },

  resetStep2: async (datasetId: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>(
      `/datasets/${datasetId}/reset-step2`
    );
    return response.data;
  },
};

import type {
  DashboardLayoutResponse,
  DashboardLayoutUpdateRequest,
  WidgetDefinition,
} from "@/types";

export const settingsApi = {
  // Get current settings
  get: async (): Promise<ApplicationSettings> => {
    const response = await api.get<ApplicationSettings>("/settings");
    return response.data;
  },

  // Update settings
  update: async (settings: Partial<ApplicationSettings>): Promise<ApplicationSettings> => {
    const response = await api.patch<ApplicationSettings>("/settings", settings);
    return response.data;
  },

  // Get available metrics for tools (grouped by category)
  getAvailableMetrics: async (): Promise<{
    sonarqube: {
      metrics: Record<string, Array<{ key: string; display_name: string; description: string; data_type: string }>>;
      all_keys: string[];
    };
    trivy: {
      metrics: Record<string, Array<{ key: string; display_name: string; description: string; data_type: string }>>;
      all_keys: string[];
    };
  }> => {
    const response = await api.get("/settings/available-metrics");
    return response.data;
  },

  // Dashboard layout moved to dashboardApi
  // Use dashboardApi.getLayout(), dashboardApi.saveLayout(), dashboardApi.getAvailableWidgets()
};

import type {
  NotificationListResponse,
  UnreadCountResponse
} from "@/types";

export const notificationsApi = {
  // List notifications for current user
  list: async (params?: {
    skip?: number;
    limit?: number;
    unread_only?: boolean;
  }): Promise<NotificationListResponse> => {
    const response = await api.get<NotificationListResponse>("/notifications", { params });
    return response.data;
  },

  // Get unread count
  getUnreadCount: async (): Promise<number> => {
    const response = await api.get<UnreadCountResponse>("/notifications/unread-count");
    return response.data.count;
  },

  // Mark single notification as read
  markAsRead: async (notificationId: string): Promise<void> => {
    await api.put(`/notifications/${notificationId}/read`);
  },

  // Mark all notifications as read
  markAllAsRead: async (): Promise<void> => {
    await api.put("/notifications/read-all");
  },
};

// ============================================================================
// Dataset Scan Results API
// ============================================================================

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

    // Convert to CSV
    const results = response.data.results as ScanResultItem[];
    if (results.length === 0) {
      alert("No results to export");
      return;
    }

    // Build CSV
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

    // Download
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `scan_${scanId}_results.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },
};
