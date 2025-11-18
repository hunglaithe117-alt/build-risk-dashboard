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
    const response = await api.get<{
      authenticated: boolean;
      reason?: string;
      user?: { id: string; email: string; name: string };
      github?: { login: string; name: string; avatar_url: string };
    }>("/auth/verify");
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
