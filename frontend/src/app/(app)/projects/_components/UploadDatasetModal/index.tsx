"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
    AlertCircle,
    CheckCircle2,
    Loader2,
    Pause,
    Play,
    RotateCcw,
    X,
    AlertTriangle,
    ArrowLeft,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { datasetsApi } from "@/lib/api";
import type { UploadDatasetModalProps, Step, CIProviderOption } from "./types";
import { StepIndicator } from "./StepIndicator";
import { StepUpload } from "./StepUpload";
import { useUploadDatasetWizard } from "./hooks/useUploadDatasetWizard";
import { useFeaturesConfig } from "./hooks/useFeaturesConfig";

// Type for repo stats from API
interface RepoStatItem {
    id: string;
    full_name: string;
    builds_total: number;
    builds_found: number;
    builds_not_found: number;
    builds_filtered: number;
}

const Portal = ({ children }: { children: React.ReactNode }) => {
    const [mounted, setMounted] = useState(false);
    useEffect(() => {
        setMounted(true);
    }, []);
    if (!mounted) return null;
    return createPortal(children, document.body);
};

const STEP_TITLES: Record<Step, string> = {
    1: "Upload & Map Columns",
    2: "Validate Builds",
};

const REPOS_PER_PAGE = 20;

export function UploadDatasetModal({
    open,
    onOpenChange,
    onSuccess,
    onDatasetCreated,
    existingDataset,
}: UploadDatasetModalProps) {
    const wizard = useUploadDatasetWizard({
        open,
        existingDataset,
        onSuccess,
        onOpenChange,
        onDatasetCreated,
    });

    const { config: featuresConfig } = useFeaturesConfig();

    // Repo stats state (separate from validation stats)
    const [repoStats, setRepoStats] = useState<RepoStatItem[]>([]);
    const [repoStatsTotal, setRepoStatsTotal] = useState(0);
    const [repoStatsPage, setRepoStatsPage] = useState(0);
    const [repoStatsLoading, setRepoStatsLoading] = useState(false);

    // Default CI providers fallback
    const ciProviders: CIProviderOption[] = featuresConfig?.ciProviders ?? [
        { value: "github_actions", label: "GitHub Actions" },
        { value: "travis_ci", label: "Travis CI" },
        { value: "circleci", label: "CircleCI" },
    ];

    // Fetch repo stats when validation completes
    const fetchRepoStats = useCallback(async (datasetId: string, page: number = 0) => {
        setRepoStatsLoading(true);
        try {
            const result = await datasetsApi.getRepoStats(datasetId, {
                skip: page * REPOS_PER_PAGE,
                limit: REPOS_PER_PAGE,
            });
            setRepoStats(result.items);
            setRepoStatsTotal(result.total);
        } catch (err) {
            console.error("Failed to fetch repo stats:", err);
        } finally {
            setRepoStatsLoading(false);
        }
    }, []);

    // Fetch repo stats when validation completes
    useEffect(() => {
        if (wizard.validationStatus === "completed" && wizard.datasetId) {
            fetchRepoStats(wizard.datasetId, repoStatsPage);
        }
    }, [wizard.validationStatus, wizard.datasetId, repoStatsPage, fetchRepoStats]);

    // Reset repo stats when modal closes or validation resets
    useEffect(() => {
        if (!open || wizard.validationStatus === "pending") {
            setRepoStats([]);
            setRepoStatsTotal(0);
            setRepoStatsPage(0);
        }
    }, [open, wizard.validationStatus]);

    if (!open) return null;

    const {
        step,
        step1,
        uploading,
        error,
        validationStatus,
        validationProgress,
        validationStats,
        validationError,
    } = wizard;

    const totalPages = Math.ceil(repoStatsTotal / REPOS_PER_PAGE);

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
                <div className="w-full max-w-5xl h-[85vh] rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-950 border dark:border-slate-800 flex flex-col overflow-hidden">
                    {/* Header */}
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold">Upload Dataset</h2>
                            <p className="text-sm text-muted-foreground">
                                Step {step} of 2: {STEP_TITLES[step]}
                            </p>
                        </div>
                        <button
                            type="button"
                            className="rounded-full p-2 text-muted-foreground hover:bg-slate-100 dark:hover:bg-slate-800"
                            onClick={() => {
                                if (validationStatus !== "validating") {
                                    wizard.resetAll();
                                }
                                onOpenChange(false);
                            }}
                        >
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    <StepIndicator currentStep={step} />

                    {error && (
                        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                            <AlertCircle className="h-4 w-4 flex-shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}

                    {/* Content */}
                    <div className="flex-1 overflow-y-auto space-y-4">
                        {/* Step 1: Upload & Map Columns + CI Provider */}
                        {step === 1 && (
                            <StepUpload
                                preview={step1.preview}
                                uploading={uploading}
                                name={step1.name}
                                description={step1.description}
                                ciProvider={step1.ciProvider}
                                ciProviderMode={step1.ciProviderMode}
                                ciProviderColumn={step1.ciProviderColumn}
                                ciProviders={ciProviders}
                                buildFilters={step1.buildFilters}
                                mappings={step1.mappings}
                                isMappingValid={step1.isMappingValid}
                                isDatasetCreated={!!wizard.datasetId}
                                fileInputRef={step1.fileInputRef}
                                onFileSelect={step1.handleFileSelect}
                                onNameChange={step1.setName}
                                onDescriptionChange={step1.setDescription}
                                onCiProviderChange={step1.setCiProvider}
                                onCiProviderModeChange={step1.setCiProviderMode}
                                onCiProviderColumnChange={step1.setCiProviderColumn}
                                onBuildFiltersChange={step1.setBuildFilters}
                                onMappingChange={step1.handleMappingChange}
                                onClearFile={step1.handleClearFile}
                            />
                        )}

                        {/* Step 2: Validation Progress */}
                        {step === 2 && (
                            <div className="space-y-6">
                                {/* Status Header */}
                                <div className="flex items-center gap-4">
                                    {validationStatus === "validating" && (
                                        <div className="flex items-center gap-2 text-blue-600">
                                            <Loader2 className="h-5 w-5 animate-spin" />
                                            <span className="font-medium">Validating builds...</span>
                                        </div>
                                    )}
                                    {validationStatus === "completed" && (
                                        <div className="flex items-center gap-2 text-emerald-600">
                                            <CheckCircle2 className="h-5 w-5" />
                                            <span className="font-medium">Validation complete</span>
                                        </div>
                                    )}
                                    {validationStatus === "failed" && (
                                        <div className="flex items-center gap-2 text-red-600">
                                            <AlertTriangle className="h-5 w-5" />
                                            <span className="font-medium">Validation failed</span>
                                        </div>
                                    )}
                                    {validationStatus === "cancelled" && (
                                        <div className="flex items-center gap-2 text-amber-600">
                                            <AlertCircle className="h-5 w-5" />
                                            <span className="font-medium">Validation cancelled</span>
                                        </div>
                                    )}
                                </div>

                                {/* Progress Bar */}
                                {validationStatus === "validating" && (
                                    <div className="space-y-2">
                                        <Progress value={validationProgress} className="h-2" />
                                        <p className="text-sm text-muted-foreground">
                                            {validationProgress}% complete
                                        </p>
                                    </div>
                                )}

                                {/* Error Message */}
                                {validationError && (
                                    <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                                        <p className="text-sm text-red-700 dark:text-red-300">
                                            {validationError}
                                        </p>
                                    </div>
                                )}

                                {/* Stats Summary */}
                                {validationStats && (
                                    <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
                                        <div className="rounded-lg border bg-slate-50 p-4 dark:bg-slate-800">
                                            <p className="text-xs uppercase text-muted-foreground">
                                                Total Repos
                                            </p>
                                            <p className="mt-1 text-2xl font-bold">
                                                {validationStats.repos_total}
                                            </p>
                                        </div>
                                        <div className="rounded-lg border bg-emerald-50 p-4 dark:bg-emerald-900/20">
                                            <p className="text-xs uppercase text-muted-foreground">
                                                Valid Repos
                                            </p>
                                            <p className="mt-1 text-2xl font-bold text-emerald-600">
                                                {validationStats.repos_valid}
                                            </p>
                                        </div>
                                        <div className="rounded-lg border bg-slate-50 p-4 dark:bg-slate-800">
                                            <p className="text-xs uppercase text-muted-foreground">
                                                Builds Found
                                            </p>
                                            <p className="mt-1 text-2xl font-bold">
                                                {validationStats.builds_found}
                                            </p>
                                        </div>
                                        <div className="rounded-lg border bg-blue-50 p-4 dark:bg-blue-900/20">
                                            <p className="text-xs uppercase text-muted-foreground">
                                                Builds Filtered
                                            </p>
                                            <p className="mt-1 text-2xl font-bold text-blue-600">
                                                {validationStats.builds_filtered ?? 0}
                                            </p>
                                        </div>
                                        <div className="rounded-lg border bg-amber-50 p-4 dark:bg-amber-900/20">
                                            <p className="text-xs uppercase text-muted-foreground">
                                                Builds Not Found
                                            </p>
                                            <p className="mt-1 text-2xl font-bold text-amber-600">
                                                {validationStats.builds_not_found}
                                            </p>
                                        </div>
                                    </div>
                                )}

                                {/* Build Coverage */}
                                {validationStats && validationStats.builds_total > 0 && (
                                    <div className="rounded-lg border p-4">
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm font-medium">Build Coverage</span>
                                            <span className="text-lg font-bold">
                                                {Math.round(
                                                    (validationStats.builds_found /
                                                        validationStats.builds_total) *
                                                    100
                                                )}
                                                %
                                            </span>
                                        </div>
                                        <Progress
                                            value={
                                                (validationStats.builds_found /
                                                    validationStats.builds_total) *
                                                100
                                            }
                                            className="mt-2 h-2"
                                        />
                                    </div>
                                )}

                                {/* Per-Repo Stats Table (Paginated) */}
                                {validationStatus === "completed" && (
                                    <div className="rounded-lg border overflow-hidden">
                                        <div className="bg-muted/50 px-4 py-2 border-b flex items-center justify-between">
                                            <span className="text-sm font-medium">
                                                Repository Details
                                                {repoStatsTotal > 0 && (
                                                    <span className="text-muted-foreground ml-2">
                                                        ({repoStatsTotal} repos)
                                                    </span>
                                                )}
                                            </span>
                                            {totalPages > 1 && (
                                                <div className="flex items-center gap-2">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setRepoStatsPage(Math.max(0, repoStatsPage - 1))}
                                                        disabled={repoStatsPage === 0 || repoStatsLoading}
                                                    >
                                                        <ChevronLeft className="h-4 w-4" />
                                                    </Button>
                                                    <span className="text-xs text-muted-foreground">
                                                        {repoStatsPage + 1} / {totalPages}
                                                    </span>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setRepoStatsPage(Math.min(totalPages - 1, repoStatsPage + 1))}
                                                        disabled={repoStatsPage >= totalPages - 1 || repoStatsLoading}
                                                    >
                                                        <ChevronRight className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                        <div className="max-h-48 overflow-y-auto">
                                            {repoStatsLoading ? (
                                                <div className="flex items-center justify-center py-8">
                                                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                                </div>
                                            ) : repoStats.length > 0 ? (
                                                <table className="w-full text-sm">
                                                    <thead className="bg-muted/30 sticky top-0">
                                                        <tr>
                                                            <th className="text-left px-4 py-2 font-medium">Repository</th>
                                                            <th className="text-center px-2 py-2 font-medium">Found</th>
                                                            <th className="text-center px-2 py-2 font-medium">Filtered</th>
                                                            <th className="text-center px-2 py-2 font-medium">Not Found</th>
                                                            <th className="text-center px-2 py-2 font-medium">Total</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {repoStats.map((repo) => (
                                                            <tr key={repo.id} className="border-t hover:bg-muted/20">
                                                                <td className="px-4 py-2 font-mono text-xs truncate max-w-[200px]" title={repo.full_name}>
                                                                    {repo.full_name}
                                                                </td>
                                                                <td className="text-center px-2 py-2 text-green-600 font-medium">
                                                                    {repo.builds_found}
                                                                </td>
                                                                <td className="text-center px-2 py-2 text-blue-600 font-medium">
                                                                    {repo.builds_filtered}
                                                                </td>
                                                                <td className="text-center px-2 py-2 text-amber-600 font-medium">
                                                                    {repo.builds_not_found}
                                                                </td>
                                                                <td className="text-center px-2 py-2 text-muted-foreground">
                                                                    {repo.builds_total}
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            ) : (
                                                <div className="py-4 text-center text-muted-foreground text-sm">
                                                    No repository data available
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="mt-6 flex items-center justify-between border-t pt-4">
                        <div className="flex items-center gap-2">
                            {step === 1 ? (
                                <Button
                                    variant="outline"
                                    onClick={() => {
                                        wizard.resetAll();
                                        onOpenChange(false);
                                    }}
                                    disabled={uploading}
                                >
                                    Cancel
                                </Button>
                            ) : validationStatus === "completed" ? (
                                // Hide back button when validation is completed
                                null
                            ) : (
                                <div className="flex items-center gap-3">
                                    {validationStatus === "validating" && (
                                        <span className="text-xs text-muted-foreground hidden sm:inline-block">
                                            Pause validation to go back
                                        </span>
                                    )}
                                    <Button
                                        variant="outline"
                                        onClick={wizard.goBackToStep1}
                                        disabled={validationStatus === "validating" || uploading}
                                        className="gap-2"
                                    >
                                        <ArrowLeft className="h-4 w-4" />
                                        Back
                                    </Button>
                                </div>
                            )}
                        </div>

                        <div className="flex items-center gap-2">
                            {/* Step 1: Continue to validate */}
                            {step === 1 && step1.preview && (
                                <Button
                                    onClick={wizard.proceedToStep2}
                                    disabled={!step1.isMappingValid || uploading}
                                    className="gap-2"
                                >
                                    {uploading ? (
                                        <>
                                            <Loader2 className="h-4 w-4 animate-spin" /> Uploading...
                                        </>
                                    ) : (
                                        "Start Validation"
                                    )}
                                </Button>
                            )}

                            {/* Step 2: Cancel during validation */}
                            {step === 2 && validationStatus === "validating" && (
                                <Button
                                    onClick={wizard.cancelValidation}
                                    variant="outline"
                                    className="gap-2 text-amber-600 border-amber-300 hover:bg-amber-50"
                                >
                                    <Pause className="h-4 w-4" />
                                    Pause
                                </Button>
                            )}

                            {/* Step 2: Resume if cancelled */}
                            {step === 2 && validationStatus === "cancelled" && (
                                <Button
                                    onClick={wizard.resumeValidation}
                                    className="gap-2"
                                >
                                    <Play className="h-4 w-4" />
                                    Resume
                                </Button>
                            )}

                            {/* Step 2: Retry if failed */}
                            {step === 2 && validationStatus === "failed" && (
                                <Button
                                    onClick={wizard.retryValidation}
                                    variant="outline"
                                    className="gap-2"
                                >
                                    <RotateCcw className="h-4 w-4" />
                                    Retry
                                </Button>
                            )}

                            {/* Step 2: Complete when validation done */}
                            {step === 2 && validationStatus === "completed" && (
                                <Button
                                    onClick={wizard.handleSubmit}
                                    disabled={uploading}
                                    className="gap-2"
                                >
                                    {uploading ? (
                                        <>
                                            <Loader2 className="h-4 w-4 animate-spin" /> Completing...
                                        </>
                                    ) : (
                                        <>
                                            <CheckCircle2 className="h-4 w-4" /> Complete Setup
                                        </>
                                    )}
                                </Button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </Portal>
    );
}
