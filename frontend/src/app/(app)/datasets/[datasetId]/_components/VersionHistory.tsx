"use client";

import { memo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    Download,
    Loader2,
    RefreshCw,
    Trash2,
    X,
    XCircle,
} from "lucide-react";
import type { DatasetVersion } from "../_hooks/useDatasetVersions";

interface VersionHistoryProps {
    versions: DatasetVersion[];
    loading: boolean;
    onRefresh: () => void;
    onDownload: (versionId: string) => void;
    onDelete: (versionId: string) => void;
    onCancel: (versionId: string) => void;
}

export const VersionHistory = memo(function VersionHistory({
    versions,
    loading,
    onRefresh,
    onDownload,
    onDelete,
    onCancel,
}: VersionHistoryProps) {
    // Separate active version from completed ones
    const activeVersion = versions.find(
        (v) => v.status === "pending" || v.status === "processing"
    );
    const completedVersions = versions.filter(
        (v) => v.status !== "pending" && v.status !== "processing"
    );

    return (
        <div className="space-y-4">
            {/* Active Version Progress */}
            {activeVersion && (
                <ActiveVersionCard version={activeVersion} onCancel={onCancel} />
            )}

            {/* Version History */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                📚 Version History
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
                                    onDownload={() => onDownload(version.id)}
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
    onCancel: (versionId: string) => void;
}

function ActiveVersionCard({ version, onCancel }: ActiveVersionCardProps) {
    return (
        <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        Processing: {version.name}
                    </CardTitle>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onCancel(version.id)}
                        className="text-destructive hover:text-destructive"
                    >
                        <X className="mr-1 h-4 w-4" />
                        Cancel
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-2">
                <Progress value={version.progress_percent} className="h-2" />
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                        {version.processed_rows.toLocaleString()} /{" "}
                        {version.total_rows.toLocaleString()} rows
                    </span>
                    <span>{version.progress_percent.toFixed(1)}%</span>
                </div>
                {version.failed_rows > 0 && (
                    <p className="text-sm text-amber-600">
                        ⚠️ {version.failed_rows} rows failed
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

interface VersionCardProps {
    version: DatasetVersion;
    onDownload: () => void;
    onDelete: () => void;
}

function VersionCard({ version, onDownload, onDelete }: VersionCardProps) {
    const statusConfig: Record<
        string,
        { icon: typeof CheckCircle2; color: string; label: string }
    > = {
        completed: {
            icon: CheckCircle2,
            color: "text-green-500",
            label: "Completed",
        },
        failed: {
            icon: XCircle,
            color: "text-red-500",
            label: "Failed",
        },
        cancelled: {
            icon: AlertCircle,
            color: "text-slate-500",
            label: "Cancelled",
        },
    };

    const status = statusConfig[version.status] || statusConfig.failed;
    const StatusIcon = status.icon;

    // Format file size
    const formatSize = (bytes: number | null): string => {
        if (!bytes) return "—";
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    // Format relative time
    const formatTime = (dateStr: string | null): string => {
        if (!dateStr) return "—";
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return "Just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    };

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
                            {version.enriched_rows.toLocaleString()} /{" "}
                            {version.total_rows.toLocaleString()} rows
                        </span>
                        {version.file_size_bytes && (
                            <span>{formatSize(version.file_size_bytes)}</span>
                        )}
                        <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatTime(version.created_at)}
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
                {version.status === "completed" && (
                    <Button variant="outline" size="sm" onClick={onDownload}>
                        <Download className="mr-1 h-4 w-4" />
                        Download
                    </Button>
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
