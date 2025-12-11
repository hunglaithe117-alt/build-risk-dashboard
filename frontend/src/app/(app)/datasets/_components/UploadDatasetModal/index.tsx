"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Loader2, RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CIProvider } from "@/types";
import type { UploadDatasetModalProps, Step } from "./types";
import { StepIndicator } from "./StepIndicator";
import { StepUpload } from "./StepUpload";
import { StepConfigureRepos } from "./StepConfigureRepos";
import { StepValidate } from "./StepValidate";
import { useUploadDatasetWizard } from "./hooks/useUploadDatasetWizard";

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
    2: "Configure Repositories",
    3: "Review & Import",
};

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

    if (!open) return null;

    const { step, step1, step2, step3, uploading, error } = wizard;

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
                <div className="w-full max-w-5xl h-[85vh] rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-950 border dark:border-slate-800 flex flex-col overflow-hidden">
                    {/* Header */}
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold">Upload Dataset</h2>
                            <p className="text-sm text-muted-foreground">
                                Step {step} of 3: {STEP_TITLES[step]}
                            </p>
                        </div>
                        <button
                            type="button"
                            className="rounded-full p-2 text-muted-foreground hover:bg-slate-100 dark:hover:bg-slate-800"
                            onClick={() => {
                                if (step3.validationStatus !== "validating") {
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
                        {/* Step 1: Upload & Map Columns + Preview */}
                        {step === 1 && (
                            <StepUpload
                                preview={step1.preview}
                                uploading={uploading}
                                name={step1.name}
                                description={step1.description}
                                ciProvider={CIProvider.GITHUB_ACTIONS}
                                mappings={step1.mappings}
                                isMappingValid={step1.isMappingValid}
                                isDatasetCreated={!!wizard.datasetId}
                                fileInputRef={step1.fileInputRef}
                                onFileSelect={step1.handleFileSelect}
                                onNameChange={step1.setName}
                                onDescriptionChange={step1.setDescription}
                                onCiProviderChange={() => { }}
                                onMappingChange={step1.handleMappingChange}
                                onClearFile={step1.handleClearFile}
                            />
                        )}

                        {/* Step 2: Configure Repos + Languages + Frameworks */}
                        {step === 2 && (
                            <StepConfigureRepos
                                uniqueRepos={step2.uniqueRepos}
                                invalidFormatRepos={step2.invalidFormatRepos}
                                repoConfigs={step2.repoConfigs}
                                activeRepo={step2.activeRepo}
                                availableLanguages={step2.availableLanguages}
                                languageLoading={step2.languageLoading}
                                transitionLoading={step2.transitionLoading}
                                validReposCount={step2.validReposCount}
                                invalidReposCount={step2.invalidReposCount}
                                onActiveRepoChange={step2.setActiveRepo}
                                onToggleLanguage={step2.toggleLanguage}
                                onToggleFramework={step2.toggleFramework}
                                onSetCiProvider={step2.setCiProvider}
                                getSuggestedFrameworks={step2.getSuggestedFrameworks}
                            />
                        )}

                        {/* Step 3: Validate Builds + Summary */}
                        {step === 3 && (
                            <StepValidate
                                datasetId={wizard.datasetId}
                                validationStatus={step3.validationStatus}
                                validationProgress={step3.validationProgress}
                                validationStats={step3.validationStats}
                                validationError={step3.validationError}
                                validatedRepos={step3.validatedRepos}
                                onStartValidation={() => wizard.datasetId && step3.startValidation(wizard.datasetId)}
                                onCancelValidation={() => wizard.datasetId && step3.cancelValidation(wizard.datasetId)}
                            />
                        )}
                    </div>

                    {/* Footer */}
                    <div className="mt-6 flex items-center justify-between border-t pt-4">
                        <div className="flex items-center gap-2">
                            {/* Cancel (Step 1) or Reset (Step 2, 3) */}
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
                            ) : (
                                <Button
                                    variant="outline"
                                    onClick={wizard.resetToStep1}
                                    disabled={step3.validationStatus === "validating" || uploading}
                                    className="gap-2"
                                >
                                    <RotateCcw className="h-4 w-4" />
                                    Reset
                                </Button>
                            )}
                        </div>

                        <div className="flex items-center gap-2">
                            {/* Step 1: Continue to configure repos */}
                            {step === 1 && step1.preview && (
                                <Button
                                    onClick={wizard.proceedToStep2}
                                    disabled={!step1.isMappingValid || uploading}
                                    className="gap-2"
                                >
                                    {uploading ? (
                                        <><Loader2 className="h-4 w-4 animate-spin" /> Uploading...</>
                                    ) : (
                                        "Continue"
                                    )}
                                </Button>
                            )}

                            {/* Step 2: Upload & start validation */}
                            {step === 2 && (
                                <Button
                                    onClick={wizard.proceedToStep3}
                                    disabled={uploading || step2.uniqueRepos.length === 0 || step2.validReposCount === 0}
                                    className="gap-2"
                                >
                                    {uploading ? (
                                        <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</>
                                    ) : (
                                        "Continue"
                                    )}
                                </Button>
                            )}

                            {/* Step 3: Import when validation complete */}
                            {step === 3 && step3.validationStatus === "completed" && (
                                <Button
                                    onClick={wizard.handleSubmit}
                                    disabled={uploading}
                                    className="gap-2"
                                >
                                    {uploading ? (
                                        <><Loader2 className="h-4 w-4 animate-spin" /> Importing...</>
                                    ) : (
                                        <><CheckCircle2 className="h-4 w-4" /> Complete Setup</>
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
