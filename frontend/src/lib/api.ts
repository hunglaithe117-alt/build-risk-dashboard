import type {
  Build,
  BuildDetail,
  BuildListResponse,
  DashboardSummaryResponse,
  GithubAuthorizeResponse,
  GithubInstallation,
  GithubInstallationListResponse,
  RepoDetail,
  RepoImportPayload,
  RepoListResponse,
  RepoSuggestionResponse,
  RepoSearchResponse,
  RepoUpdatePayload,
  RepositoryRecord,
  UserAccount,
  AuthVerifyResponse,
  RefreshTokenResponse,
  ScanJob,
  ScanResult,
  FailedScan,
  FeatureListResponse,
  FeatureDAGResponse,
  DatasetListResponse,
  DatasetCreatePayload,
  DatasetRecord,
  DatasetUpdatePayload,
  DatasetTemplateListResponse,
  GithubToken,
  TokenListResponse,
  TokenPoolStatus,
  TokenCreatePayload,
  TokenUpdatePayload,
  TokenVerifyResponse,
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

// Response interceptor to handle token expiration
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

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
  sync: async () => {
    const response = await api.post<RepoSuggestionResponse>("/repos/sync");
    return response.data;
  },
  triggerScan: async (repoId: string, buildId: string) => {
    const response = await api.post<{ status: string; job_id: string }>(
      `/repos/${repoId}/builds/${buildId}/scan`
    );
    return response.data;
  },
  detectLanguages: async (fullName: string) => {
    const response = await api.get<{ languages: string[] }>(`/repos/languages`, {
      params: { full_name: fullName },
    });
    return response.data;
  },
  getTestFrameworks: async () => {
    const response = await api.get<{ frameworks: string[]; by_language?: Record<string, string[]> }>(
      `/repos/test-frameworks`
    );
    return response.data;
  },
};

export const datasetsApi = {
  list: async (params?: { skip?: number; limit?: number; q?: string }) => {
    const response = await api.get<DatasetListResponse>("/datasets", { params });
    return response.data;
  },
  listTemplates: async () => {
    const response = await api.get<DatasetTemplateListResponse>("/datasets/templates");
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
  applyTemplate: async (datasetId: string, templateId: string) => {
    const response = await api.post<DatasetRecord>(
      `/datasets/${datasetId}/apply-template/${templateId}`
    );
    return response.data;
  },
  upload: async (file: File, payload?: { name?: string; description?: string; tags?: string[] }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (payload?.name) formData.append("name", payload.name);
    if (payload?.description) formData.append("description", payload.description);
    if (payload?.tags) {
      payload.tags.forEach((tag) => formData.append("tags", tag));
    }

    const response = await api.post<DatasetRecord>("/datasets/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
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
  getSupportedLanguages: async () => {
    const response = await api.get<{ languages: string[] }>("/features/languages");
    return response.data;
  },
};

export const sonarApi = {
  getConfig: async (repoId: string) => {
    const response = await api.get<{ content: string }>(`/repos/${repoId}/sonar/config`);
    return response.data;
  },
  updateConfig: async (repoId: string, content: string) => {
    const response = await api.post<{ status: string }>(
      `/repos/${repoId}/sonar/config`,
      { content }
    );
    return response.data;
  },
  listJobs: async (repoId: string, params?: { skip?: number; limit?: number }) => {
    const response = await api.get<{ items: ScanJob[]; total: number }>(
      `/repos/${repoId}/sonar/jobs`,
      { params }
    );
    return response.data;
  },
  retryJob: async (jobId: string) => {
    const response = await api.post<{ status: string; job_id: string }>(
      `/repos/sonar/jobs/${jobId}/retry`
    );
    return response.data;
  },
  listResults: async (repoId: string, params?: { skip?: number; limit?: number }) => {
    const response = await api.get<{ items: ScanResult[]; total: number }>(
      `/repos/${repoId}/sonar/results`,
      { params }
    );
    return response.data;
  },
  listFailedScans: async (repoId: string, params?: { skip?: number; limit?: number }) => {
    const response = await api.get<{ items: FailedScan[]; total: number }>(
      `/repos/${repoId}/sonar/failed`,
      { params }
    );
    return response.data;
  },
  updateFailedScanConfig: async (failedScanId: string, content: string) => {
    const response = await api.put<{ status: string; failed_scan_id: string }>(
      `/repos/sonar/failed/${failedScanId}/config`,
      { content }
    );
    return response.data;
  },
  retryFailedScan: async (failedScanId: string) => {
    const response = await api.post<{ status: string; job_id: string }>(
      `/repos/sonar/failed/${failedScanId}/retry`
    );
    return response.data;
  },
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

  listGithubInstallations: async () => {
    const response = await api.get<GithubInstallationListResponse>(
      "/integrations/github/installations"
    );
    return response.data;
  },
  getGithubInstallation: async (installationId: string) => {
    const response = await api.get<GithubInstallation>(
      `/integrations/github/installations/${installationId}`
    );
    return response.data;
  },
  syncInstallations: async () => {
    const response = await api.post<GithubInstallationListResponse>(
      "/integrations/github/sync"
    );
    return response.data;
  },
};

export const usersApi = {
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>("/users/me");
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
};
