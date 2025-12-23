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
  update: async (datasetId: string, payload: DatasetUpdatePayload) => {
    const response = await api.patch<DatasetRecord>(`/datasets/${datasetId}`, payload);
    return response.data;
  },
  cancelValidation: async (datasetId: string) => {
    const response = await api.delete<{ message: string; can_resume: boolean }>(
      `/datasets/${datasetId}/validation`
    );
    return response.data;
  },
  startValidation: async (datasetId: string) => {
    const response = await api.post<{ task_id: string; message: string }>(
      `/datasets/${datasetId}/validate`
    );
    return response.data;
  },
  getValidationSummary: async (datasetId: string) => {
    const response = await api.get<{
      dataset_id: string;
      status: string;
      stats: Record<string, number>;
      repos: Array<{
        id: string;
        raw_repo_id: string;
        full_name: string;
        ci_provider: string;
        validation_status: string;
        validation_error?: string | null;
        builds_total: number;
        builds_found: number;
        builds_not_found: number;
      }>;
    }>(`/datasets/${datasetId}/validation-summary`);
    return response.data;
  },
  // Paginated repo stats from separate collection
  getRepoStats: async (
    datasetId: string,
    params?: { skip?: number; limit?: number; q?: string }
  ) => {
    const response = await api.get<{
      items: Array<{
        id: string;
        raw_repo_id: string;
        full_name: string;
        is_valid: boolean;
        validation_status: string;
        validation_error?: string;
        builds_total: number;
        builds_found: number;
        builds_not_found: number;
        builds_filtered: number;
      }>;
      total: number;
      skip: number;
      limit: number;
    }>(`/datasets/${datasetId}/repos`, { params });
    return response.data;
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
      ci_providers: Array<{ value: string; label: string }>;
    }>("/features/config");
    return response.data;
  },
  getConfigRequirements: async (selectedFeatures: string[]) => {
    const response = await api.post<{
      fields: Array<{
        name: string;
        type: string;
        scope: string;
        required: boolean;
        description: string;
        default: unknown;
        options: string[] | null;
      }>;
    }>("/features/config-requirements", { selected_features: selectedFeatures });
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
  get: async (userId: string): Promise<UserAccount> => {
    const response = await api.get<UserAccount>(`/admin/users/${userId}`);
    return response.data;
  },
  update: async (userId: string, payload: UserUpdatePayload): Promise<UserAccount> => {
    const response = await api.patch<UserAccount>(`/admin/users/${userId}`, payload);
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
      `/repos/${repoId}/export/preview`,
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
    return `${baseUrl}/repos/${repoId}/export?${searchParams.toString()}`;
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
    const response = await api.get(`/repos/${repoId}/export`, {
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
      `/repos/${repoId}/export/async`,
      null,
      { params: { format, ...params } }
    );
    return response.data;
  },

  // Get job status
  getJobStatus: async (jobId: string): Promise<ExportJobResponse> => {
    const response = await api.get<ExportJobResponse>(`/repos/export/jobs/${jobId}`);
    return response.data;
  },

  // Download completed export
  downloadJob: async (jobId: string): Promise<Blob> => {
    const response = await api.get(`/repos/export/jobs/${jobId}/download`, {
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
      `/repos/${repoId}/export/jobs`,
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

// Dataset Version API
export interface EnrichedBuildData {
  id: string;
  raw_build_run_id: string;
  repo_full_name: string;
  extraction_status: string;
  feature_count: number;
  expected_feature_count: number;
  skipped_features: string[];
  missing_resources: string[];
  enriched_at: string | null;
  features: Record<string, unknown>;
}

export interface VersionDataResponse {
  version: {
    id: string;
    name: string;
    version_number: number;
    status: string;
    total_rows: number;
    enriched_rows: number;
    failed_rows: number;
    selected_features: string[];
    created_at: string | null;
    completed_at: string | null;
  };
  builds: EnrichedBuildData[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  column_stats?: Record<string, unknown>;
}

export const datasetVersionApi = {
  getVersionData: async (
    datasetId: string,
    versionId: string,
    page: number = 1,
    pageSize: number = 20,
    includeStats: boolean = true
  ): Promise<VersionDataResponse> => {
    const response = await api.get<VersionDataResponse>(
      `/datasets/${datasetId}/versions/${versionId}/data`,
      {
        params: {
          page,
          page_size: pageSize,
          include_stats: includeStats,
        },
      }
    );
    return response.data;
  },

  // Get export preview with row count and recommendation
  getExportPreview: async (datasetId: string, versionId: string) => {
    const response = await api.get<{
      total_rows: number;
      use_async_recommended: boolean;
      sample_features: string[];
    }>(`/datasets/${datasetId}/versions/${versionId}/preview`);
    return response.data;
  },

  // Stream export (for small datasets)
  getExportUrl: (
    datasetId: string,
    versionId: string,
    format: "csv" | "json" = "csv"
  ): string => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    return `${baseUrl}/datasets/${datasetId}/versions/${versionId}/export?format=${format}`;
  },

  // Download export as blob
  downloadExport: async (
    datasetId: string,
    versionId: string,
    format: "csv" | "json" = "csv",
    normalization: "none" | "minmax" | "zscore" | "robust" | "maxabs" | "log" | "decimal" = "none"
  ): Promise<Blob> => {
    const response = await api.get(
      `/datasets/${datasetId}/versions/${versionId}/export`,
      { params: { format, normalization }, responseType: "blob" }
    );
    return response.data;
  },

  // Create async export job (for large datasets)
  createExportJob: async (
    datasetId: string,
    versionId: string,
    format: "csv" | "json" = "csv",
    normalization: "none" | "minmax" | "zscore" | "robust" | "maxabs" | "log" | "decimal" = "none"
  ): Promise<{ job_id: string; status: string; total_rows: number }> => {
    const response = await api.post(
      `/datasets/${datasetId}/versions/${versionId}/export/async`,
      null,
      { params: { format, normalization } }
    );
    return response.data;
  },

  // Get export job status
  getExportJobStatus: async (datasetId: string, jobId: string): Promise<{
    id: string;
    status: "pending" | "processing" | "completed" | "failed";
    progress: number;
    error_message?: string;
  }> => {
    const response = await api.get<{
      id: string;
      status: string;
      format: string;
      total_rows: number;
      processed_rows: number;
      progress: number;
      file_path?: string;
      file_size?: number;
      error_message?: string;
      created_at?: string;
      completed_at?: string;
    }>(`/datasets/${datasetId}/versions/export/jobs/${jobId}`);
    // Map to ExportJobStatus format
    return {
      id: response.data.id,
      status: response.data.status as "pending" | "processing" | "completed" | "failed",
      progress: response.data.progress,
      error_message: response.data.error_message,
    };
  },

  // List export jobs for a version
  listExportJobs: async (datasetId: string, versionId: string) => {
    const response = await api.get<Array<{
      id: string;
      status: string;
      format: string;
      total_rows: number;
      processed_rows: number;
      file_size?: number;
      created_at?: string;
      completed_at?: string;
    }>>(`/datasets/${datasetId}/versions/${versionId}/export/jobs`);
    return response.data;
  },

  // Download completed export
  downloadExportJob: async (datasetId: string, jobId: string): Promise<Blob> => {
    const response = await api.get(
      `/datasets/${datasetId}/versions/export/jobs/${jobId}/download`,
      { responseType: "blob" }
    );
    return response.data;
  },
};

// Quality Evaluation API Types
export interface QualityIssue {
  severity: "info" | "warning" | "error";
  category: string;
  feature_name?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface QualityMetric {
  feature_name: string;
  data_type: string;
  total_values: number;
  null_count: number;
  completeness_pct: number;
  validity_pct: number;
  min_value?: number;
  max_value?: number;
  mean_value?: number;
  std_dev?: number;
  expected_range?: [number, number];
  out_of_range_count: number;
  invalid_value_count: number;
  issues: string[];
}

export interface QualityReport {
  id: string;
  dataset_id: string;
  version_id: string;
  status: "pending" | "running" | "completed" | "failed";
  error_message?: string;
  quality_score: number;
  completeness_score: number;
  validity_score: number;
  consistency_score: number;
  coverage_score: number;
  total_builds: number;
  enriched_builds: number;
  partial_builds: number;
  failed_builds: number;
  total_features: number;
  features_with_issues: number;
  feature_metrics: QualityMetric[];
  issues: QualityIssue[];
  issue_counts: Record<string, number>;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

export interface EvaluateQualityResponse {
  report_id: string;
  status: string;
  message: string;
  quality_score?: number;
}

// Quality Evaluation API
export const qualityApi = {
  // Trigger quality evaluation for a version
  evaluate: async (
    datasetId: string,
    versionId: string
  ): Promise<EvaluateQualityResponse> => {
    const response = await api.post<EvaluateQualityResponse>(
      `/datasets/${datasetId}/versions/${versionId}/evaluate`
    );
    return response.data;
  },

  // Get quality report for a version
  getReport: async (
    datasetId: string,
    versionId: string
  ): Promise<QualityReport | { available: false; message: string }> => {
    const response = await api.get<
      QualityReport | { available: false; message: string }
    >(`/datasets/${datasetId}/versions/${versionId}/quality-report`);
    return response.data;
  },
};

// User Settings types
export interface UserNotificationPreferences {
  email_on_version_complete: boolean;
  email_on_scan_complete: boolean;
  email_on_version_failed: boolean;
  browser_notifications: boolean;
}

export interface UserSettingsResponse {
  user_id: string;
  notification_preferences: UserNotificationPreferences;
  timezone: string;
  language: string;
  created_at: string;
  updated_at: string;
}

export interface UpdateUserSettingsRequest {
  notification_preferences?: Partial<UserNotificationPreferences>;
  timezone?: string;
  language?: string;
}

// User Settings API (personal preferences for each user)
export const userSettingsApi = {
  get: async (): Promise<UserSettingsResponse> => {
    const response = await api.get<UserSettingsResponse>("/user-settings");
    return response.data;
  },

  update: async (request: UpdateUserSettingsRequest): Promise<UserSettingsResponse> => {
    const response = await api.patch<UserSettingsResponse>("/user-settings", request);
    return response.data;
  },
};

// =============================================================================
// Statistics API Types and Functions
// =============================================================================

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

// Statistics API
export const statisticsApi = {
  // Get version statistics
  getVersionStatistics: async (
    datasetId: string,
    versionId: string
  ): Promise<VersionStatisticsResponse> => {
    const response = await api.get<VersionStatisticsResponse>(
      `/datasets/${datasetId}/versions/${versionId}/statistics`
    );
    return response.data;
  },

  // Get feature distributions
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

  // Get correlation matrix
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
};

export interface NodeExecutionResult {
  node_name: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  duration_ms: number;
  features_extracted: string[];
  feature_values: Record<string, unknown>;
  resources_used: string[];
  resources_missing: string[];
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

// Enrichment Logs API
export const enrichmentLogsApi = {
  // Get audit logs for version
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

  // Get audit log for specific build
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
