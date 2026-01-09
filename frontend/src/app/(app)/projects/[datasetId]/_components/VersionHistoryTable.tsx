"use client";

import { useState, useCallback, useMemo } from "react";
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
} from "lucide-react";
import { SearchFilterBar } from "@/components/builds";
import { formatDateTime } from "@/lib/utils";
import type { DatasetVersion } from "../_hooks/useDatasetVersions";

// Version status options for filter dropdown
const VERSION_STATUS_OPTIONS = [
    { value: "all", label: "All Statuses" },
    { value: "queued", label: "Queued" },
    { value: "ingesting", label: "Ingesting" },
    { value: "ingested", label: "Ingested" },
    { value: "processing", label: "Processing" },
    { value: "processed", label: "Processed" },
    { value: "failed", label: "Failed" },
];

type ExportFormat = "csv" | "json";

interface VersionHistoryTableProps {
    datasetId: string;
    versions: DatasetVersion[];
    loading: boolean;
    onRefresh: () => void;
    onDelete: (versionId: string) => void;
}

const ITEMS_PER_PAGE = 10;

export function VersionHistoryTable({
    datasetId,
    versions,
    loading,
    onRefresh,
    onDelete,
}: VersionHistoryTableProps) {
    const router = useRouter();
    const [currentPage, setCurrentPage] = useState(1);
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");

    // Search and filter handlers
    const handleSearch = useCallback((query: string) => {
        setSearchQuery(query);
        setCurrentPage(1);
    }, []);

    const handleStatusFilter = useCallback((status: string) => {
        setStatusFilter(status);
        setCurrentPage(1);
    }, []);

    // Filter versions based on search and status
    const displayVersions = useMemo(() => {
        let filtered = versions;

        // Filter by status
        if (statusFilter !== "all") {
            filtered = filtered.filter(v => v.status === statusFilter);
        }

        // Filter by search query (name)
        if (searchQuery) {
            const query = searchQuery.toLowerCase();
            filtered = filtered.filter(v =>
                v.name.toLowerCase().includes(query)
            );
        }

        return filtered;
    }, [versions, searchQuery, statusFilter]);

    // Pagination
    const totalPages = Math.ceil(displayVersions.length / ITEMS_PER_PAGE);
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const paginatedVersions = displayVersions.slice(startIndex, startIndex + ITEMS_PER_PAGE);

    // Navigate to version detail
    const handleViewVersion = (versionId: string) => {
        router.push(`/projects/${datasetId}/versions/${versionId}`);
    };

    // Status config
    const getStatusConfig = (status: string) => {
        const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
            queued: { icon: Clock, color: "text-gray-500", label: "Queued" },
            ingesting: { icon: Loader2, color: "text-blue-500", label: "Ingesting" },
            ingested: { icon: CheckCircle2, color: "text-emerald-500", label: "Ingested" },
            processing: { icon: Loader2, color: "text-purple-500", label: "Processing" },
            processed: { icon: CheckCircle2, color: "text-green-500", label: "Processed" },
            failed: { icon: XCircle, color: "text-red-500", label: "Failed" },
        };
        return config[status] || { icon: Clock, color: "text-gray-400", label: status };
    };

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            Version History
                        </CardTitle>
                        <CardDescription>
                            {displayVersions.length} version(s) created
                        </CardDescription>
                    </div>
                    <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
                        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    </Button>
                </div>
            </CardHeader>

            {/* Search and Filter */}
            <div className="px-6 pb-4">
                <SearchFilterBar
                    placeholder="Search by version name..."
                    statusOptions={VERSION_STATUS_OPTIONS}
                    onSearch={handleSearch}
                    onStatusFilter={handleStatusFilter}
                    isLoading={loading}
                />
            </div>

            <CardContent>
                {loading && versions.length === 0 ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Loading versions...
                    </div>
                ) : displayVersions.length === 0 ? (
                    <div className="py-8 text-center text-muted-foreground">
                        No versions created yet. Click &quot;Create New Version&quot; to get started.
                    </div>
                ) : (
                    <>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[30%]">Name</TableHead>
                                    <TableHead className="w-[20%]">Status</TableHead>
                                    <TableHead className="w-[15%] text-center">Features</TableHead>
                                    <TableHead className="w-[15%] text-center">Scans</TableHead>
                                    <TableHead className="w-[15%] text-right">Created</TableHead>
                                    <TableHead className="w-[5%] text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {paginatedVersions.map((version) => {
                                    const statusConfig = getStatusConfig(version.status);
                                    const StatusIcon = statusConfig.icon;

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
                                                    <StatusIcon className={`h-4 w-4 ${statusConfig.color} ${["ingesting", "processing"].includes(version.status) ? "animate-spin" : ""}`} />
                                                    <span className="text-sm">{statusConfig.label}</span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-center">
                                                <Badge variant="outline">
                                                    {version.selected_features.length}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-center">
                                                {(() => {
                                                    const sonarCount = version.scan_metrics?.sonarqube?.length || 0;
                                                    const trivyCount = version.scan_metrics?.trivy?.length || 0;
                                                    const total = sonarCount + trivyCount;
                                                    if (total === 0) return <span className="text-muted-foreground">—</span>;
                                                    return (
                                                        <Badge variant="secondary" title={`SonarQube: ${sonarCount}, Trivy: ${trivyCount}`}>
                                                            {total}
                                                        </Badge>
                                                    );
                                                })()}
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <div className="flex items-center justify-end gap-1 text-muted-foreground">
                                                    <Clock className="h-3 w-3" />
                                                    <span className="text-sm">
                                                        {formatDateTime(version.created_at)}
                                                    </span>
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <div
                                                    className="flex items-center justify-end gap-1"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
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
                        <div className="mt-4 flex items-center justify-between border-t pt-4">
                            <p className="text-sm text-muted-foreground">
                                Showing {paginatedVersions.length} of {displayVersions.length} versions
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
                                    Page {currentPage} of {Math.max(1, totalPages)}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                    disabled={currentPage >= totalPages || totalPages <= 1}
                                >
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </>
                )
                }
            </CardContent >
        </Card >
    );
}
