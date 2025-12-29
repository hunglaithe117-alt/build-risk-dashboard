"use client";

import { useState } from "react";
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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    CheckCircle2,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Clock,
    Download,
    FileJson,
    FileSpreadsheet,
    FileText,
    Loader2,
    RefreshCw,
    Trash2,
    XCircle,
    AlertCircle,
} from "lucide-react";
import type { DatasetVersion } from "../_hooks/useDatasetVersions";

type ExportFormat = "csv" | "json";

interface VersionHistoryTableProps {
    datasetId: string;
    versions: DatasetVersion[];
    loading: boolean;
    onRefresh: () => void;
    onDownload: (versionId: string, format?: ExportFormat) => void;
    onDelete: (versionId: string) => void;
}

const ITEMS_PER_PAGE = 10;

export function VersionHistoryTable({
    datasetId,
    versions,
    loading,
    onRefresh,
    onDownload,
    onDelete,
}: VersionHistoryTableProps) {
    const router = useRouter();
    const [currentPage, setCurrentPage] = useState(1);
    const [downloadingId, setDownloadingId] = useState<string | null>(null);

    // Filter completed versions (not pending/ingesting/processing)
    const completedVersions = versions.filter(
        (version) => version.status !== "pending" && version.status !== "ingesting" && version.status !== "processing"
    );

    // Pagination
    const totalPages = Math.ceil(completedVersions.length / ITEMS_PER_PAGE);
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const paginatedVersions = completedVersions.slice(startIndex, startIndex + ITEMS_PER_PAGE);

    // Navigate to version detail
    const handleViewVersion = (versionId: string) => {
        router.push(`/projects/${datasetId}/versions/${versionId}`);
    };

    // Handle download
    const handleDownload = async (versionId: string, format: ExportFormat) => {
        setDownloadingId(versionId);
        try {
            await onDownload(versionId, format);
        } finally {
            setDownloadingId(null);
        }
    };

    // Format relative time
    const formatRelativeTime = (dateStr: string | null): string => {
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

    // Status config
    const getStatusConfig = (status: string) => {
        const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
            completed: { icon: CheckCircle2, color: "text-green-500", label: "Completed" },
            failed: { icon: XCircle, color: "text-red-500", label: "Failed" },
            cancelled: { icon: AlertCircle, color: "text-slate-500", label: "Cancelled" },
        };
        return config[status] || config.failed;
    };

    const formatOptions: { format: ExportFormat; label: string; icon: typeof FileText }[] = [
        { format: "csv", label: "CSV", icon: FileSpreadsheet },
        { format: "json", label: "JSON", icon: FileJson },
    ];

    return (
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
                    <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
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
                        No versions created yet. Click &quot;Create New Version&quot; to get started.
                    </div>
                ) : (
                    <>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="text-center">Features</TableHead>
                                    <TableHead className="text-right">Rows</TableHead>
                                    <TableHead>Created</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {paginatedVersions.map((version) => {
                                    const statusConfig = getStatusConfig(version.status);
                                    const StatusIcon = statusConfig.icon;
                                    const isDownloading = downloadingId === version.id;

                                    return (
                                        <TableRow
                                            key={version.id}
                                            className="cursor-pointer hover:bg-muted/50"
                                            onClick={() => handleViewVersion(version.id)}
                                        >
                                            <TableCell className="font-medium">
                                                {version.name}
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-2">
                                                    <StatusIcon className={`h-4 w-4 ${statusConfig.color}`} />
                                                    <span className="text-sm">{statusConfig.label}</span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-center">
                                                <Badge variant="outline">
                                                    {version.selected_features.length}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <span className="text-muted-foreground">
                                                    {version.enriched_rows.toLocaleString()} /{" "}
                                                    {version.total_rows.toLocaleString()}
                                                </span>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-1 text-muted-foreground">
                                                    <Clock className="h-3 w-3" />
                                                    <span className="text-sm">
                                                        {formatRelativeTime(version.created_at)}
                                                    </span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <div
                                                    className="flex items-center justify-end gap-1"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    {version.status === "completed" && (
                                                        <DropdownMenu>
                                                            <DropdownMenuTrigger asChild>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    disabled={isDownloading}
                                                                >
                                                                    {isDownloading ? (
                                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                                    ) : (
                                                                        <Download className="h-4 w-4" />
                                                                    )}
                                                                    <ChevronDown className="ml-1 h-3 w-3" />
                                                                </Button>
                                                            </DropdownMenuTrigger>
                                                            <DropdownMenuContent align="end">
                                                                {formatOptions.map(({ format, label, icon: Icon }) => (
                                                                    <DropdownMenuItem
                                                                        key={format}
                                                                        onClick={() => handleDownload(version.id, format)}
                                                                    >
                                                                        <Icon className="mr-2 h-4 w-4" />
                                                                        {label}
                                                                    </DropdownMenuItem>
                                                                ))}
                                                            </DropdownMenuContent>
                                                        </DropdownMenu>
                                                    )}
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => onDelete(version.id)}
                                                        className="text-muted-foreground hover:text-destructive"
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="mt-4 flex items-center justify-between">
                                <p className="text-sm text-muted-foreground">
                                    Showing {startIndex + 1}-{Math.min(startIndex + ITEMS_PER_PAGE, completedVersions.length)} of{" "}
                                    {completedVersions.length}
                                </p>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                                        disabled={currentPage === 1}
                                    >
                                        <ChevronLeft className="h-4 w-4" />
                                    </Button>
                                    <span className="text-sm">
                                        Page {currentPage} of {totalPages}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                        disabled={currentPage === totalPages}
                                    >
                                        <ChevronRight className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}
