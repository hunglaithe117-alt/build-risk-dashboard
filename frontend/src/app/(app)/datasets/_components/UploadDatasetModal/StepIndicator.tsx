"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StepIndicatorProps } from "./types";

const STEP_LABELS = {
    1: "Upload",
    2: "Configure",
    3: "Review",
} as const;

export function StepIndicator({ currentStep }: StepIndicatorProps) {
    return (
        <div className="flex items-center justify-center gap-3 mb-8">
            {([1, 2, 3] as const).map((s, i) => (
                <div key={s} className="flex items-center gap-3">
                    <div className="flex flex-col items-center gap-1">
                        <div className={cn(
                            "flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold transition-all",
                            currentStep === s ? "bg-blue-500 text-white shadow-lg shadow-blue-500/30" :
                                currentStep > s ? "bg-emerald-500 text-white" :
                                    "bg-slate-200 text-slate-500 dark:bg-slate-700"
                        )}>
                            {currentStep > s ? <Check className="h-4 w-4" /> : s}
                        </div>
                        <span className={cn(
                            "text-xs font-medium whitespace-nowrap",
                            currentStep === s ? "text-blue-600" : "text-muted-foreground"
                        )}>
                            {STEP_LABELS[s]}
                        </span>
                    </div>
                    {i < 2 && (
                        <div className={cn(
                            "h-1 w-12 rounded-full transition-colors",
                            currentStep > s ? "bg-emerald-500" : "bg-slate-200 dark:bg-slate-700"
                        )} />
                    )}
                </div>
            ))}
        </div>
    );
}
