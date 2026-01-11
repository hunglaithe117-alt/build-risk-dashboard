"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { BuildSourceRecord, ValidationStats } from "@/types";
import { buildSourcesApi } from "@/lib/api";
import type { Step } from "../types";
import { useStep1Upload } from "./useStep1Upload";

interface UseUploadBuildSourceWizardProps {
    open: boolean;
    existingSource?: BuildSourceRecord;
    onSuccess: (source: BuildSourceRecord) => void;
    onOpenChange: (open: boolean) => void;
    onSourceCreated?: (source: BuildSourceRecord) => void;
}

/**
 * Simplified 2-step upload wizard.
 *
 * Step 1: Upload CSV + Map columns + Select CI Provider
 * Step 2: Validation status + Repo stats
 */
export function useUploadBuildSourceWizard({
    open,
    existingSource,
    onSuccess,
    onOpenChange,
    onSourceCreated,
}: UseUploadBuildSourceWizardProps) {
    const [step, setStep] = useState<Step>(1);
    const [createdSource, setCreatedSource] = useState<BuildSourceRecord | null>(null);
    const [sourceId, setSourceId] = useState<string | null>(null);
    const [isResuming, setIsResuming] = useState(false);
    const [uploading, setUploading] = useState(false);

    // Validation state (for Step 2)
    const [validationStatus, setValidationStatus] = useState<
        "pending" | "validating" | "completed" | "failed"
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
        setCreatedSource(null);
        setSourceId(null);
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
    const pollValidationStatus = useCallback(async (id: string) => {
        try {
            const source = await buildSourcesApi.get(id);
            setValidationStatus(source.validation_status || "pending");
            setValidationProgress(source.validation_progress || 0);
            if (source.validation_stats) {
                setValidationStats(source.validation_stats);
            }
            if (source.validation_error) {
                setValidationError(source.validation_error);
            }
            setCreatedSource(source);

            // Stop polling on completion
            if (["completed", "failed"].includes(source.validation_status || "")) {
                stopPolling();
            }
        } catch (err) {
            console.error("Failed to poll validation status:", err);
        }
    }, [stopPolling]);

    // Start polling for validation status
    const startValidationPolling = useCallback((id: string) => {
        // Clear existing interval
        stopPolling();

        // Initial poll
        pollValidationStatus(id);

        // Start interval
        const interval = setInterval(() => {
            pollValidationStatus(id);
        }, 2000);

        pollingIntervalRef.current = interval;
    }, [pollValidationStatus, stopPolling]);

    // Load existing source when modal opens in resume mode
    useEffect(() => {
        if (!open) {
            resetAll();
            return;
        }

        if (!existingSource) return;

        setIsResuming(true);
        setCreatedSource(existingSource);
        setSourceId(existingSource.id);
        step1.loadFromExistingSource(existingSource);

        const validationStatus = existingSource.validation_status;

        if (validationStatus && ["validating", "completed", "failed"].includes(validationStatus)) {
            setStep(2);
            setValidationStatus(validationStatus as typeof validationStatus);
            setValidationProgress(existingSource.validation_progress || 0);
            if (existingSource.validation_stats) {
                setValidationStats(existingSource.validation_stats);
            }
            if (validationStatus === "validating") {
                startValidationPolling(existingSource.id);
            }
        } else {
            setStep(1);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, existingSource]);

    // Step 1 -> Step 2: Upload/Update and start validation
    const proceedToStep2 = async () => {
        if (!step1.file && !createdSource) return;
        if (!step1.isMappingValid) return;

        setUploading(true);
        step1.setError(null);

        try {
            let source: BuildSourceRecord;

            // Prepare mapped fields based on CI provider mode
            const mappedFields = {
                build_id: step1.mappings.build_id || null,
                repo_name: step1.mappings.repo_name || null,
                ci_provider: step1.ciProviderMode === "column" ? step1.ciProviderColumn : null,
            };

            // Only set ci_provider (single mode) if not using column mapping
            const ciProviderValue = step1.ciProviderMode === "single" ? step1.ciProvider : null;

            if (createdSource?.id) {
                // Update existing source with mappings and CI provider
                source = await buildSourcesApi.update(createdSource.id, {
                    mapped_fields: mappedFields,
                    ci_provider: ciProviderValue,
                });
                setCreatedSource(source);
            } else if (step1.file) {
                // Upload new source - backend triggers validation automatically
                source = await buildSourcesApi.upload(step1.file, {
                    name: step1.name || step1.file.name.replace(/\.csv$/i, ""),
                    description: step1.description || undefined,
                });

                // Update with mappings and CI provider (upload doesn't take mappings directly in current API impl in build-sources.ts line 105)
                source = await buildSourcesApi.update(source.id, {
                    mapped_fields: mappedFields,
                    ci_provider: ciProviderValue,
                });

                setCreatedSource(source);
                setSourceId(source.id);
                onSourceCreated?.(source);
            } else {
                throw new Error("No file to upload");
            }

            // Start the validation process explicitly
            await buildSourcesApi.startValidation(source.id);

            // Move to Step 2 and start polling
            setStep(2);
            setValidationStatus("validating");
            startValidationPolling(source.id);
        } catch (err) {
            console.error("Upload failed:", err);
            step1.setError(err instanceof Error ? err.message : "Failed to upload build source");
        } finally {
            setUploading(false);
        }
    };

    // Final submission - close modal on success
    const handleSubmit = async () => {
        if (!createdSource) return;

        if (validationStatus !== "completed") {
            step1.setError("Validation must complete before submitting");
            return;
        }

        onSuccess(createdSource);
        onOpenChange(false);
        resetAll();
    };

    // Retry validation
    const retryValidation = useCallback(async () => {
        if (!sourceId) return;

        try {
            // Call API to restart validation
            await buildSourcesApi.startValidation(sourceId);
            setValidationStatus("validating");
            setValidationProgress(0);
            setValidationError(null);
            startValidationPolling(sourceId);
        } catch (err) {
            console.error("Failed to retry validation:", err);
            setValidationError(err instanceof Error ? err.message : "Failed to retry validation");
        }
    }, [sourceId, startValidationPolling]);

    // Delete source and close
    const deleteSource = useCallback(async () => {
        if (!sourceId) {
            resetAll();
            onOpenChange(false);
            return;
        }

        try {
            await buildSourcesApi.delete(sourceId);
            resetAll();
            onOpenChange(false);
        } catch (err) {
            console.error("Failed to delete source:", err);
            step1.setError("Failed to delete source.");
        }
    }, [sourceId, resetAll, onOpenChange, step1]);

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
        createdSource,
        sourceId,
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
        retryValidation,
        deleteSource,
        goBackToStep1,
        resetAll,
    };
}
