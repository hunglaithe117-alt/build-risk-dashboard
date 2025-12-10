"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PipelineStage {
    id: string;
    name: string;
    status: "pending" | "running" | "completed" | "failed" | "skipped";
    duration_ms?: number;
    error?: string;
}

interface PipelineStagesProps {
    stages: PipelineStage[];
    className?: string;
}

export function PipelineStages({ stages, className }: PipelineStagesProps) {
    if (!stages || stages.length === 0) {
        return null;
    }

    const formatDuration = (ms?: number) => {
        if (!ms) return "";
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(1)}s`;
    };

    return (
        <div className={cn("space-y-1", className)}>
            <p className="text-xs text-muted-foreground mb-2">Pipeline Stages</p>
            <div className="space-y-1.5">
                {stages.map((stage, index) => (
                    <div
                        key={stage.id}
                        className={cn(
                            "flex items-center gap-2 text-xs rounded px-2 py-1.5",
                            stage.status === "running" && "bg-blue-50 dark:bg-blue-900/20",
                            stage.status === "completed" && "bg-emerald-50/50 dark:bg-emerald-900/10",
                            stage.status === "failed" && "bg-red-50 dark:bg-red-900/20",
                        )}
                    >
                        {/* Icon */}
                        {stage.status === "pending" && (
                            <Circle className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                        {stage.status === "running" && (
                            <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin" />
                        )}
                        {stage.status === "completed" && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        )}
                        {stage.status === "failed" && (
                            <Circle className="h-3.5 w-3.5 text-red-500 fill-red-500" />
                        )}
                        {stage.status === "skipped" && (
                            <Circle className="h-3.5 w-3.5 text-muted-foreground/50" />
                        )}

                        {/* Name */}
                        <span
                            className={cn(
                                "flex-1",
                                stage.status === "pending" && "text-muted-foreground",
                                stage.status === "running" && "text-blue-700 dark:text-blue-300 font-medium",
                                stage.status === "completed" && "text-emerald-700 dark:text-emerald-300",
                                stage.status === "failed" && "text-red-700 dark:text-red-300",
                                stage.status === "skipped" && "text-muted-foreground/50 line-through",
                            )}
                        >
                            {stage.name}
                        </span>

                        {/* Duration */}
                        {stage.duration_ms && stage.status === "completed" && (
                            <span className="text-muted-foreground">
                                {formatDuration(stage.duration_ms)}
                            </span>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
