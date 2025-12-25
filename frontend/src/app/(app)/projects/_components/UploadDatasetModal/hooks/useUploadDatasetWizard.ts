"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { DatasetRecord, CIProvider, ValidationStats } from "@/types";
import { datasetsApi } from "@/lib/api";
import type { Step } from "../types";
import { useStep1Upload } from "./useStep1Upload";

interface UseUploadDatasetWizardProps {
    open: boolean;
    existingDataset?: DatasetRecord;
    onSuccess: (dataset: DatasetRecord) => void;
    onOpenChange: (open: boolean) => void;
    onDatasetCreated?: (dataset: DatasetRecord) => void;
}

/**
 * Simplified 2-step upload wizard.
 *
 * Step 1: Upload CSV + Map columns + Select CI Provider
 * Step 2: Validate repos + builds (unified task)
 */
export function useUploadDatasetWizard({
    open,
    existingDataset,
    onSuccess,
    onOpenChange,
    onDatasetCreated,
}: UseUploadDatasetWizardProps) {
    const [step, setStep] = useState<Step>(1);
    const [createdDataset, setCreatedDataset] = useState<DatasetRecord | null>(null);
    const [datasetId, setDatasetId] = useState<string | null>(null);
    const [isResuming, setIsResuming] = useState(false);
    const [uploading, setUploading] = useState(false);

    // Validation state (for Step 2)
    const [validationStatus, setValidationStatus] = useState<
        "pending" | "validating" | "completed" | "failed" | "cancelled"
    >("pending");
    const [validationProgress, setValidationProgress] = useState(0);
    const [validationStats, setValidationStats] = useState<ValidationStats | null>(null);
    const [validationError, setValidationError] = useState<string | null>(null);

    // Use ref for polling to avoid stale closure issues
    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Step 1 hook
    const step1 = useStep1Upload();

    // Stop polling helper
    const stopPolling = useCallback(() => {
        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
        }
    }, []);

    const resetAll = useCallback(() => {
        setStep(1);
        setCreatedDataset(null);
        setDatasetId(null);
        setIsResuming(false);
        setUploading(false);
        setValidationStatus("pending");
        setValidationProgress(0);
        setValidationStats(null);
        setValidationError(null);
        stopPolling();
        step1.resetStep1();
    }, [step1, stopPolling]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            stopPolling();
        };
    }, [stopPolling]);

    // Poll validation status
    const pollValidationStatus = useCallback(async (dsId: string) => {
        try {
            const dataset = await datasetsApi.get(dsId);
            setValidationStatus(dataset.validation_status || "pending");
            setValidationProgress(dataset.validation_progress || 0);
            if (dataset.validation_stats) {
                setValidationStats(dataset.validation_stats);
            }
            if (dataset.validation_error) {
                setValidationError(dataset.validation_error);
            }
            setCreatedDataset(dataset);

            // Stop polling on completion
            if (["completed", "failed", "cancelled"].includes(dataset.validation_status || "")) {
                stopPolling();
            }
        } catch (err) {
            console.error("Failed to poll validation status:", err);
        }
    }, [stopPolling]);

    // Start polling for validation status
    const startValidationPolling = useCallback((dsId: string) => {
        // Clear existing interval
        stopPolling();

        // Initial poll
        pollValidationStatus(dsId);

        // Start interval
        const interval = setInterval(() => {
            pollValidationStatus(dsId);
        }, 2000);

        pollingIntervalRef.current = interval;
    }, [pollValidationStatus, stopPolling]);

    // Load existing dataset when modal opens in resume mode
    useEffect(() => {
        if (!open) {
            resetAll();
            return;
        }

        if (!existingDataset) return;

        setIsResuming(true);
        setCreatedDataset(existingDataset);
        setDatasetId(existingDataset.id);
        step1.loadFromExistingDataset(existingDataset);

        const validationStatus = existingDataset.validation_status;

        if (validationStatus && ["validating", "completed", "failed", "cancelled"].includes(validationStatus)) {
            setStep(2);
            setValidationStatus(validationStatus as typeof validationStatus);
            setValidationProgress(existingDataset.validation_progress || 0);
            if (existingDataset.validation_stats) {
                setValidationStats(existingDataset.validation_stats);
            }
            if (validationStatus === "validating") {
                startValidationPolling(existingDataset.id);
            }
        } else {
            setStep(1);
        }
    }, [open, existingDataset]);

    // Step 1 -> Step 2: Upload/Update and start validation
    const proceedToStep2 = async () => {
        if (!step1.file && !createdDataset) return;
        if (!step1.isMappingValid) return;

        setUploading(true);
        step1.setError(null);

        try {
            let dataset: DatasetRecord;

            // Prepare mapped fields based on CI provider mode
            const mappedFields = {
                build_id: step1.mappings.build_id || null,
                repo_name: step1.mappings.repo_name || null,
                ci_provider: step1.ciProviderMode === "column" ? step1.ciProviderColumn : null,
            };

            // Only set ci_provider (single mode) if not using column mapping
            const ciProviderValue = step1.ciProviderMode === "single" ? step1.ciProvider : null;

            if (createdDataset?.id) {
                // Update existing dataset with mappings and CI provider
                dataset = await datasetsApi.update(createdDataset.id, {
                    mapped_fields: mappedFields,
                    ci_provider: ciProviderValue,
                    build_filters: step1.buildFilters,
                });
                setCreatedDataset(dataset);
            } else if (step1.file) {
                // Upload new dataset - backend triggers validation automatically
                dataset = await datasetsApi.upload(step1.file, {
                    name: step1.name || step1.file.name.replace(/\.csv$/i, ""),
                    description: step1.description || undefined,
                });

                // Update with mappings and CI provider
                dataset = await datasetsApi.update(dataset.id, {
                    mapped_fields: mappedFields,
                    ci_provider: ciProviderValue,
                    build_filters: step1.buildFilters,
                });

                setCreatedDataset(dataset);
                setDatasetId(dataset.id);
                onDatasetCreated?.(dataset);
            } else {
                throw new Error("No file to upload");
            }

            // Start the validation process explicitly
            await datasetsApi.startValidation(dataset.id);

            // Move to Step 2 and start polling
            setStep(2);
            setValidationStatus("validating");
            startValidationPolling(dataset.id);
        } catch (err) {
            console.error("Upload failed:", err);
            step1.setError(err instanceof Error ? err.message : "Failed to upload dataset");
        } finally {
            setUploading(false);
        }
    };

    // Final submission - close modal on success
    const handleSubmit = async () => {
        if (!createdDataset) return;

        if (validationStatus !== "completed") {
            step1.setError("Validation must complete before submitting");
            return;
        }

        onSuccess(createdDataset);
        onOpenChange(false);
        resetAll();
    };

    // Cancel validation (if running)
    const cancelValidation = useCallback(async () => {
        if (!datasetId) return;

        try {
            await datasetsApi.cancelValidation(datasetId);
            stopPolling();
            setValidationStatus("cancelled");
        } catch (err) {
            console.error("Failed to cancel validation:", err);
        }
    }, [datasetId, stopPolling]);

    // Resume validation after cancel
    const resumeValidation = useCallback(async () => {
        if (!datasetId) return;

        try {
            await datasetsApi.startValidation(datasetId);
            setValidationStatus("validating");
            setValidationError(null);
            startValidationPolling(datasetId);
        } catch (err) {
            console.error("Failed to resume validation:", err);
        }
    }, [datasetId, startValidationPolling]);

    // Retry validation
    const retryValidation = useCallback(async () => {
        if (!datasetId) return;

        try {
            // Call API to restart validation
            await datasetsApi.startValidation(datasetId);
            setValidationStatus("validating");
            setValidationProgress(0);
            setValidationError(null);
            startValidationPolling(datasetId);
        } catch (err) {
            console.error("Failed to retry validation:", err);
            setValidationError(err instanceof Error ? err.message : "Failed to retry validation");
        }
    }, [datasetId, startValidationPolling]);

    // Delete dataset and close
    const deleteDataset = useCallback(async () => {
        if (!datasetId) {
            resetAll();
            onOpenChange(false);
            return;
        }

        try {
            await datasetsApi.delete(datasetId);
            resetAll();
            onOpenChange(false);
        } catch (err) {
            console.error("Failed to delete dataset:", err);
            step1.setError("Failed to delete dataset.");
        }
    }, [datasetId, resetAll, onOpenChange, step1]);

    // Go back to Step 1
    const goBackToStep1 = useCallback(() => {
        stopPolling();
        setValidationStatus("pending");
        setValidationProgress(0);
        setValidationStats(null);
        setValidationError(null);
        setStep(1);
    }, [stopPolling]);

    return {
        // Current state
        step,
        createdDataset,
        datasetId,
        isResuming,
        uploading,
        error: step1.error,

        // Validation state
        validationStatus,
        validationProgress,
        validationStats,
        validationError,

        // Step 1 hook
        step1,

        // Actions
        proceedToStep2,
        handleSubmit,
        cancelValidation,
        resumeValidation,
        retryValidation,
        deleteDataset,
        goBackToStep1,
        resetAll,
    };
}
