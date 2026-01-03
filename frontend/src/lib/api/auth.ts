import type {
    AuthVerifyResponse,
    GithubAuthorizeResponse,
    RefreshTokenResponse,
    UserAccount,
} from "@/types";
import { api } from "./client";

export const integrationApi = {
    verifyAuth: async () => {
        const response = await api.get<AuthVerifyResponse>("/auth/verify");
        return response.data;
    },
    startGithubOAuth: async (redirectPath?: string) => {
        const response = await api.post<GithubAuthorizeResponse>(
            "/auth/github/login",
            { redirect_path: redirectPath }
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
