"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type StepState = "completed" | "active" | "pending";

interface VersionProgress {
    builds_total: number;
    builds_ingested: number;
    builds_missing_resource: number;
    builds_processed: number;
    builds_processing_failed: number;
}

interface Step {
    id: string;
    label: string;
    getCurrent: (p: VersionProgress | null) => number;
    getTotal: (p: VersionProgress | null) => number;
    getState: (status: string, p: VersionProgress | null) => StepState;
}

const STEPS: Step[] = [
    {
        id: "ingestion",
        label: "Ingestion",
        getCurrent: (p) => (p?.builds_ingested || 0) + (p?.builds_missing_resource || 0),
        getTotal: (p) => p?.builds_total || 0,
        getState: (status, p) => {
            const s = status.toLowerCase();
            if (["ingested", "processing", "processed"].includes(s)) return "completed";
            if (["ingesting", "queued"].includes(s)) return "active";
            return "pending";
        },
    },
    {
        id: "processing",
        label: "Processing",
        getCurrent: (p) => (p?.builds_processed || 0) + (p?.builds_processing_failed || 0),
        getTotal: (p) => p?.builds_ingested || 0,
        getState: (status, p) => {
            const s = status.toLowerCase();
            if (s === "processed") return "completed";
            if (s === "processing") return "active";
            return "pending";
        },
    },
];

function StepIcon({ state }: { state: StepState }) {
    if (state === "completed") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    if (state === "active") return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    return <Circle className="h-4 w-4 text-slate-300 dark:text-slate-600" />;
}

interface VersionMiniStepperProps {
    status: string;
    progress: VersionProgress | null;
}

export function VersionMiniStepper({ status, progress }: VersionMiniStepperProps) {
    return (
        <div className="flex items-center justify-center py-4">
            <div className="inline-flex items-center gap-2 py-3 px-6 bg-slate-50 dark:bg-slate-900/50 rounded-lg">
                {STEPS.map((step, i) => {
                    const state = step.getState(status, progress);
                    const current = step.getCurrent(progress);
                    const total = step.getTotal(progress);
                    const isLast = i === STEPS.length - 1;

                    return (
                        <div key={step.id} className="flex items-center">
                            <div className="flex items-center gap-2">
                                <StepIcon state={state} />
                                <div className="flex flex-col">
                                    <span className={cn(
                                        "text-sm font-medium",
                                        state === "completed" && "text-green-600",
                                        state === "active" && "text-blue-600",
                                        state === "pending" && "text-slate-400"
                                    )}>
                                        {step.label}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {total > 0 ? `${current}/${total}` : "—"}
                                    </span>
                                </div>
                            </div>
                            {!isLast && (
                                <div className={cn(
                                    "w-24 h-0.5 mx-4",
                                    state === "completed" ? "bg-green-500" : "bg-slate-200 dark:bg-slate-700"
                                )} />
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
