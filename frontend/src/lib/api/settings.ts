import type {
    ApplicationSettings,
    NotificationListResponse,
    UnreadCountResponse,
} from "@/types";
import { api } from "./client";

export const settingsApi = {
    get: async (): Promise<ApplicationSettings> => {
        const response = await api.get<ApplicationSettings>("/settings");
        return response.data;
    },

    update: async (settings: Partial<ApplicationSettings>): Promise<ApplicationSettings> => {
        const response = await api.patch<ApplicationSettings>("/settings", settings);
        return response.data;
    },

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
};

export const notificationsApi = {
    list: async (params?: {
        skip?: number;
        limit?: number;
        unread_only?: boolean;
        cursor?: string | null;
    }): Promise<NotificationListResponse> => {
        const response = await api.get<NotificationListResponse>("/notifications", { params });
        return response.data;
    },

    getUnreadCount: async (): Promise<number> => {
        const response = await api.get<UnreadCountResponse>("/notifications/unread-count");
        return response.data.count;
    },

    markAsRead: async (notificationId: string): Promise<void> => {
        await api.put(`/notifications/${notificationId}/read`);
    },

    markAllAsRead: async (): Promise<void> => {
        await api.put("/notifications/read-all");
    },
};
