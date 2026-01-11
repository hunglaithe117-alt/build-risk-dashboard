import { DatasetTemplateListResponse, DatasetTemplateRecord } from "@/types";
import { api } from "./client";

export const templatesApi = {
    list: async () => {
        const response = await api.get<DatasetTemplateListResponse>("/templates");
        return response.data;
    },
    getByName: async (name: string) => {
        const response = await api.get<DatasetTemplateRecord>(`/templates/by-name/${name}`);
        return response.data;
    },
};
