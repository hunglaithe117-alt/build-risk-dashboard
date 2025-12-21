"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    ArrowLeft,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock,
    Download,
    Loader2,
    AlertCircle,
    XCircle,
} from "lucide-react";
import { datasetVersionApi } from "@/lib/api";

interface PageParams {
    datasetId: string;
    versionId: string;
}

interface VersionData {
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

interface EnrichedBuild {
    id: string;
    features: Record<string, unknown>;
    extraction_status: string;
    feature_count: number;
}

interface VersionDataResponse {
    version: VersionData;
    data: {
        rows: Record<string, unknown>[];
        total: number;
        page: number;
        page_size: number;
        total_pages: number;
    };
}

const ITEMS_PER_PAGE = 20;

export default function VersionDetailPage(props: { params: Promise<PageParams> }) {
    const params = use(props.params);
    const { datasetId, versionId } = params;
    const router = useRouter();

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [versionData, setVersionData] = useState<VersionDataResponse | null>(null);
    const [currentPage, setCurrentPage] = useState(1);

    // Fetch version data
    useEffect(() => {
        async function fetchVersionData() {
            setLoading(true);
            setError(null);
            try {
                const response = await datasetVersionApi.getVersionData(
                    datasetId,
                    versionId,
                    currentPage,
                    ITEMS_PER_PAGE
                );
                setVersionData(response);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load version data");
            } finally {
                setLoading(false);
            }
        }
        fetchVersionData();
    }, [datasetId, versionId, currentPage]);

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
        const config: Record<string, { icon: typeof CheckCircle2; color: string; bgColor: string }> = {
            completed: { icon: CheckCircle2, color: "text-green-600", bgColor: "bg-green-100" },
            failed: { icon: XCircle, color: "text-red-600", bgColor: "bg-red-100" },
            cancelled: { icon: AlertCircle, color: "text-slate-600", bgColor: "bg-slate-100" },
        };
        return config[status] || config.failed;
    };

    if (loading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !versionData) {
        return (
            <div className="space-y-4 p-6">
                <Button variant="ghost" size="sm" onClick={() => router.back()}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back
                </Button>
                <Card className="border-destructive">
                    <CardContent className="pt-6">
                        <p className="text-destructive">{error || "Version not found"}</p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const { version, data } = versionData;
    const statusConfig = getStatusConfig(version.status);
    const StatusIcon = statusConfig.icon;

    return (
        <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link href={`/projects/${datasetId}`}>
                        <Button variant="ghost" size="sm">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                    </Link>
                    <div>
                        <h1 className="text-2xl font-bold">{version.name}</h1>
                        <p className="text-sm text-muted-foreground">
                            Version {version.version_number}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <Badge className={`${statusConfig.bgColor} ${statusConfig.color}`}>
                        <StatusIcon className="mr-1 h-3 w-3" />
                        {version.status.charAt(0).toUpperCase() + version.status.slice(1)}
                    </Badge>
                    {version.status === "completed" && (
                        <Button variant="outline" size="sm">
                            <Download className="mr-2 h-4 w-4" />
                            Export
                        </Button>
                    )}
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-4 gap-4">
                <Card>
                    <CardContent className="pt-4">
                        <p className="text-sm text-muted-foreground">Total Rows</p>
                        <p className="text-2xl font-bold">{version.total_rows.toLocaleString()}</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <p className="text-sm text-muted-foreground">Enriched Rows</p>
                        <p className="text-2xl font-bold text-green-600">
                            {version.enriched_rows.toLocaleString()}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <p className="text-sm text-muted-foreground">Failed Rows</p>
                        <p className="text-2xl font-bold text-red-600">
                            {version.failed_rows.toLocaleString()}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <p className="text-sm text-muted-foreground">Features</p>
                        <p className="text-2xl font-bold">{version.selected_features.length}</p>
                    </CardContent>
                </Card>
            </div>

            {/* Enriched Builds Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Enriched Builds</CardTitle>
                    <CardDescription>
                        Showing {data.rows.length} of {data.total} builds
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {data.rows.length === 0 ? (
                        <div className="py-8 text-center text-muted-foreground">
                            No enriched builds found
                        </div>
                    ) : (
                        <>
                            <div className="rounded-md border overflow-x-auto">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            {version.selected_features.slice(0, 8).map((feature) => (
                                                <TableHead key={feature} className="min-w-[100px]">
                                                    {feature}
                                                </TableHead>
                                            ))}
                                            {version.selected_features.length > 8 && (
                                                <TableHead>+{version.selected_features.length - 8} more</TableHead>
                                            )}
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {data.rows.map((row, idx) => (
                                            <TableRow key={idx}>
                                                {version.selected_features.slice(0, 8).map((feature) => (
                                                    <TableCell key={feature} className="font-mono text-sm">
                                                        {formatCellValue(row[feature])}
                                                    </TableCell>
                                                ))}
                                                {version.selected_features.length > 8 && (
                                                    <TableCell className="text-muted-foreground">...</TableCell>
                                                )}
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>

                            {/* Pagination */}
                            {data.total_pages > 1 && (
                                <div className="mt-4 flex items-center justify-between">
                                    <p className="text-sm text-muted-foreground">
                                        Page {data.page} of {data.total_pages}
                                    </p>
                                    <div className="flex items-center gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                                            disabled={currentPage === 1}
                                        >
                                            <ChevronLeft className="h-4 w-4" />
                                            Previous
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setCurrentPage((p) => Math.min(data.total_pages, p + 1))}
                                            disabled={currentPage === data.total_pages}
                                        >
                                            Next
                                            <ChevronRight className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

function formatCellValue(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "boolean") return value ? "✓" : "✗";
    if (typeof value === "number") {
        if (Number.isInteger(value)) return value.toLocaleString();
        return value.toFixed(2);
    }
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}
