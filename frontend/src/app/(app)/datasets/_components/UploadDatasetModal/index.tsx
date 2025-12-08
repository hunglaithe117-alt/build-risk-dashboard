"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { UploadDatasetModalProps, Step } from "./types";
import { StepIndicator } from "./StepIndicator";
import { StepUpload } from "./StepUpload";
import { StepConfigureRepos } from "./StepConfigureRepos";
import { StepSelectFeatures } from "./StepSelectFeatures";
import { useUploadDatasetForm } from "./hooks/useUploadDatasetForm";

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
    3: "Select Features",
};

export function UploadDatasetModal({
    open,
    onOpenChange,
    onSuccess,
    existingDataset,
}: UploadDatasetModalProps) {
    const form = useUploadDatasetForm({
        open,
        existingDataset,
        onSuccess,
        onOpenChange,
    });

    if (!open) return null;

    return (
        <Portal>
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
                <div className="w-full max-w-5xl h-[85vh] rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-950 border dark:border-slate-800 flex flex-col overflow-hidden">
                    {/* Header */}
                    <div className="mb-6 flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold">Upload Dataset</h2>
                            <p className="text-sm text-muted-foreground">
                                Step {form.step} of 3: {STEP_TITLES[form.step]}
                            </p>
                        </div>
                        <button
                            type="button"
                            className="rounded-full p-2 text-muted-foreground hover:bg-slate-100 dark:hover:bg-slate-800"
                            onClick={() => {
                                form.resetState();
                                onOpenChange(false);
                            }}
                        >
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    <StepIndicator currentStep={form.step} />

                    {form.error && (
                        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                            <AlertCircle className="h-4 w-4 flex-shrink-0" />
                            <span>{form.error}</span>
                        </div>
                    )}

                    {/* Content */}
                    <div className="flex-1 overflow-y-auto">
                        {form.step === 1 && (
                            <div className="space-y-6">
                                <StepUpload
                                    preview={form.preview}
                                    uploading={form.uploading}
                                    name={form.name}
                                    description={form.description}
                                    mappings={form.mappings}
                                    isMappingValid={form.isMappingValid}
                                    fileInputRef={form.fileInputRef}
                                    onFileSelect={form.handleFileSelect}
                                    onNameChange={form.setName}
                                    onDescriptionChange={form.setDescription}
                                    onMappingChange={form.handleMappingChange}
                                    onClearFile={form.handleClearFile}
                                />
                            </div>
                        )}

                        {form.step === 2 && (
                            <StepConfigureRepos
                                uniqueRepos={form.uniqueRepos}
                                repoConfigs={form.repoConfigs}
                                activeRepo={form.activeRepo}
                                availableLanguages={form.availableLanguages}
                                languageLoading={form.languageLoading}
                                frameworksByLang={form.frameworksByLang}
                                transitionLoading={form.transitionLoading}
                                onActiveRepoChange={form.setActiveRepo}
                                onToggleLanguage={form.toggleLanguage}
                                onToggleFramework={form.toggleFramework}
                                onSetCiProvider={form.setCiProvider}
                                getSuggestedFrameworks={form.getSuggestedFrameworks}
                            />
                        )}

                        {form.step === 3 && (
                            <div className="space-y-6">
                                <StepSelectFeatures
                                    features={form.features}
                                    templates={form.templates}
                                    selectedFeatures={form.selectedFeatures}
                                    featureSearch={form.featureSearch}
                                    featuresLoading={form.featuresLoading}
                                    collapsedCategories={form.collapsedCategories}
                                    onFeatureSearchChange={form.setFeatureSearch}
                                    onToggleFeature={form.toggleFeature}
                                    onToggleCategory={form.toggleCategory}
                                    onApplyTemplate={form.applyTemplate}
                                    onClearAll={() => {
                                        // Clear all selected features
                                        for (const feat of form.selectedFeatures) {
                                            form.toggleFeature(feat);
                                        }
                                    }}
                                    dagData={form.dagData}
                                    dagLoading={form.dagLoading}
                                    onLoadDAG={form.loadDAG}
                                    onSetSelectedFeatures={form.setSelectedFeaturesFromDAG}
                                />
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="mt-6 flex items-center justify-between border-t pt-4">
                        <Button
                            variant="outline"
                            onClick={() => {
                                if (form.step <= form.minStep) {
                                    form.resetState();
                                    onOpenChange(false);
                                } else {
                                    form.setStep((form.step - 1) as Step);
                                }
                            }}
                        >
                            {form.step <= form.minStep ? "Cancel" : "Back"}
                        </Button>

                        <div className="flex items-center gap-2">
                            {form.step === 1 && form.preview && (
                                <Button
                                    onClick={form.handleProceedToStep2}
                                    disabled={!form.isMappingValid || form.uploading}
                                    className="gap-2"
                                >
                                    {form.uploading ? (
                                        <><Loader2 className="h-4 w-4 animate-spin" /> Uploading...</>
                                    ) : (
                                        <>Continue</>
                                    )}
                                </Button>
                            )}

                            {form.step === 2 && (
                                <Button onClick={() => form.setStep(3)} className="gap-2">
                                    Continue to Features
                                </Button>
                            )}

                            {form.step === 3 && (
                                <Button
                                    onClick={form.handleSubmit}
                                    disabled={form.uploading}
                                    className="gap-2"
                                >
                                    {form.uploading ? (
                                        <><Loader2 className="h-4 w-4 animate-spin" /> Saving...</>
                                    ) : (
                                        <><CheckCircle2 className="h-4 w-4" /> Create Dataset</>
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
