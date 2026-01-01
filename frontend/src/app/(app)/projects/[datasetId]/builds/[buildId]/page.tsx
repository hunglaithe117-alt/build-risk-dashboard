"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
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
import {
    ArrowLeft,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    ExternalLink,
    GitBranch,
    GitCommit,
    Loader2,
    AlertCircle,
    XCircle,
    AlertTriangle,
    Clock,
    User,
    Bot,
    FileCode,
} from "lucide-react";
import {
    datasetVersionApi,
    type EnrichmentBuildDetailResponse,
    type NodeExecutionDetail,
} from "@/lib/api";

/** CI Provider labels mapping */
const CI_PROVIDER_LABELS: Record<string, string> = {
    github_actions: "GitHub Actions",
    circleci: "CircleCI",
    travis_ci: "Travis CI",
};

const getCIProviderLabel = (provider: string): string => {
    return CI_PROVIDER_LABELS[provider] || provider;
};

/** Format duration */
const formatDuration = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    if (mins < 60) return `${mins}m ${secs}s`;
    const hours = Math.floor(mins / 60);
    const remainMins = mins % 60;
    return `${hours}h ${remainMins}m`;
};

/** Format relative time */
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

/** Get status config */
const getStatusConfig = (status: string) => {
    const config: Record<string, { icon: typeof CheckCircle2; color: string; bgColor: string }> = {
        success: { icon: CheckCircle2, color: "text-green-600", bgColor: "bg-green-100" },
        completed: { icon: CheckCircle2, color: "text-green-600", bgColor: "bg-green-100" },
        failure: { icon: XCircle, color: "text-red-600", bgColor: "bg-red-100" },
        failed: { icon: XCircle, color: "text-red-600", bgColor: "bg-red-100" },
        partial: { icon: AlertTriangle, color: "text-amber-600", bgColor: "bg-amber-100" },
        skipped: { icon: AlertCircle, color: "text-gray-600", bgColor: "bg-gray-100" },
        pending: { icon: Loader2, color: "text-blue-600", bgColor: "bg-blue-100" },
    };
    return config[status] || { icon: AlertCircle, color: "text-gray-600", bgColor: "bg-gray-100" };
};

export default function BuildDetailPage() {
    const params = useParams<{ datasetId: string; buildId: string }>();
    const searchParams = useSearchParams();
    const { datasetId, buildId } = params;
    const versionId = searchParams.get("versionId") || "";
    const router = useRouter();

    const [data, setData] = useState<EnrichmentBuildDetailResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

    const fetchBuildDetail = useCallback(async () => {
        if (!buildId) return;
        setIsLoading(true);
        setError(null);
        try {
            const response = await datasetVersionApi.getBuildDetail(datasetId, versionId, buildId);
            setData(response);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load build details");
        } finally {
            setIsLoading(false);
        }
    }, [datasetId, versionId, buildId]);

    useEffect(() => {
        fetchBuildDetail();
    }, [fetchBuildDetail]);

    const toggleNode = (nodeName: string) => {
        setExpandedNodes((prev) => {
            const next = new Set(prev);
            if (next.has(nodeName)) {
                next.delete(nodeName);
            } else {
                next.add(nodeName);
            }
            return next;
        });
    };

    if (isLoading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !data) {
        return (
            <div className="space-y-4 p-6">
                <Button variant="ghost" size="sm" onClick={() => router.back()}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back
                </Button>
                <Card className="border-destructive">
                    <CardContent className="pt-6">
                        <p className="text-destructive">{error || "Build not found"}</p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const { raw_build_run: rawBuild, enrichment_build: enrichment, audit_log: auditLog } = data;
    const buildStatus = getStatusConfig(rawBuild.conclusion);
    const extractionStatus = getStatusConfig(enrichment.extraction_status);
    const BuildStatusIcon = buildStatus.icon;
    const ExtractionStatusIcon = extractionStatus.icon;

    return (
        <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link href={`/projects/${datasetId}/versions/${versionId}/builds/processing`}>
                        <Button variant="ghost" size="sm">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back to Feature Extraction
                        </Button>
                    </Link>
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-2">
                            Build #{rawBuild.ci_run_id.slice(-8)}
                            {rawBuild.web_url && (
                                <a
                                    href={rawBuild.web_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-muted-foreground hover:text-foreground"
                                >
                                    <ExternalLink className="h-5 w-5" />
                                </a>
                            )}
                        </h1>
                        <p className="text-sm text-muted-foreground flex items-center gap-2">
                            {rawBuild.repo_name}
                            <span>•</span>
                            {getCIProviderLabel(rawBuild.provider)}
                        </p>
                    </div>
                </div>
            </div>

            {/* Enrichment Status */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                        Enrichment Status
                        <Badge className={`${extractionStatus.bgColor} ${extractionStatus.color}`}>
                            <ExtractionStatusIcon className="mr-1 h-3 w-3" />
                            {enrichment.extraction_status}
                        </Badge>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span className="text-muted-foreground">Features Extracted:</span>
                            <p className="font-medium text-lg">
                                {enrichment.feature_count} / {enrichment.expected_feature_count}
                            </p>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Created At:</span>
                            <p className="font-medium">{formatRelativeTime(enrichment.created_at)}</p>
                        </div>
                    </div>

                    {enrichment.missing_resources.length > 0 && (
                        <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 p-3 text-sm">
                            <p className="font-medium text-amber-800 dark:text-amber-200">Missing Resources:</p>
                            <p className="text-amber-700 dark:text-amber-300">
                                {enrichment.missing_resources.join(", ")}
                            </p>
                        </div>
                    )}

                    {enrichment.skipped_features.length > 0 && (
                        <div>
                            <span className="text-sm text-muted-foreground">Skipped Features:</span>
                            <p className="text-sm font-medium">{enrichment.skipped_features.length} features</p>
                        </div>
                    )}

                    {enrichment.extraction_error && (
                        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm">
                            <p className="font-medium text-red-800 dark:text-red-200">Error:</p>
                            <p className="text-red-700 dark:text-red-300">{enrichment.extraction_error}</p>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Two Column Layout: Extracted Features + Extraction Logs */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Extracted Features */}
                <Card className="flex flex-col">
                    <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2">
                            <FileCode className="h-5 w-5" />
                            Extracted Features
                        </CardTitle>
                        <CardDescription>
                            {Object.keys(enrichment.features).length} features extracted
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 overflow-hidden">
                        <div className="rounded-md border h-[500px] overflow-y-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[200px] sticky top-0 bg-background">Feature</TableHead>
                                        <TableHead className="sticky top-0 bg-background">Value</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {Object.entries(enrichment.features)
                                        .sort(([a], [b]) => a.localeCompare(b))
                                        .map(([key, value]) => (
                                            <TableRow key={key}>
                                                <TableCell className="font-medium text-xs">{key}</TableCell>
                                                <TableCell className="font-mono text-sm">
                                                    <ExpandableValue value={formatValue(value)} />
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                </TableBody>
                            </Table>
                        </div>
                    </CardContent>
                </Card>

                {/* Extraction Logs */}
                <Card className="flex flex-col">
                    <CardHeader className="pb-2">
                        <CardTitle>Extraction Logs</CardTitle>
                        {auditLog ? (
                            <CardDescription className="flex items-center gap-2 flex-wrap">
                                <span>Duration: {auditLog.duration_ms ? `${(auditLog.duration_ms / 1000).toFixed(2)}s` : "—"}</span>
                                <span>•</span>
                                <span className="text-green-600">{auditLog.nodes_succeeded} succeeded</span>
                                {auditLog.nodes_failed > 0 && (
                                    <>
                                        <span>•</span>
                                        <span className="text-red-600">{auditLog.nodes_failed} failed</span>
                                    </>
                                )}
                                {auditLog.nodes_skipped > 0 && (
                                    <>
                                        <span>•</span>
                                        <span className="text-gray-600">{auditLog.nodes_skipped} skipped</span>
                                    </>
                                )}
                            </CardDescription>
                        ) : (
                            <CardDescription>No extraction logs available</CardDescription>
                        )}
                    </CardHeader>
                    <CardContent className="flex-1 overflow-hidden">
                        {auditLog ? (
                            <div className="h-[500px] overflow-y-auto space-y-2">
                                {auditLog.errors.length > 0 && (
                                    <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3">
                                        <p className="font-medium text-red-800 dark:text-red-200 mb-1 text-sm">Errors:</p>
                                        <ul className="list-disc list-inside text-xs text-red-700 dark:text-red-300">
                                            {auditLog.errors.map((err, i) => (
                                                <li key={i}>{err}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {auditLog.warnings.length > 0 && (
                                    <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 p-3">
                                        <p className="font-medium text-amber-800 dark:text-amber-200 mb-1 text-sm">Warnings:</p>
                                        <ul className="list-disc list-inside text-xs text-amber-700 dark:text-amber-300">
                                            {auditLog.warnings.map((warn, i) => (
                                                <li key={i}>{warn}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                <div className="space-y-1">
                                    {auditLog.node_results.map((node) => (
                                        <NodeResultRow
                                            key={node.node_name}
                                            node={node}
                                            isExpanded={expandedNodes.has(node.node_name)}
                                            onToggle={() => toggleNode(node.node_name)}
                                        />
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div className="h-[500px] flex items-center justify-center text-muted-foreground">
                                No extraction logs available for this build
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

// =============================================================================
// Sub-components
// =============================================================================

interface NodeResultRowProps {
    node: NodeExecutionDetail;
    isExpanded: boolean;
    onToggle: () => void;
}

function NodeResultRow({ node, isExpanded, onToggle }: NodeResultRowProps) {
    const statusConfig = getStatusConfig(node.status);
    const StatusIcon = statusConfig.icon;

    return (
        <Collapsible open={isExpanded} onOpenChange={onToggle}>
            <CollapsibleTrigger className="w-full">
                <div className="flex items-center justify-between p-3 rounded-md border hover:bg-muted/50 cursor-pointer">
                    <div className="flex items-center gap-3">
                        {isExpanded ? (
                            <ChevronUp className="h-4 w-4" />
                        ) : (
                            <ChevronDown className="h-4 w-4" />
                        )}
                        <StatusIcon className={`h-4 w-4 ${statusConfig.color}`} />
                        <span className="font-medium">{node.node_name}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        {node.features_extracted.length > 0 && (
                            <span>{node.features_extracted.length} features</span>
                        )}
                        {node.duration_ms > 0 && (
                            <span>{node.duration_ms.toFixed(0)}ms</span>
                        )}
                        {node.skip_reason && (
                            <Badge variant="secondary" className="text-xs">{node.skip_reason}</Badge>
                        )}
                    </div>
                </div>
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="ml-8 mt-2 p-3 bg-muted/30 rounded-md text-sm space-y-2">
                    {node.features_extracted.length > 0 && (
                        <div>
                            <span className="text-muted-foreground">Features: </span>
                            <span className="font-mono text-xs">
                                {node.features_extracted.join(", ")}
                            </span>
                        </div>
                    )}
                    {node.resources_used.length > 0 && (
                        <div>
                            <span className="text-muted-foreground">Resources: </span>
                            <span>{node.resources_used.join(", ")}</span>
                        </div>
                    )}
                    {node.error && (
                        <div className="text-red-600">
                            <span className="font-medium">Error: </span>
                            {node.error}
                        </div>
                    )}
                    {node.warning && (
                        <div className="text-amber-600">
                            <span className="font-medium">Warning: </span>
                            {node.warning}
                        </div>
                    )}
                    {node.retry_count > 0 && (
                        <div className="text-muted-foreground">
                            Retries: {node.retry_count}
                        </div>
                    )}
                </div>
            </CollapsibleContent>
        </Collapsible>
    );
}

function formatValue(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "boolean") return value ? "✓" : "✗";
    if (typeof value === "number") {
        if (Number.isInteger(value)) return value.toLocaleString();
        return value.toFixed(2);
    }
    if (typeof value === "string") return value;
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

function ExpandableValue({ value }: { value: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const MAX_LENGTH = 50;

    const isLong = value.length > MAX_LENGTH;

    if (!isLong) {
        return <span>{value}</span>;
    }

    return (
        <div>
            <span className={isExpanded ? "break-all" : "line-clamp-1"}>
                {value}
            </span>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-xs text-blue-600 hover:underline ml-1"
            >
                {isExpanded ? "Show less" : "Show more"}
            </button>
        </div>
    );
}
