import type {
  BuildDetail,
  BuildListResponse,
  DashboardSummaryResponse,
  GithubAuthorizeResponse,
  GithubImportJob,
  GithubInstallation,
  GithubInstallationListResponse,
  PipelineStatus,
  RepoDetail,
  RepoImportPayload,
  RepoSuggestionResponse,
  RepoUpdatePayload,
  RepositoryRecord,
  UserAccount,
  AuthVerifyResponse,
  RefreshTokenResponse,
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

    // Check if error is 401 and we haven't already tried to refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
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
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Build API
export const buildApi = {
  getAll: async (params?: {
    skip?: number;
    limit?: number;
    repository?: string;
    status?: string;
  }) => {
    const response = await api.get<BuildListResponse>("/builds/", { params });
    return response.data;
  },

  getById: async (id: string) => {
    const response = await api.get<BuildDetail>(`/builds/${id}`);
    return response.data;
  },

  create: async (data: any) => {
    const response = await api.post("/builds/", data);
    return response.data;
  },

  delete: async (id: string) => {
    const response = await api.delete(`/builds/${id}`);
    return response.data;
  },
};

export const reposApi = {
  list: async () => {
    const response = await api.get<RepositoryRecord[]>("/repos/");
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
  scan: async (repoId: string, payload?: { initiated_by?: string }) => {
    const response = await api.post<GithubImportJob>(
      `/repos/${repoId}/scan`,
      payload ?? {}
    );
    return response.data;
  },
  listJobs: async (repoId: string) => {
    const response = await api.get<GithubImportJob[]>(`/repos/${repoId}/jobs`);
    return response.data;
  },
  import: async (payload: RepoImportPayload) => {
    const response = await api.post<RepositoryRecord>("/repos/import", payload);
    return response.data;
  },
  discover: async (query?: string) => {
    const response = await api.get<RepoSuggestionResponse>("/repos/available", {
      params: query ? { q: query } : undefined,
    });
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
  refreshToken: async () => {
    const response = await api.post<RefreshTokenResponse>("/auth/refresh");
    return response.data;
  },
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>("/auth/me");
    return response.data;
  },
  getGithubImports: async () => {
    const response = await api.get<GithubImportJob[]>(
      "/integrations/github/imports"
    );
    return response.data;
  },
  startGithubImport: async (payload: {
    repository: string;
    branch: string;
    initiated_by?: string;
    user_id?: string;
  }) => {
    const response = await api.post<GithubImportJob>(
      "/integrations/github/imports",
      payload
    );
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
};

export const pipelineApi = {
  getStatus: async () => {
    const response = await api.get<PipelineStatus>("/pipeline/status");
    return response.data;
  },
};

export const usersApi = {
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>("/users/me");
    return response.data;
  },
};
