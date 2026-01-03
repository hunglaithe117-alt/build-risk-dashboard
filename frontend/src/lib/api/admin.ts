import type { UserAccount } from "@/types";
import { api } from "./client";

// Types
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

// Admin Users API
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

// Admin Repos API
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
