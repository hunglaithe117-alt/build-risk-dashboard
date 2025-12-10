"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StepIndicatorProps } from "./types";

const STEP_LABELS = {
    1: "Upload",
    2: "Configure",
    3: "Sources",
    4: "Features",
} as const;

export function StepIndicator({ currentStep }: StepIndicatorProps) {
    return (
        <div className="flex items-center justify-center gap-4 mb-8">
            {([1, 2, 3, 4] as const).map((s, i) => (
                <div key={s} className="flex items-center gap-4">
                    <div className="flex flex-col items-center gap-1">
                        <div className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold transition-all",
                            currentStep === s ? "bg-blue-500 text-white shadow-lg shadow-blue-500/30" :
                                currentStep > s ? "bg-emerald-500 text-white" :
                                    "bg-slate-200 text-slate-500 dark:bg-slate-700"
                        )}>
                            {currentStep > s ? <Check className="h-5 w-5" /> : s}
                        </div>
                        <span className={cn(
                            "text-xs font-medium",
                            currentStep === s ? "text-blue-600" : "text-muted-foreground"
                        )}>
                            {STEP_LABELS[s]}
                        </span>
                    </div>
                    {i < 3 && (
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
