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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    FileText,
    Layers,
    Loader2,
    RefreshCw,
    X,
    XCircle,
    AlertTriangle,
    SkipForward,
    Server,
} from "lucide-react";
import {
    enrichmentLogsApi,
    type FeatureAuditLogDto,
    type NodeExecutionResult,
} from "@/lib/api";

interface EnrichmentLogsModalProps {
    datasetId: string;
    versionId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

// Status helpers
function getStatusIcon(status: string) {
    switch (status) {
        case "completed":
        case "success":
            return <CheckCircle2 className="h-4 w-4 text-green-500" />;
        case "failed":
            return <XCircle className="h-4 w-4 text-red-500" />;
        case "running":
            return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
        case "skipped":
            return <SkipForward className="h-4 w-4 text-gray-400" />;
        case "pending":
            return <Clock className="h-4 w-4 text-gray-400" />;
        default:
            return <AlertCircle className="h-4 w-4 text-gray-400" />;
    }
}

function getStatusColor(status: string): string {
    switch (status) {
        case "completed":
        case "success":
            return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
        case "failed":
            return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400";
        case "running":
            return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400";
        case "partial":
            return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400";
        default:
            return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400";
    }
}

function formatDuration(seconds: number | null | undefined): string {
    if (!seconds) return "-";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.round((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

function formatDurationMs(ms: number | null | undefined): string {
    if (!ms) return "-";
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
}

export function EnrichmentLogsModal({
    datasetId,
    versionId,
    open,
    onOpenChange,
}: EnrichmentLogsModalProps) {
    const [auditLogs, setAuditLogs] = useState<FeatureAuditLogDto[]>([]);
    const [selectedLog, setSelectedLog] = useState<FeatureAuditLogDto | null>(null);
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchData = useCallback(async () => {
        if (!versionId) return;

        setIsLoading(true);
        setError(null);

        try {
            // Fetch audit logs only (pipeline run was removed)
            const logsData = await enrichmentLogsApi.getAuditLogs(datasetId, versionId, {
                limit: 100,
                status: statusFilter !== "all" ? statusFilter : undefined,
            });
            setAuditLogs(logsData.items);

            // Auto-select first log if none selected
            if (logsData.items.length > 0 && !selectedLog) {
                setSelectedLog(logsData.items[0]);
            }
        } catch (err) {
            console.error("Failed to fetch enrichment logs:", err);
            setError("Failed to load enrichment logs");
        } finally {
            setIsLoading(false);
        }
    }, [datasetId, versionId, statusFilter, selectedLog]);

    useEffect(() => {
        if (open && versionId) {
            fetchData();
        }
    }, [open, versionId, fetchData]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[95vw] max-h-[90vh] overflow-hidden flex flex-col">
                <DialogHeader className="flex flex-row items-center justify-between">
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5" />
                        Enrichment Logs
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

                {isLoading && auditLogs.length === 0 ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center py-12 gap-4">
                        <AlertCircle className="h-12 w-12 text-destructive" />
                        <p className="text-muted-foreground">{error}</p>
                        <Button variant="outline" onClick={fetchData}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Retry
                        </Button>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col gap-4 overflow-hidden">

                        {/* Filters */}
                        <div className="flex items-center gap-4">
                            <Select value={statusFilter} onValueChange={setStatusFilter}>
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue placeholder="Filter by status" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Status</SelectItem>
                                    <SelectItem value="completed">Completed</SelectItem>
                                    <SelectItem value="failed">Failed</SelectItem>
                                    <SelectItem value="running">Running</SelectItem>
                                </SelectContent>
                            </Select>
                            <Button variant="outline" size="sm" onClick={fetchData} disabled={isLoading}>
                                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`} />
                                Refresh
                            </Button>
                            <span className="text-sm text-muted-foreground">
                                {auditLogs.length} logs
                            </span>
                        </div>

                        {/* Split View: Log List | Log Detail */}
                        <div className="flex-1 grid grid-cols-[300px_1fr] gap-4 overflow-hidden">
                            {/* Log List */}
                            <ScrollArea className="border rounded-lg">
                                <div className="p-2 space-y-1">
                                    {auditLogs.map((log) => (
                                        <button
                                            key={log.id}
                                            onClick={() => setSelectedLog(log)}
                                            className={`w-full text-left p-2 rounded-md transition-colors ${selectedLog?.id === log.id
                                                ? "bg-primary/10 border border-primary/30"
                                                : "hover:bg-muted"
                                                }`}
                                        >
                                            <div className="flex items-center gap-2">
                                                {getStatusIcon(log.status)}
                                                <span className="text-xs font-mono truncate">
                                                    {log.enrichment_build_id?.slice(-8) || log.id.slice(-8)}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                                                <span>{log.feature_count} features</span>
                                                <span>•</span>
                                                <span>{formatDurationMs(log.duration_ms)}</span>
                                            </div>
                                        </button>
                                    ))}
                                    {auditLogs.length === 0 && (
                                        <p className="text-center text-sm text-muted-foreground py-4">
                                            No logs found
                                        </p>
                                    )}
                                </div>
                            </ScrollArea>

                            {/* Log Detail */}
                            <ScrollArea className="border rounded-lg">
                                {selectedLog ? (
                                    <AuditLogDetail log={selectedLog} />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground">
                                        Select a log to view details
                                    </div>
                                )}
                            </ScrollArea>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

// =============================================================================
// Sub-components
// =============================================================================

interface AuditLogDetailProps {
    log: FeatureAuditLogDto;
}

function AuditLogDetail({ log }: AuditLogDetailProps) {
    return (
        <div className="p-4 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {getStatusIcon(log.status)}
                    <span className="font-medium">Build {log.enrichment_build_id?.slice(-8) || log.id.slice(-8)}</span>
                </div>
                <Badge className={getStatusColor(log.status)}>{log.status}</Badge>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-4 gap-4 p-3 bg-muted/50 rounded-lg">
                <div className="text-center">
                    <p className="text-2xl font-bold text-green-600">{log.nodes_succeeded}</p>
                    <p className="text-xs text-muted-foreground">Succeeded</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-red-600">{log.nodes_failed}</p>
                    <p className="text-xs text-muted-foreground">Failed</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold text-gray-500">{log.nodes_skipped}</p>
                    <p className="text-xs text-muted-foreground">Skipped</p>
                </div>
                <div className="text-center">
                    <p className="text-2xl font-bold">{log.feature_count}</p>
                    <p className="text-xs text-muted-foreground">Features</p>
                </div>
            </div>

            {/* Errors & Warnings */}
            {log.errors.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-sm font-medium flex items-center gap-2 text-red-600">
                        <XCircle className="h-4 w-4" />
                        Errors ({log.errors.length})
                    </h4>
                    <div className="space-y-1">
                        {log.errors.map((error, index) => (
                            <div key={index} className="p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-700 dark:text-red-300 font-mono">
                                {error}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {log.warnings.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-sm font-medium flex items-center gap-2 text-yellow-600">
                        <AlertTriangle className="h-4 w-4" />
                        Warnings ({log.warnings.length})
                    </h4>
                    <div className="space-y-1">
                        {log.warnings.map((warning, index) => (
                            <div key={index} className="p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-yellow-700 dark:text-yellow-300 font-mono">
                                {warning}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Node Results */}
            <div className="space-y-2">
                <h4 className="text-sm font-medium flex items-center gap-2">
                    <Layers className="h-4 w-4" />
                    Node Execution ({log.node_results.length})
                </h4>
                <Accordion type="multiple" className="space-y-1">
                    {log.node_results.map((node, index) => (
                        <AccordionItem key={index} value={`node-${index}`} className="border rounded-lg">
                            <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                                <div className="flex items-center gap-2 w-full">
                                    {getStatusIcon(node.status)}
                                    <span className="font-mono text-xs">{node.node_name}</span>
                                    <span className="ml-auto text-xs text-muted-foreground">
                                        {formatDurationMs(node.duration_ms)}
                                    </span>
                                </div>
                            </AccordionTrigger>
                            <AccordionContent className="px-3 pb-3">
                                <NodeResultDetail node={node} />
                            </AccordionContent>
                        </AccordionItem>
                    ))}
                </Accordion>
            </div>
        </div>
    );
}

interface NodeResultDetailProps {
    node: NodeExecutionResult;
}

function NodeResultDetail({ node }: NodeResultDetailProps) {
    return (
        <div className="space-y-3 text-xs">
            {/* Features Extracted */}
            {node.features_extracted.length > 0 && (
                <div>
                    <p className="text-muted-foreground mb-1">Features Extracted:</p>
                    <div className="flex flex-wrap gap-1">
                        {node.features_extracted.map((feature) => (
                            <Badge key={feature} variant="secondary" className="text-xs">
                                {feature}
                            </Badge>
                        ))}
                    </div>
                </div>
            )}

            {/* Resources */}
            {(node.resources_used.length > 0 || node.resources_missing.length > 0) && (
                <div className="grid grid-cols-2 gap-2">
                    {node.resources_used.length > 0 && (
                        <div>
                            <p className="text-muted-foreground mb-1">Resources Used:</p>
                            <div className="flex flex-wrap gap-1">
                                {node.resources_used.map((resource) => (
                                    <Badge key={resource} variant="outline" className="text-xs text-green-600">
                                        {resource}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}
                    {node.resources_missing.length > 0 && (
                        <div>
                            <p className="text-muted-foreground mb-1">Resources Missing:</p>
                            <div className="flex flex-wrap gap-1">
                                {node.resources_missing.map((resource) => (
                                    <Badge key={resource} variant="outline" className="text-xs text-red-600">
                                        {resource}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Error/Warning/Skip Reason */}
            {node.error && (
                <div className="p-2 bg-red-50 dark:bg-red-900/20 rounded">
                    <p className="font-medium text-red-600">Error:</p>
                    <p className="font-mono text-red-700 dark:text-red-300">{node.error}</p>
                </div>
            )}
            {node.warning && (
                <div className="p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded">
                    <p className="font-medium text-yellow-600">Warning:</p>
                    <p className="font-mono text-yellow-700 dark:text-yellow-300">{node.warning}</p>
                </div>
            )}
            {node.skip_reason && (
                <div className="p-2 bg-gray-100 dark:bg-gray-800 rounded">
                    <p className="font-medium text-gray-600">Skip Reason:</p>
                    <p className="font-mono">{node.skip_reason}</p>
                </div>
            )}

            {/* Feature Values (if any) */}
            {Object.keys(node.feature_values).length > 0 && (
                <div>
                    <p className="text-muted-foreground mb-1">Feature Values:</p>
                    <pre className="p-2 bg-muted rounded overflow-x-auto text-xs">
                        {JSON.stringify(node.feature_values, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
}
