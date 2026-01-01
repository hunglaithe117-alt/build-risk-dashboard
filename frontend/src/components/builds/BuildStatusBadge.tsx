"use client";

import {
    CheckCircle2,
    Clock,
    Loader2,
    XCircle,
    AlertTriangle,
    CircleDot,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type IngestionStatus = "pending" | "fetched" | "ingesting" | "ingested" | "failed" | "missing_resource";
type ExtractionStatus = "pending" | "in_progress" | "completed" | "partial" | "failed";

interface StatusConfig {
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bgColor: string;
    label: string;
    animate?: boolean;
}

const INGESTION_STATUS_CONFIG: Record<string, StatusConfig> = {
    pending: {
        icon: Clock,
        color: "text-gray-500",
        bgColor: "bg-gray-100 dark:bg-gray-800",
        label: "Pending",
    },
    fetched: {
        icon: CircleDot,
        color: "text-blue-500",
        bgColor: "bg-blue-100 dark:bg-blue-900/30",
        label: "Fetched",
    },
    ingesting: {
        icon: Loader2,
        color: "text-blue-500",
        bgColor: "bg-blue-100 dark:bg-blue-900/30",
        label: "Ingesting",
        animate: true,
    },
    ingested: {
        icon: CheckCircle2,
        color: "text-green-500",
        bgColor: "bg-green-100 dark:bg-green-900/30",
        label: "Ingested",
    },
    failed: {
        icon: XCircle,
        color: "text-red-500",
        bgColor: "bg-red-100 dark:bg-red-900/30",
        label: "Failed",
    },
    missing_resource: {
        icon: AlertTriangle,
        color: "text-amber-500",
        bgColor: "bg-amber-100 dark:bg-amber-900/30",
        label: "Missing Resource",
    },
};

const EXTRACTION_STATUS_CONFIG: Record<string, StatusConfig> = {
    pending: {
        icon: Clock,
        color: "text-gray-500",
        bgColor: "bg-gray-100 dark:bg-gray-800",
        label: "Pending",
    },
    in_progress: {
        icon: Loader2,
        color: "text-blue-500",
        bgColor: "bg-blue-100 dark:bg-blue-900/30",
        label: "Processing",
        animate: true,
    },
    completed: {
        icon: CheckCircle2,
        color: "text-green-500",
        bgColor: "bg-green-100 dark:bg-green-900/30",
        label: "Completed",
    },
    partial: {
        icon: AlertTriangle,
        color: "text-amber-500",
        bgColor: "bg-amber-100 dark:bg-amber-900/30",
        label: "Partial",
    },
    failed: {
        icon: XCircle,
        color: "text-red-500",
        bgColor: "bg-red-100 dark:bg-red-900/30",
        label: "Failed",
    },
};

interface IngestionStatusBadgeProps {
    status: string;
    className?: string;
}

/**
 * Badge component for ingestion phase status.
 * Distinguishes between FAILED (retryable) and MISSING_RESOURCE (not retryable).
 */
export function IngestionStatusBadge({ status, className }: IngestionStatusBadgeProps) {
    const config = INGESTION_STATUS_CONFIG[status.toLowerCase()] || INGESTION_STATUS_CONFIG.pending;
    const Icon = config.icon;

    return (
        <Badge
            variant="secondary"
            className={cn(
                "gap-1.5 font-medium",
                config.bgColor,
                config.color,
                className
            )}
        >
            <Icon className={cn("h-3.5 w-3.5", config.animate && "animate-spin")} />
            {config.label}
        </Badge>
    );
}

interface ExtractionStatusBadgeProps {
    status: string;
    className?: string;
}

/**
 * Badge component for extraction/processing phase status.
 */
export function ExtractionStatusBadge({ status, className }: ExtractionStatusBadgeProps) {
    const config = EXTRACTION_STATUS_CONFIG[status.toLowerCase()] || EXTRACTION_STATUS_CONFIG.pending;
    const Icon = config.icon;

    return (
        <Badge
            variant="secondary"
            className={cn(
                "gap-1.5 font-medium",
                config.bgColor,
                config.color,
                className
            )}
        >
            <Icon className={cn("h-3.5 w-3.5", config.animate && "animate-spin")} />
            {config.label}
        </Badge>
    );
}

interface ResourceStatusIndicatorProps {
    status: string;
    resourceName: string;
    error?: string | null;
}

/**
 * Compact indicator for individual resource status.
 */
export function ResourceStatusIndicator({ status, resourceName, error }: ResourceStatusIndicatorProps) {
    const s = status?.toLowerCase() || "pending";

    let IconComponent = Clock;
    let colorClass = "text-gray-400";

    if (s === "completed" || s === "skipped") {
        IconComponent = CheckCircle2;
        colorClass = "text-green-500";
    } else if (s === "failed") {
        IconComponent = XCircle;
        colorClass = "text-red-500";
    } else if (s === "in_progress") {
        IconComponent = Loader2;
        colorClass = "text-blue-500";
    }

    return (
        <div className="flex items-start gap-2 p-2 rounded-lg border bg-background">
            <IconComponent
                className={cn(
                    "h-4 w-4 mt-0.5 flex-shrink-0",
                    colorClass,
                    s === "in_progress" && "animate-spin"
                )}
            />
            <div className="min-w-0 flex-1">
                <p className="text-xs font-medium font-mono truncate">{resourceName}</p>
                <p className="text-[10px] text-muted-foreground capitalize">{status}</p>
                {error && (
                    <p className="text-[10px] text-red-500 mt-0.5 break-words leading-tight">
                        {error}
                    </p>
                )}
            </div>
        </div>
    );
}

// Re-export configs for external use
export { INGESTION_STATUS_CONFIG, EXTRACTION_STATUS_CONFIG };
export type { IngestionStatus, ExtractionStatus };
