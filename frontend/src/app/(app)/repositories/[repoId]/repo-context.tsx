"use client";

import { createContext, useContext } from "react";
import type { Build, RepoDetail } from "@/types";

export interface ImportProgress {
    checkpoint: {
        has_checkpoint: boolean;
        last_checkpoint_at: string | null;
        accepted_failed: number;
        stats: Record<string, number>;
        last_processed_build_number?: number | null;
        last_processed_ci_run_id?: string | null;
        pending_processing_count?: number;
    };
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
        missing_resource_retryable?: number;
        total: number;
    };
    resource_status?: Record<string, Record<string, number>>;
    training_builds: {
        pending: number;
        completed: number;
        partial: number;
        failed: number;
        total: number;
        with_prediction?: number;
        pending_prediction?: number;
        prediction_failed?: number;
    };
}

export interface RepoContextType {
    repo: RepoDetail | null;
    progress: ImportProgress | null;
    builds: Build[];
    loading: boolean;
    repoId: string;
    // Actions
    loadRepo: () => Promise<void>;
    loadProgress: () => Promise<void>;
    loadBuilds: () => Promise<void>;
    handleStartProcessing: () => Promise<void>;
    handleSync: () => Promise<void>;
    handleRetryIngestion: () => Promise<void>;
    handleRetryProcessing: () => Promise<void>;
    // Loading states
    startProcessingLoading: boolean;
    syncLoading: boolean;
    retryIngestionLoading: boolean;
    retryProcessingLoading: boolean;
}

export const RepoContext = createContext<RepoContextType | null>(null);

export function useRepo() {
    const ctx = useContext(RepoContext);
    if (!ctx) throw new Error("useRepo must be used within RepoLayout");
    return ctx;
}
