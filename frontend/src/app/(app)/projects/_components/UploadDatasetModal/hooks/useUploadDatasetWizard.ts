"use client";

import { useState, useCallback, useEffect } from "react";
import type { DatasetRecord } from "@/types";
import { datasetsApi, datasetValidationApi } from "@/lib/api";
import type { Step } from "../types";
import { useStep1Upload } from "./useStep1Upload";
import { useStep2ConfigRepos } from "./useStep2ConfigRepos";
import { useStep3Validation } from "./useStep3Validation";

interface UseUploadDatasetWizardProps {
    open: boolean;
    existingDataset?: DatasetRecord;
    onSuccess: (dataset: DatasetRecord) => void;
    onOpenChange: (open: boolean) => void;
    onDatasetCreated?: (dataset: DatasetRecord) => void;
}

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

    // Step hooks
    const step1 = useStep1Upload();
    const step2 = useStep2ConfigRepos();
    const step3 = useStep3Validation();

    const resetAll = useCallback(() => {
        setStep(1);
        setCreatedDataset(null);
        setDatasetId(null);
        setIsResuming(false);
        setUploading(false);
        step1.resetStep1();
        step2.resetStep2();
        step3.resetStep3();
    }, [step1, step2, step3]);


    const resetToStep1 = useCallback(async () => {
        if (!datasetId) {
            resetAll();
            return;
        }

        try {
            await datasetValidationApi.resetStep2(datasetId);
            step1.resetMappings(); // Clear mappings but keep file preview
            step2.resetStep2();
            step3.resetStep3();
            setStep(1);
        } catch (err) {
            console.error("Failed to reset:", err);
            step1.setError("Failed to reset. Please try again.");
        }
    }, [datasetId, resetAll, step1, step2, step3]);

    // Delete dataset completely
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

        const setupStep = existingDataset.setup_step || 1;
        const validationStatus = existingDataset.validation_status;

        let extractedRepos: string[] = [];
        if (existingDataset.preview?.length && existingDataset.mapped_fields?.repo_name) {
            const repoCol = existingDataset.mapped_fields.repo_name;
            const { valid } = step2.extractAndSetRepos(
                {
                    columns: existingDataset.columns || [],
                    rows: (existingDataset.preview || []).map((row) => {
                        const converted: Record<string, string> = {};
                        Object.entries(row).forEach(([key, value]) => {
                            converted[key] = String(value ?? "");
                        });
                        return converted;
                    }),
                    totalRows: existingDataset.rows || 0,
                    fileName: existingDataset.file_name || "dataset.csv",
                    fileSize: existingDataset.size_bytes || 0,
                },
                existingDataset.mapped_fields.repo_name
            );
            extractedRepos = valid;
        }

        if (
            setupStep >= 3 ||
            (validationStatus && ["validating", "completed", "failed", "cancelled"].includes(validationStatus))
        ) {
            setStep(3);
            if (validationStatus) {
                step3.setValidationStatus(validationStatus as "validating" | "completed" | "failed" | "cancelled");
            }
            if (validationStatus === "validating" && existingDataset.id) {
                // Resume polling
                step3.loadValidationSummary(existingDataset.id);
            }
        } else if (setupStep >= 2) {
            setStep(2);
            // Load pre-validated repo configs from backend
            datasetsApi.listRepoConfigs(existingDataset.id).then(repoConfigs => {
                step2.initializeFromRepoConfigs(repoConfigs);
            }).catch(console.error);
        } else {
            setStep(1);
        }
    }, [open, existingDataset]);

    // Step 1 -> Step 2
    const proceedToStep2 = async () => {
        if (!step1.file || !step1.isMappingValid) return;

        setUploading(true);
        step1.setError(null);

        try {
            let dataset: DatasetRecord;

            if (createdDataset?.id) {
                await datasetsApi.update(createdDataset.id, {
                    mapped_fields: {
                        build_id: step1.mappings.build_id || null,
                        repo_name: step1.mappings.repo_name || null,
                        commit_sha: null,
                    },
                    setup_step: 2,
                });
                dataset = { ...createdDataset };
            } else {
                // Upload triggers validate_repos_task on backend
                dataset = await datasetsApi.upload(step1.file, {
                    name: step1.name || step1.file.name.replace(/\.csv$/i, ""),
                    description: step1.description || undefined,
                });

                await datasetsApi.update(dataset.id, {
                    mapped_fields: {
                        build_id: step1.mappings.build_id || null,
                        repo_name: step1.mappings.repo_name || null,
                        commit_sha: null,
                    },
                    setup_step: 2,
                });

                setCreatedDataset(dataset);
                setDatasetId(dataset.id);
                onDatasetCreated?.(dataset);
            }

            // Poll for repo validation completion
            const pollRepoValidation = async (dsId: string, maxAttempts = 60): Promise<DatasetRecord> => {
                for (let i = 0; i < maxAttempts; i++) {
                    const refreshed = await datasetsApi.get(dsId);
                    if (refreshed.repo_validation_status === "completed") {
                        return refreshed;
                    }
                    if (refreshed.repo_validation_status === "failed") {
                        throw new Error(refreshed.repo_validation_error || "Repo validation failed");
                    }
                    // Wait 1 second before next poll
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
                throw new Error("Repo validation timed out");
            };

            // Wait for repo validation to complete
            const validatedDataset = await pollRepoValidation(dataset.id);
            setCreatedDataset(validatedDataset);

            // Fetch repo configs and initialize Step 2
            const repoConfigs = await datasetsApi.listRepoConfigs(dataset.id);
            step2.initializeFromRepoConfigs(repoConfigs);

            setStep(2);
        } catch (err) {
            console.error("Upload failed:", err);
            step1.setError(err instanceof Error ? err.message : "Failed to upload dataset");
        } finally {
            setUploading(false);
        }
    };

    // Step 2 -> Step 3
    const proceedToStep3 = async () => {
        if (!datasetId) return;

        setUploading(true);
        step1.setError(null);

        try {
            const allLanguages = new Set<string>();
            const allFrameworks = new Set<string>();
            const reposToSave: Array<{
                full_name: string;
                ci_provider: string;
                source_languages: string[];
                test_frameworks: string[];
                validation_status: string;
            }> = [];

            Object.entries(step2.repoConfigs).forEach(([repo, config]) => {
                if (config.validation_status === "valid") {
                    config.source_languages.forEach((l) => allLanguages.add(l));
                    config.test_frameworks.forEach((f) => allFrameworks.add(f));
                    reposToSave.push({
                        full_name: repo,
                        ci_provider: config.ci_provider,
                        source_languages: config.source_languages,
                        test_frameworks: config.test_frameworks,
                        validation_status: config.validation_status,
                    });
                }
            });

            await datasetValidationApi.saveRepos(datasetId, reposToSave);

            await datasetsApi.update(datasetId, {
                source_languages: Array.from(allLanguages),
                test_frameworks: Array.from(allFrameworks),
                setup_step: 3,
            });

            setStep(3);
            await step3.startValidation(datasetId);
        } catch (err) {
            console.error("Failed to proceed to Step 3:", err);
            step1.setError(err instanceof Error ? err.message : "Failed to save configuration");
        } finally {
            setUploading(false);
        }
    };

    // Final submission
    const handleSubmit = async () => {
        if (!createdDataset) return;

        setUploading(true);
        step1.setError(null);

        try {
            onSuccess(createdDataset);
            onOpenChange(false);
            resetAll();
        } catch (err) {
            console.error("Submit failed:", err);
            step1.setError(err instanceof Error ? err.message : "Failed to complete");
        } finally {
            setUploading(false);
        }
    };

    return {
        // Current state
        step,
        createdDataset,
        datasetId,
        isResuming,
        uploading,
        error: step1.error,

        // Step hooks (expose for components)
        step1,
        step2,
        step3,

        // Actions
        proceedToStep2,
        proceedToStep3,
        handleSubmit,
        resetToStep1,
        deleteDataset,
        resetAll,
    };
}
