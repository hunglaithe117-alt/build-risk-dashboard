"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ImportProgress {
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
        total: number;
    };
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

type PipelinePhase = "fetch" | "ingest" | "extract" | "predict";
type StepState = "completed" | "active" | "pending" | "error";

interface PipelineStep {
    id: PipelinePhase;
    label: string;
    description: string;
}

const PIPELINE_STEPS: PipelineStep[] = [
    { id: "fetch", label: "Fetch", description: "Download build metadata from CI" },
    { id: "ingest", label: "Ingest", description: "Clone repo, worktrees, logs" },
    { id: "extract", label: "Extract", description: "Extract features from builds" },
    { id: "predict", label: "Predict", description: "Run risk prediction model" },
];

interface PipelineStepperProps {
    status: string;
    progress: ImportProgress | null;
}

function getStepState(
    step: PipelinePhase,
    status: string,
    progress: ImportProgress | null
): StepState {
    const statusLower = status.toLowerCase();

    switch (step) {
        case "fetch":
            // Fetch is complete once we have any builds
            if (progress && progress.import_builds.total > 0) {
                return "completed";
            }
            if (statusLower === "queued" || statusLower === "fetching") {
                return "active";
            }
            return "pending";

        case "ingest":
            if (statusLower === "ingested") {
                return "completed";
            }
            if (["processing", "processed"].includes(statusLower)) {
                return "completed"; // Already past ingestion
            }
            if (statusLower === "ingesting") {
                return "active";
            }
            // If failed but we have ingested builds, it might be partial? 
            // But backend status only has FAILED or INGESTING/INGESTED.
            // Let's rely on valid statuses.
            if (statusLower === "failed" && progress?.import_builds.ingested === 0) {
                return "error";
            }
            return "pending";

        case "extract":
            if (statusLower === "processed") {
                return "completed";
            }
            if (statusLower === "processing") {
                return "active";
            }
            // If ingestion is done, extraction is next (pending or active)
            if (statusLower === "ingested") {
                return "pending";
            }
            return "pending";

        case "predict":
            const hasAllPredictions =
                progress?.training_builds.with_prediction &&
                progress.training_builds.with_prediction >= progress.training_builds.completed;

            if (hasAllPredictions && statusLower === "processed") {
                return "completed";
            }
            if (progress?.training_builds.prediction_failed) {
                return "error";
            }
            if (
                progress?.training_builds.pending_prediction &&
                progress.training_builds.pending_prediction > 0
            ) {
                return "active";
            }
            if (statusLower === "processed") {
                // Check if prediction is in progress
                if (progress?.training_builds.with_prediction) {
                    return progress.training_builds.with_prediction >=
                        (progress.training_builds.completed + progress.training_builds.partial)
                        ? "completed"
                        : "active";
                }
            }
            return "pending";
    }
}

function getStepCount(
    step: PipelinePhase,
    progress: ImportProgress | null
): { current: number; total: number } | null {
    if (!progress) return null;

    switch (step) {
        case "fetch":
            return {
                current: progress.import_builds.total,
                total: progress.import_builds.total,
            };
        case "ingest":
            return {
                current: progress.import_builds.ingested,
                total: progress.import_builds.total,
            };
        case "extract":
            return {
                current: progress.training_builds.completed + progress.training_builds.partial,
                total: progress.training_builds.total || progress.import_builds.ingested,
            };
        case "predict":
            return {
                current: progress.training_builds.with_prediction || 0,
                total: progress.training_builds.completed + progress.training_builds.partial,
            };
    }
}

function StepIcon({ state }: { state: StepState }) {
    if (state === "completed") {
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    }
    if (state === "active") {
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    }
    if (state === "error") {
        return <XCircle className="h-5 w-5 text-red-500" />;
    }
    return <Circle className="h-5 w-5 text-slate-300 dark:text-slate-600" />;
}

export function PipelineStepper({ status, progress }: PipelineStepperProps) {
    return (
        <div className="w-full">
            <div className="flex items-center justify-between">
                {PIPELINE_STEPS.map((step, index) => {
                    const state = getStepState(step.id, status, progress);
                    const counts = getStepCount(step.id, progress);
                    const isLast = index === PIPELINE_STEPS.length - 1;

                    return (
                        <div key={step.id} className="flex items-center flex-1">
                            {/* Step */}
                            <div className="flex flex-col items-center">
                                {/* Icon */}
                                <div
                                    className={cn(
                                        "flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors",
                                        state === "completed" && "border-green-500 bg-green-50 dark:bg-green-950",
                                        state === "active" && "border-blue-500 bg-blue-50 dark:bg-blue-950",
                                        state === "error" && "border-red-500 bg-red-50 dark:bg-red-950",
                                        state === "pending" && "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900"
                                    )}
                                >
                                    <StepIcon state={state} />
                                </div>

                                {/* Label */}
                                <span
                                    className={cn(
                                        "mt-2 text-sm font-medium",
                                        state === "completed" && "text-green-600 dark:text-green-400",
                                        state === "active" && "text-blue-600 dark:text-blue-400",
                                        state === "error" && "text-red-600 dark:text-red-400",
                                        state === "pending" && "text-slate-400 dark:text-slate-500"
                                    )}
                                >
                                    {step.label}
                                </span>

                                {/* Count */}
                                {counts && counts.total > 0 && (
                                    <span
                                        className={cn(
                                            "text-xs",
                                            state === "completed" && "text-green-500",
                                            state === "active" && "text-blue-500",
                                            state === "error" && "text-red-500",
                                            state === "pending" && "text-slate-400"
                                        )}
                                    >
                                        {counts.current}/{counts.total}
                                    </span>
                                )}
                                {(!counts || counts.total === 0) && (
                                    <span className="text-xs text-slate-400">—</span>
                                )}
                            </div>

                            {/* Connector Line */}
                            {!isLast && (
                                <div
                                    className={cn(
                                        "flex-1 h-0.5 mx-2 transition-colors",
                                        state === "completed"
                                            ? "bg-green-500"
                                            : "bg-slate-200 dark:bg-slate-700"
                                    )}
                                />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
