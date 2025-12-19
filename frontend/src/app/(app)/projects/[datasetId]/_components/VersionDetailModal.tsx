"use client";

import { useEffect, useState, useCallback } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    ChevronLeft,
    ChevronRight,
    Loader2,
    AlertCircle,
    CheckCircle2,
    XCircle,
    X,
    Hash,
    Type,
    ToggleLeft,
    List,
    HelpCircle,
} from "lucide-react";
import { api } from "@/lib/api";

interface VersionMetadata {
    id: string;
    name: string;
    version_number: number;
    status: string;
    total_rows: number;
    enriched_rows: number;
    failed_rows: number;
    selected_features: string[];
    created_at: string | null;
    completed_at: string | null;
}

interface ColumnStats {
    non_null: number;
    missing: number;
    missing_rate: number;
    type: "numeric" | "string" | "boolean" | "array" | "unknown";
    min?: number;
    max?: number;
    avg?: number;
}

interface PaginationData {
    rows: Record<string, unknown>[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

interface VersionDataResponse {
    version: VersionMetadata;
    data: PaginationData;
    column_stats: Record<string, ColumnStats>;
}

interface VersionDetailModalProps {
    datasetId: string;
    versionId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function VersionDetailModal({
    datasetId,
    versionId,
    open,
    onOpenChange,
}: VersionDetailModalProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<VersionDataResponse | null>(null);
    const [page, setPage] = useState(1);
    const [columnStats, setColumnStats] = useState<Record<string, ColumnStats>>({});

    const fetchData = useCallback(
        async (pageNum: number) => {
            if (!versionId) return;

            setLoading(true);
            setError(null);

            try {
                const response = await api.get<VersionDataResponse>(
                    `/datasets/${datasetId}/versions/${versionId}/data`,
                    { params: { page: pageNum, page_size: 20 } }
                );
                setData(response.data);

                // Store column stats from first page
                if (pageNum === 1 && response.data.column_stats) {
                    setColumnStats(response.data.column_stats);
                }
            } catch (err) {
                console.error("Failed to fetch version data:", err);
                setError(err instanceof Error ? err.message : "Failed to load data");
            } finally {
                setLoading(false);
            }
        },
        [datasetId, versionId]
    );

    useEffect(() => {
        if (open && versionId) {
            setPage(1);
            fetchData(1);
        }
    }, [open, versionId, fetchData]);

    const handlePageChange = (newPage: number) => {
        setPage(newPage);
        fetchData(newPage);
    };

    const typeIcons: Record<string, typeof Hash> = {
        numeric: Hash,
        string: Type,
        boolean: ToggleLeft,
        array: List,
        unknown: HelpCircle,
    };

    const getColumns = (): string[] => {
        if (!data) return [];
        return ["build_id", "extraction_status", ...data.version.selected_features];
    };

    const formatValue = (value: unknown): string => {
        if (value === null || value === undefined) return "—";
        if (typeof value === "boolean") return value ? "Yes" : "No";
        if (typeof value === "number") return value.toLocaleString();
        if (Array.isArray(value)) return `[${value.length} items]`;
        if (typeof value === "object") return JSON.stringify(value);
        return String(value);
    };

    const formatDuration = (startStr: string | null, endStr: string | null): string => {
        if (!startStr || !endStr) return "—";
        const start = new Date(startStr);
        const end = new Date(endStr);
        const diffMs = end.getTime() - start.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 60) return `${diffMins}m`;
        const diffHours = Math.floor(diffMins / 60);
        return `${diffHours}h ${diffMins % 60}m`;
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[95vw] max-h-[90vh] overflow-hidden flex flex-col">
                <DialogHeader className="flex flex-row items-center justify-between">
                    <DialogTitle className="flex items-center gap-2">
                        📊 Version Details
                        {data && (
                            <Badge variant="outline">{data.version.name}</Badge>
                        )}
                    </DialogTitle>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => onOpenChange(false)}
                    >
                        <X className="h-4 w-4" />
                        <span className="sr-only">Close</span>
                    </Button>
                </DialogHeader>

                {loading && !data ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="flex items-center justify-center py-12 text-destructive">
                        <AlertCircle className="mr-2 h-5 w-5" />
                        {error}
                    </div>
                ) : data ? (
                    <div className="flex flex-col gap-4 overflow-hidden">
                        {/* Metadata Summary */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-muted/50 rounded-lg">
                            <div>
                                <p className="text-xs text-muted-foreground">Status</p>
                                <Badge
                                    variant={
                                        data.version.status === "completed"
                                            ? "default"
                                            : "destructive"
                                    }
                                >
                                    {data.version.status}
                                </Badge>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Rows</p>
                                <p className="font-medium">
                                    <span className="text-green-600">
                                        {data.version.enriched_rows.toLocaleString()}
                                    </span>
                                    {" / "}
                                    {data.version.total_rows.toLocaleString()}
                                    {data.version.failed_rows > 0 && (
                                        <span className="text-red-500 ml-1">
                                            ({data.version.failed_rows} failed)
                                        </span>
                                    )}
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Features</p>
                                <p className="font-medium">
                                    {data.version.selected_features.length} columns
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Duration</p>
                                <p className="font-medium">
                                    {formatDuration(
                                        data.version.created_at,
                                        data.version.completed_at
                                    )}
                                </p>
                            </div>
                        </div>

                        {/* Data Table */}
                        <div className="flex-1 overflow-auto border rounded-lg">
                            <Table>
                                <TableHeader className="sticky top-0 bg-background z-10">
                                    <TableRow>
                                        {getColumns().map((col) => {
                                            const stats = columnStats[col];
                                            const TypeIcon = stats
                                                ? typeIcons[stats.type] || HelpCircle
                                                : HelpCircle;

                                            return (
                                                <TableHead
                                                    key={col}
                                                    className="min-w-[120px] whitespace-nowrap"
                                                >
                                                    <TooltipProvider>
                                                        <Tooltip>
                                                            <TooltipTrigger asChild>
                                                                <div className="flex flex-col gap-1">
                                                                    <div className="flex items-center gap-1">
                                                                        {stats && (
                                                                            <TypeIcon className="h-3 w-3 text-muted-foreground" />
                                                                        )}
                                                                        <span className="font-medium truncate max-w-[100px]">
                                                                            {col}
                                                                        </span>
                                                                    </div>
                                                                    {stats && (
                                                                        <div className="text-xs font-normal text-muted-foreground">
                                                                            {stats.missing_rate > 0 ? (
                                                                                <span className="text-amber-600">
                                                                                    {stats.missing_rate}% missing
                                                                                </span>
                                                                            ) : (
                                                                                <span className="text-green-600">
                                                                                    100% complete
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </TooltipTrigger>
                                                            <TooltipContent side="bottom" className="max-w-xs">
                                                                <div className="text-xs space-y-1">
                                                                    <p className="font-medium">{col}</p>
                                                                    {stats && (
                                                                        <>
                                                                            <p>Type: {stats.type}</p>
                                                                            <p>
                                                                                Non-null: {stats.non_null} / Missing:{" "}
                                                                                {stats.missing}
                                                                            </p>
                                                                            {stats.type === "numeric" && (
                                                                                <p>
                                                                                    Min: {stats.min} / Max: {stats.max} / Avg:{" "}
                                                                                    {stats.avg}
                                                                                </p>
                                                                            )}
                                                                        </>
                                                                    )}
                                                                </div>
                                                            </TooltipContent>
                                                        </Tooltip>
                                                    </TooltipProvider>
                                                </TableHead>
                                            );
                                        })}
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {data.data.rows.map((row, idx) => (
                                        <TableRow key={idx}>
                                            {getColumns().map((col) => (
                                                <TableCell
                                                    key={col}
                                                    className="max-w-[200px] truncate"
                                                >
                                                    {col === "extraction_status" ? (
                                                        row[col] === "completed" ? (
                                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                                        ) : (
                                                            <XCircle className="h-4 w-4 text-red-500" />
                                                        )
                                                    ) : (
                                                        formatValue(row[col])
                                                    )}
                                                </TableCell>
                                            ))}
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>

                        {/* Pagination */}
                        <div className="flex items-center justify-between px-2">
                            <p className="text-sm text-muted-foreground">
                                Showing {(page - 1) * data.data.page_size + 1} -{" "}
                                {Math.min(page * data.data.page_size, data.data.total)} of{" "}
                                {data.data.total.toLocaleString()} rows
                            </p>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handlePageChange(page - 1)}
                                    disabled={page <= 1 || loading}
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                    Previous
                                </Button>
                                <span className="text-sm">
                                    Page {page} of {data.data.total_pages}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handlePageChange(page + 1)}
                                    disabled={page >= data.data.total_pages || loading}
                                >
                                    Next
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}
