import axios from 'axios'
import type {
  BuildDetail,
  BuildListResponse,
  DashboardSummaryResponse,
  GithubIntegrationStatus,
  GithubAuthorizeResponse,
  PipelineStatus,
  GithubImportJob,
  GithubInstallation,
  GithubInstallationListResponse,
  SystemSettings,
  SystemSettingsUpdateRequest,
  ActivityLogListResponse,
  NotificationListResponse,
  NotificationPolicy,
  NotificationPolicyUpdateRequest,
  RoleListResponse,
  UserAccount,
} from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Build API
export const buildApi = {
  getAll: async (params?: { skip?: number; limit?: number; repository?: string; status?: string }) => {
    const response = await api.get<BuildListResponse>('/builds/', { params })
    return response.data
  },
  
  getById: async (id: string) => {
    const response = await api.get<BuildDetail>(`/builds/${id}`)
    return response.data
  },
  
  create: async (data: any) => {
    const response = await api.post('/builds/', data)
    return response.data
  },
  
  delete: async (id: string) => {
    const response = await api.delete(`/builds/${id}`)
    return response.data
  },
}

export const dashboardApi = {
  getSummary: async () => {
    const response = await api.get<DashboardSummaryResponse>('/dashboard/summary')
    return response.data
  },
}

export const integrationApi = {
  getGithubStatus: async () => {
    const response = await api.get<GithubIntegrationStatus>('/integrations/github')
    return response.data
  },
  startGithubOAuth: async (redirectPath?: string) => {
    const response = await api.post<GithubAuthorizeResponse>('/integrations/github/login', {
      redirect_path: redirectPath,
    })
    return response.data
  },
  revokeGithubToken: async () => {
    await api.post('/integrations/github/revoke')
  },
  getGithubImports: async () => {
    const response = await api.get<GithubImportJob[]>('/integrations/github/imports')
    return response.data
  },
  startGithubImport: async (payload: { repository: string; branch: string; initiated_by?: string; user_id?: number }) => {
    const response = await api.post<GithubImportJob>('/integrations/github/imports', payload)
    return response.data
  },
  listGithubInstallations: async () => {
    const response = await api.get<GithubInstallationListResponse>('/integrations/github/installations')
    return response.data
  },
  getGithubInstallation: async (installationId: string) => {
    const response = await api.get<GithubInstallation>(`/integrations/github/installations/${installationId}`)
    return response.data
  },
}

export const pipelineApi = {
  getStatus: async () => {
    const response = await api.get<PipelineStatus>('/pipeline/status')
    return response.data
  },
}

export const settingsApi = {
  get: async () => {
    const response = await api.get<SystemSettings>('/settings/')
    return response.data
  },
  update: async (payload: SystemSettingsUpdateRequest) => {
    const response = await api.put<SystemSettings>('/settings/', payload)
    return response.data
  },
}

export const logsApi = {
  list: async (limit = 50) => {
    const response = await api.get<ActivityLogListResponse>('/logs/', { params: { limit } })
    return response.data
  },
}

export const notificationsApi = {
  listEvents: async () => {
    const response = await api.get<NotificationListResponse>('/notifications/events')
    return response.data
  },
  getPolicy: async () => {
    const response = await api.get<NotificationPolicy>('/notifications/policy')
    return response.data
  },
  updatePolicy: async (payload: NotificationPolicyUpdateRequest) => {
    const response = await api.put<NotificationPolicy>('/notifications/policy', payload)
    return response.data
  },
}

export const usersApi = {
  listRoles: async () => {
    const response = await api.get<RoleListResponse>('/users/roles')
    return response.data
  },
  getCurrentUser: async () => {
    const response = await api.get<UserAccount>('/users/me')
    return response.data
  },
}

// Health API
export const healthApi = {
  check: async () => {
    const response = await api.get('/health')
    return response.data
  },
  
  checkDb: async () => {
    const response = await api.get('/health/db')
    return response.data
  },
}
