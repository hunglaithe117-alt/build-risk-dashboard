"use client";

import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, ArrowRight } from "lucide-react";

interface ExecutionLevel {
    level: number;
    nodes: string[];
}

interface ExtractionPlanTimelineProps {
    executionLevels: ExecutionLevel[];
    nodeLabels?: Record<string, string>;
    activeNodes?: Set<string>;
}

export function ExtractionPlanTimeline({
    executionLevels,
    nodeLabels = {},
    activeNodes = new Set(),
}: ExtractionPlanTimelineProps) {
    if (executionLevels.length === 0) {
        return null;
    }

    // Filter to only levels with active nodes
    const activeLevels = executionLevels
        .map((level) => ({
            ...level,
            nodes: level.nodes.filter((n) => activeNodes.has(n)),
        }))
        .filter((level) => level.nodes.length > 0);

    if (activeLevels.length === 0) {
        return (
            <div className="rounded-xl border bg-slate-50/50 dark:bg-slate-900/20 p-4">
                <p className="text-sm text-muted-foreground text-center">
                    Select features to see the extraction plan.
                </p>
            </div>
        );
    }

    return (
        <div className="rounded-xl border bg-white dark:bg-slate-900 p-4 space-y-3">
            <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">Extraction Plan</span>
                <Badge variant="outline">{activeLevels.length} steps</Badge>
            </div>

            <div className="flex items-center gap-2 overflow-x-auto pb-2">
                {activeLevels.map((level, idx) => (
                    <div key={level.level} className="flex items-center gap-2">
                        <div className="flex flex-col items-center gap-1 min-w-[100px]">
                            <div className="flex items-center gap-1.5">
                                <div className="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-xs font-bold">
                                    {idx + 1}
                                </div>
                                <span className="text-xs font-medium text-muted-foreground">
                                    Step {idx + 1}
                                </span>
                            </div>
                            <div className="flex flex-wrap gap-1 justify-center">
                                {level.nodes.map((node) => (
                                    <Badge
                                        key={node}
                                        variant="secondary"
                                        className="text-[10px] px-1.5 py-0.5"
                                    >
                                        {nodeLabels[node] || node.replace(/_/g, " ")}
                                    </Badge>
                                ))}
                            </div>
                        </div>

                        {idx < activeLevels.length - 1 && (
                            <ArrowRight className="h-4 w-4 text-slate-400 flex-shrink-0" />
                        )}
                    </div>
                ))}

                <div className="flex items-center gap-1.5 ml-2">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    <span className="text-xs font-medium text-green-600 dark:text-green-400">
                        Done
                    </span>
                </div>
            </div>
        </div>
    );
}
