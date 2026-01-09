"use client";

import { memo, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    Clock,
    Download,
    Eye,
    FileJson,
    FileSpreadsheet,
    FileText,
    Loader2,
    Play,
    RefreshCw,
    RotateCcw,
    Trash2,
    XCircle,
} from "lucide-react";
import { formatDateTime } from "@/lib/utils";
import type { DatasetVersion } from "../_hooks/useDatasetVersions";

type ExportFormat = "csv" | "json";

interface VersionHistoryProps {
    datasetId: string;
    versions: DatasetVersion[];
    loading: boolean;
    onRefresh: () => void;
    onDownload: (versionId: string, format?: ExportFormat) => void;
    onDelete: (versionId: string) => void;
    // Processing control
    onStartProcessing: (versionId: string) => void;
    onRetryIngestion: (versionId: string) => void;
    onRetryProcessing: (versionId: string) => void;
}

// Status types that are "active" (in progress)
const ACTIVE_STATUSES = ["queued", "ingesting", "processing"];
// Status types that can trigger start processing
const CAN_START_PROCESSING = ["ingested"];

export const VersionHistory = memo(function VersionHistory({
    datasetId,
    versions,
    loading,
    onRefresh,
    onDownload,
    onDelete,
    onStartProcessing,
    onRetryIngestion,
    onRetryProcessing,
}: VersionHistoryProps) {
    const router = useRouter();

    // Separate active version from completed ones
    const activeVersion = versions.find((v) => ACTIVE_STATUSES.includes(v.status));
    // Versions waiting for user action
    const waitingVersion = versions.find((v) => CAN_START_PROCESSING.includes(v.status));
    const completedVersions = versions.filter(
        (v) => !ACTIVE_STATUSES.includes(v.status) && !CAN_START_PROCESSING.includes(v.status)
    );

    return (
        <div className="space-y-4">
            {/* Active Version Progress */}
            {activeVersion && (
                <ActiveVersionCard version={activeVersion} datasetId={datasetId} />
            )}

            {/* Waiting for user action - Start Processing */}
            {waitingVersion && (
                <WaitingVersionCard
                    version={waitingVersion}
                    onStartProcessing={() => onStartProcessing(waitingVersion.id)}
                    onRetryIngestion={() => onRetryIngestion(waitingVersion.id)}
                />
            )}

            {/* Version History */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                Version History
                            </CardTitle>
                            <CardDescription>
                                {completedVersions.length} version(s) created
                            </CardDescription>
                        </div>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={onRefresh}
                            disabled={loading}
                        >
                            <RefreshCw
                                className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
                            />
                        </Button>
                    </div>
                </CardHeader>

                <CardContent>
                    {loading && versions.length === 0 ? (
                        <div className="flex items-center justify-center py-8 text-muted-foreground">
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Loading versions...
                        </div>
                    ) : completedVersions.length === 0 ? (
                        <div className="py-8 text-center text-muted-foreground">
                            No versions created yet. Select features above and click
                            &quot;Create Version&quot; to get started.
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {completedVersions.map((version) => (
                                <VersionCard
                                    key={version.id}
                                    version={version}
                                    onView={() => {
                                        router.push(`/projects/${datasetId}/versions/${version.id}`);
                                    }}
                                    onDownload={(format) => onDownload(version.id, format)}
                                    onDelete={() => onDelete(version.id)}
                                />
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
});

interface ActiveVersionCardProps {
    version: DatasetVersion;
    datasetId: string;
}

function ActiveVersionCard({ version, datasetId }: ActiveVersionCardProps) {
    const router = useRouter();
    // Determine current phase
    const isIngesting = version.status.startsWith("ingesting");

    const handleClick = () => {
        router.push(`/projects/${datasetId}/versions/${version.id}/builds`);
    };

    return (
        <Card
            className="border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20 cursor-pointer transition-all hover:shadow-md hover:border-blue-300"
            onClick={handleClick}
        >
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        {isIngesting ? "Ingesting" : "Processing"}: {version.name}
                    </CardTitle>
                    <Eye className="h-4 w-4 text-muted-foreground" />
                </div>
            </CardHeader>
            <CardContent className="space-y-2">
                <Progress value={version.progress_percent} className="h-2" />
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                        {version.builds_features_extracted.toLocaleString()} /{" "}
                        {version.builds_total.toLocaleString()} builds
                    </span>
                    <span>{version.progress_percent.toFixed(1)}%</span>
                </div>
                {version.builds_extraction_failed > 0 && (
                    <p className="text-sm text-amber-600">
                        ⚠️ {version.builds_extraction_failed} builds failed
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

// Card for versions waiting for user action (ingesting complete/partial)
interface WaitingVersionCardProps {
    version: DatasetVersion;
    onStartProcessing: () => void;
    onRetryIngestion: () => void;
}

function WaitingVersionCard({ version, onStartProcessing, onRetryIngestion }: WaitingVersionCardProps) {
    const hasMissingResource = version.builds_missing_resource > 0;

    return (
        <Card className={hasMissingResource
            ? "border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20"
            : "border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20"
        }>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <CheckCircle2 className={`h-4 w-4 ${hasMissingResource ? "text-amber-500" : "text-green-500"}`} />
                        Ingestion Complete: {version.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        {hasMissingResource && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={onRetryIngestion}
                            >
                                <RotateCcw className="mr-1 h-4 w-4" />
                                Retry Failed
                            </Button>
                        )}
                        <Button
                            size="sm"
                            onClick={onStartProcessing}
                            className="bg-green-600 hover:bg-green-700"
                        >
                            <Play className="mr-1 h-4 w-4" />
                            Start Processing
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <p className="text-sm text-muted-foreground">
                    {version.builds_ingested} / {version.builds_total} builds ingested.
                    {hasMissingResource && ` ${version.builds_missing_resource} missing resources.`}
                    {" "}Click &quot;Start Processing&quot; to begin feature extraction.
                </p>
            </CardContent>
        </Card>
    );
}

interface VersionCardProps {
    version: DatasetVersion;
    onView: () => void;
    onDownload: (format: ExportFormat) => void;
    onDelete: () => void;
    onRetryProcessing?: () => void;
}

function VersionCard({ version, onView, onDownload, onDelete, onRetryProcessing }: VersionCardProps) {
    const [downloading, setDownloading] = useState(false);

    const statusConfig: Record<
        string,
        { icon: typeof CheckCircle2; color: string; label: string }
    > = {
        queued: {
            icon: Clock,
            color: "text-gray-500",
            label: "Queued",
        },
        ingesting: {
            icon: Loader2,
            color: "text-blue-500",
            label: "Ingesting",
        },
        ingested: {
            icon: CheckCircle2,
            color: "text-emerald-500",
            label: "Ingested",
        },
        processing: {
            icon: Loader2,
            color: "text-purple-500",
            label: "Processing",
        },
        processed: {
            icon: CheckCircle2,
            color: "text-green-500",
            label: "Processed",
        },
        failed: {
            icon: XCircle,
            color: "text-red-500",
            label: "Failed",
        },
    };

    const status = statusConfig[version.status] || { icon: Clock, color: "text-gray-400", label: version.status };
    const StatusIcon = status.icon;

    const handleDownload = async (format: ExportFormat) => {
        setDownloading(true);
        try {
            await onDownload(format);
        } finally {
            setDownloading(false);
        }
    };

    const formatOptions: { format: ExportFormat; label: string; icon: typeof FileText }[] = [
        { format: "csv", label: "CSV", icon: FileSpreadsheet },
        { format: "json", label: "JSON", icon: FileJson },
    ];

    return (
        <div className="flex items-center justify-between rounded-lg border bg-white p-4 dark:bg-slate-900">
            <div className="flex items-center gap-4">
                <StatusIcon className={`h-5 w-5 ${status.color}`} />
                <div>
                    <div className="flex items-center gap-2">
                        <span className="font-medium">{version.name}</span>
                        <Badge variant="outline" className="text-xs">
                            {version.selected_features.length} features
                        </Badge>
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                        <span>
                            {version.builds_features_extracted.toLocaleString()} /{" "}
                            {version.builds_total.toLocaleString()} builds
                        </span>
                        <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatDateTime(version.created_at)}
                        </span>
                    </div>
                    {version.error_message && (
                        <p className="mt-1 text-xs text-red-500">
                            {version.error_message}
                        </p>
                    )}
                </div>
            </div>

            <div className="flex items-center gap-2">
                {version.status === "processed" && (
                    <>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={onView}
                            className="text-muted-foreground hover:text-foreground"
                        >
                            <Eye className="h-4 w-4" />
                        </Button>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" size="sm" disabled={downloading}>
                                    {downloading ? (
                                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                                    ) : (
                                        <Download className="mr-1 h-4 w-4" />
                                    )}
                                    Download
                                    <ChevronDown className="ml-1 h-3 w-3" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                {formatOptions.map(({ format, label, icon: Icon }) => (
                                    <DropdownMenuItem
                                        key={format}
                                        onClick={() => handleDownload(format)}
                                    >
                                        <Icon className="mr-2 h-4 w-4" />
                                        {label}
                                    </DropdownMenuItem>
                                ))}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </>
                )}
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={onDelete}
                    className="text-muted-foreground hover:text-destructive"
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
}
