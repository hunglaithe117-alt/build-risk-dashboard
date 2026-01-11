"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, RotateCcw, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useUploadBuildSourceWizard } from "./_components/hooks/useUploadDatasetWizard";
import { UploadForm } from "./_components/UploadForm";
import { UploadPreview } from "./_components/UploadPreview";
import { ValidationView } from "./_components/ValidationView";
import { StepIndicator } from "./_components/StepIndicator";

export default function UploadBuildDataPage() {
    const router = useRouter();

    // Initialize wizard with open=true always for page
    const wizard = useUploadBuildSourceWizard({
        open: true,
        onOpenChange: () => { }, // Not needed for page
        onSuccess: (source) => {
            // Navigate back to scenarios list after upload completes
            router.push("/scenarios");
        },
        onSourceCreated: () => {
            // Optional: Refresh list if needed
        },
    });

    const {
        step,
        step1,
        uploading,
        error,
        validationStatus,
    } = wizard;

    const handleBack = () => {
        router.push("/scenarios");
    };

    return (
        <div className="flex h-[calc(100vh-theme(spacing.16))] overflow-hidden -m-6 rounded-none">
            {/* Left Panel: Configuration & Controls */}
            <div className="w-[500px] flex-shrink-0 border-r bg-background flex flex-col z-10 shadow-xl shadow-slate-200/50 dark:shadow-none">
                {/* Header */}
                <div className="flex items-center gap-3 px-6 py-4 border-b">
                    {step === 1 && (
                        <Button variant="ghost" size="icon" className="-ml-2" onClick={handleBack}>
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                    )}
                    <div>
                        <h1 className="text-lg font-semibold leading-none">Upload Build Data</h1>
                        <p className="text-xs text-muted-foreground mt-1">Import CSV to add raw build records</p>
                    </div>
                </div>

                {/* Steps */}
                <div className="px-6 py-4 border-b bg-muted/30">
                    <StepIndicator currentStep={step} />
                </div>

                {/* Scrollable Form Content */}
                <div className="flex-1 overflow-y-auto px-6 py-6">
                    {/* Error Banner */}
                    {error && (
                        <div className="mb-6 p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md dark:bg-red-900/20 dark:border-red-800 dark:text-red-300">
                            {error}
                        </div>
                    )}

                    {step === 1 ? (
                        <UploadForm
                            previewExists={!!step1.preview}
                            columns={step1.preview?.columns || []}
                            uploading={uploading}
                            name={step1.name}
                            description={step1.description}
                            ciProvider={step1.ciProvider}
                            ciProviderMode={step1.ciProviderMode}
                            ciProviderColumn={step1.ciProviderColumn}
                            ciProviders={step1.ciProviders}
                            mappings={step1.mappings}
                            isMappingValid={step1.isMappingValid}
                            fileInputRef={step1.fileInputRef}
                            onFileSelect={step1.handleFileSelect}
                            onNameChange={step1.setName}
                            onDescriptionChange={step1.setDescription}
                            onCiProviderChange={step1.setCiProvider}
                            onCiProviderModeChange={step1.setCiProviderMode}
                            onCiProviderColumnChange={step1.setCiProviderColumn}
                            onMappingChange={step1.handleMappingChange}
                        />
                    ) : (
                        <div className="space-y-6">
                            <div className="space-y-2">
                                <h3 className="text-lg font-semibold">Validation Progress</h3>
                                <p className="text-sm text-muted-foreground">
                                    We are analyzing your build data and importing records into the database.
                                </p>
                            </div>

                            {/* Validation Status Card */}
                            <div className="p-4 rounded-lg bg-slate-50 border space-y-4 dark:bg-slate-900">
                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-muted-foreground">Status</span>
                                        <span className="font-medium capitalize">{validationStatus.replace('_', ' ')}</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span className="text-muted-foreground">Source ID</span>
                                        <span className="font-mono text-xs">{wizard.sourceId}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer Controls */}
                <div className="px-6 py-4 border-t bg-background mt-auto">
                    <div className="flex justify-between items-center">
                        {step === 1 && (
                            <Button
                                variant="ghost"
                                onClick={() => router.push("/scenarios")}
                                disabled={uploading}
                            >
                                Cancel
                            </Button>
                        )}

                        <div className="flex gap-2">
                            {step === 1 && (
                                <Button
                                    onClick={wizard.proceedToStep2}
                                    disabled={!step1.preview || !step1.isMappingValid || uploading}
                                    className="min-w-[140px]"
                                >
                                    {uploading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Uploading...
                                        </>
                                    ) : (
                                        "Start Validation"
                                    )}
                                </Button>
                            )}

                            {step === 2 && (
                                <>
                                    {validationStatus === "validating" && (
                                        <div className="flex items-center gap-2 text-muted-foreground">
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            <span>Validating...</span>
                                        </div>
                                    )}
                                    {validationStatus === "failed" && (
                                        <Button onClick={wizard.retryValidation} variant="outline">
                                            <RotateCcw className="mr-2 h-4 w-4" /> Retry
                                        </Button>
                                    )}
                                    {validationStatus === "completed" && (
                                        <Button
                                            onClick={wizard.handleSubmit}
                                            className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                        >
                                            <CheckCircle2 className="mr-2 h-4 w-4" /> Complete Import
                                        </Button>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Panel: Visualization & Preview */}
            <div className="flex-1 bg-slate-50/50 dark:bg-slate-950/50 p-8 overflow-y-auto">
                <div className="max-w-5xl mx-auto h-full">
                    {step === 1 ? (
                        <div className="h-full flex flex-col items-center justify-center">
                            {step1.preview ? (
                                <div className="w-full h-full">
                                    <UploadPreview
                                        preview={step1.preview}
                                        isSourceCreated={!!wizard.sourceId}
                                        onClearFile={step1.handleClearFile}
                                    />
                                </div>
                            ) : (
                                <div className="text-center space-y-4 max-w-md text-muted-foreground opacity-50">
                                    <div className="aspect-video rounded-lg border-2 border-dashed flex items-center justify-center bg-slate-100 dark:bg-slate-900">
                                        Data Preview
                                    </div>
                                    <p>Select a CSV file to preview its content and map columns.</p>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="max-w-4xl mx-auto">
                            <ValidationView wizard={wizard} />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
