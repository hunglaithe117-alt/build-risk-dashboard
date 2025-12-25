"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
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
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import {
    ArrowLeft,
    CheckCircle2,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    ChevronUp,
    Download,
    Loader2,
    AlertCircle,
    XCircle,
    AlertTriangle,
    ExternalLink,
} from "lucide-react";
import { datasetVersionApi, type EnrichedBuildData } from "@/lib/api";
import { ExportVersionModal } from "@/components/datasets/ExportVersionModal";

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

interface VersionDataResponse {
    version: VersionData;
    builds: EnrichedBuildData[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

const ITEMS_PER_PAGE = 20;

export default function VersionDetailPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const datasetId = params.datasetId;
    const versionId = params.versionId;
    const router = useRouter();

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [versionData, setVersionData] = useState<VersionDataResponse | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [expandedBuildId, setExpandedBuildId] = useState<string | null>(null);
    const [isExportModalOpen, setIsExportModalOpen] = useState(false);

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
                    ITEMS_PER_PAGE,
                    true
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
    const getVersionStatusConfig = (status: string) => {
        const config: Record<string, { icon: typeof CheckCircle2; color: string; bgColor: string }> = {
            completed: { icon: CheckCircle2, color: "text-green-600", bgColor: "bg-green-100" },
            failed: { icon: XCircle, color: "text-red-600", bgColor: "bg-red-100" },
            cancelled: { icon: AlertCircle, color: "text-slate-600", bgColor: "bg-slate-100" },
        };
        return config[status] || config.failed;
    };

    const getBuildStatusConfig = (status: string) => {
        const config: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
            completed: { icon: CheckCircle2, color: "text-green-600", label: "Complete" },
            partial: { icon: AlertTriangle, color: "text-amber-500", label: "Partial" },
            failed: { icon: XCircle, color: "text-red-500", label: "Failed" },
            pending: { icon: Loader2, color: "text-blue-500", label: "Pending" },
        };
        return config[status] || config.pending;
    };

    // Toggle build expansion
    const toggleBuildExpansion = (buildId: string) => {
        setExpandedBuildId(expandedBuildId === buildId ? null : buildId);
    };

    // Render Build Row Logic (reusable)
    const renderBuildRow = (build: EnrichedBuildData) => {
        const buildStatus = getBuildStatusConfig(build.extraction_status);
        const BuildStatusIcon = buildStatus.icon;
        const isExpanded = expandedBuildId === build.id;
        const featurePercent = (build.feature_count / build.expected_feature_count) * 100;

        return (
            <Collapsible
                key={build.id}
                open={isExpanded}
                onOpenChange={() => toggleBuildExpansion(build.id)}
                asChild
            >
                <>
                    <CollapsibleTrigger asChild>
                        <TableRow className="cursor-pointer hover:bg-muted/50">
                            <TableCell>
                                {isExpanded ? (
                                    <ChevronUp className="h-4 w-4" />
                                ) : (
                                    <ChevronDown className="h-4 w-4" />
                                )}
                            </TableCell>
                            <TableCell className="font-mono text-sm">
                                <span className={build.web_url ? "text-blue-600 hover:underline" : ""}>
                                    {build.web_url ? (
                                        <Link href={build.web_url} target="_blank" onClick={(e) => e.stopPropagation()}>
                                            #{build.raw_build_run_id.slice(-8)}
                                        </Link>
                                    ) : (
                                        `#${build.raw_build_run_id.slice(-8)}`
                                    )}
                                </span>
                            </TableCell>
                            <TableCell className="max-w-[200px] truncate">
                                <div className="flex items-center gap-2">
                                    {build.repo_url ? (
                                        <a
                                            href={build.repo_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="hover:underline flex items-center gap-1"
                                            onClick={(e) => e.stopPropagation()}
                                        >
                                            {build.repo_full_name}
                                            <ExternalLink className="h-3 w-3 opacity-50" />
                                        </a>
                                    ) : (
                                        build.repo_full_name
                                    )}
                                </div>
                            </TableCell>
                            <TableCell>
                                <span className="capitalize">{build.provider || "—"}</span>
                            </TableCell>
                            <TableCell>
                                <Badge
                                    variant="outline"
                                    className={buildStatus.color}
                                >
                                    <BuildStatusIcon className="mr-1 h-3 w-3" />
                                    {buildStatus.label}
                                </Badge>
                            </TableCell>
                            <TableCell>
                                <div className="flex items-center gap-2">
                                    <span className="text-sm">
                                        {build.feature_count}/{build.expected_feature_count}
                                    </span>
                                    <Progress
                                        value={featurePercent}
                                        className="h-2 w-16"
                                    />
                                </div>
                            </TableCell>
                            <TableCell>
                                {build.skipped_features.length > 0 ? (
                                    <Badge variant="secondary">
                                        {build.skipped_features.length}
                                    </Badge>
                                ) : (
                                    "—"
                                )}
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                                {formatRelativeTime(build.enriched_at)}
                            </TableCell>
                        </TableRow>
                    </CollapsibleTrigger>
                    <CollapsibleContent asChild>
                        <tr>
                            <td colSpan={7} className="p-0">
                                <div className="border-t bg-muted/30 p-4">
                                    {build.missing_resources.length > 0 && (
                                        <div className="mb-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                                            <strong>Missing Resources:</strong>{" "}
                                            {build.missing_resources.join(", ")}
                                        </div>
                                    )}
                                    <div className="rounded-md border bg-background max-h-[500px] overflow-y-auto">
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead className="w-[300px]">Feature</TableHead>
                                                    <TableHead>Value</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {Object.entries(build.features)
                                                    .sort(([keyA], [keyB]) => keyA.localeCompare(keyB))
                                                    .map(([key, value]) => (
                                                        <TableRow key={key}>
                                                            <TableCell className="font-medium text-xs">
                                                                {key}
                                                            </TableCell>
                                                            <TableCell className="font-mono text-sm break-all">
                                                                {formatValue(value, true)}
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                </div>
                            </td>
                        </tr>
                    </CollapsibleContent>
                </>
            </Collapsible>
        );
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

    const { version, builds, total, total_pages } = versionData;
    const statusConfig = getVersionStatusConfig(version.status);
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
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setIsExportModalOpen(true)}
                        >
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

            {/* Content Area */}
            <Card>
                <CardHeader>
                    <CardTitle>Enriched Builds</CardTitle>
                    <CardDescription>
                        Showing {builds.length} of {total} builds
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {builds.length === 0 ? (
                        <div className="py-8 text-center text-muted-foreground">
                            No enriched builds found
                        </div>
                    ) : (
                        <div className="rounded-md border overflow-hidden">
                            <Table className="table-fixed w-full">
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[40px]"></TableHead>
                                        <TableHead className="w-[100px]">Build ID</TableHead>
                                        <TableHead className="w-[200px]">Repository</TableHead>
                                        <TableHead className="w-[100px]">CI Provider</TableHead>
                                        <TableHead className="w-[100px]">Status</TableHead>
                                        <TableHead className="w-[120px]">Features</TableHead>
                                        <TableHead className="w-[80px]">Skipped</TableHead>
                                        <TableHead className="w-[100px]">Enriched At</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {builds.map((build) => renderBuildRow(build))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Pagination */}
            {total_pages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                    <p className="text-sm text-muted-foreground">
                        Page {currentPage} of {total_pages} (Builds)
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
                            onClick={() => setCurrentPage((p) => Math.min(total_pages, p + 1))}
                            disabled={currentPage === total_pages}
                        >
                            Next
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}

            {/* Export Modal */}
            <ExportVersionModal
                isOpen={isExportModalOpen}
                onClose={() => setIsExportModalOpen(false)}
                datasetId={datasetId}
                versionId={versionId}
                versionName={version.name}
                totalRows={version.total_rows}
            />
        </div>
    );
}

function formatValue(value: unknown, showFull = false): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "boolean") return value ? "✓" : "✗";
    if (typeof value === "number") {
        if (Number.isInteger(value)) return value.toLocaleString();
        return value.toFixed(2);
    }
    if (typeof value === "string") {
        if (!showFull && value.length > 30) return value.slice(0, 27) + "...";
        return value;
    }
    if (typeof value === "object") {
        const str = JSON.stringify(value);
        if (!showFull && str.length > 30) return str.slice(0, 30) + "...";
        return str;
    }
    return String(value);
}
