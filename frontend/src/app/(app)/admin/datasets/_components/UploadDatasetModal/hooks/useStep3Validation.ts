"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { ValidationStats, RepoValidationResultNew } from "@/types";
import { datasetValidationApi } from "@/lib/api";

type ValidationStatus = "pending" | "validating" | "completed" | "failed" | "cancelled";

interface UseStep3ValidationReturn {
    validationStatus: ValidationStatus;
    validationProgress: number;
    validationStats: ValidationStats | null;
    validationError: string | null;
    validatedRepos: RepoValidationResultNew[];
    startValidation: (datasetId: string) => Promise<void>;
    cancelValidation: (datasetId: string) => Promise<void>;
    loadValidationSummary: (datasetId: string) => Promise<void>;
    resetStep3: () => void;
    setValidationStatus: (status: ValidationStatus) => void;
}

export function useStep3Validation(): UseStep3ValidationReturn {
    const [validationStatus, setValidationStatus] = useState<ValidationStatus>("pending");
    const [validationProgress, setValidationProgress] = useState(0);
    const [validationStats, setValidationStats] = useState<ValidationStats | null>(null);
    const [validationError, setValidationError] = useState<string | null>(null);
    const [validatedRepos, setValidatedRepos] = useState<RepoValidationResultNew[]>([]);

    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

    const resetStep3 = useCallback(() => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
        setValidationStatus("pending");
        setValidationProgress(0);
        setValidationStats(null);
        setValidationError(null);
        setValidatedRepos([]);
    }, []);

    const loadValidationSummary = useCallback(async (datasetId: string) => {
        try {
            const summary = await datasetValidationApi.getSummary(datasetId);
            setValidationStats(summary.stats);
            setValidatedRepos(summary.repos);
        } catch (err) {
            console.error("Failed to load summary:", err);
        }
    }, []);

    const pollValidationStatus = useCallback(
        (datasetId: string) => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }

            pollIntervalRef.current = setInterval(async () => {
                try {
                    const status = await datasetValidationApi.getStatus(datasetId);
                    setValidationProgress(status.progress);

                    if (status.status === "completed") {
                        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                        setValidationStatus("completed");
                        setValidationStats(status.stats ?? null);
                        loadValidationSummary(datasetId);
                    } else if (status.status === "failed") {
                        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                        setValidationStatus("failed");
                        setValidationError(status.error || "Validation failed");
                    } else if (status.status === "cancelled") {
                        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                        setValidationStatus("cancelled");
                    }
                } catch (err) {
                    console.error("Failed to poll status:", err);
                    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                    setValidationStatus("failed");
                    setValidationError("Failed to get validation status");
                }
            }, 2000);
        },
        [loadValidationSummary]
    );

    const startValidation = useCallback(
        async (datasetId: string) => {
            setValidationStatus("validating");
            setValidationProgress(0);
            setValidationError(null);

            try {
                const result = await datasetValidationApi.start(datasetId);
                pollValidationStatus(datasetId);
            } catch (err) {
                setValidationStatus("failed");
                setValidationError(err instanceof Error ? err.message : "Failed to start validation");
            }
        },
        [pollValidationStatus]
    );

    const cancelValidation = useCallback(async (datasetId: string) => {
        try {
            await datasetValidationApi.cancel(datasetId);
            setValidationStatus("cancelled"); ``
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
        } catch (err) {
            setValidationStatus("failed");
            setValidationError(err instanceof Error ? err.message : "Failed to cancel validation");
        }
    }, []);

    useEffect(() => {
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, []);

    return {
        validationStatus,
        validationProgress,
        validationStats,
        validationError,
        validatedRepos,
        startValidation,
        cancelValidation,
        loadValidationSummary,
        resetStep3,
        setValidationStatus,
    };
}
