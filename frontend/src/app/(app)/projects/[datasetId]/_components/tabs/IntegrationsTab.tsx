"use client";

import React, { useCallback, useEffect, useState, useRef } from "react";
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
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { api, settingsApi } from "@/lib/api";
import type { ApplicationSettings } from "@/types";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Clock,
    ExternalLink,
    Loader2,
    RefreshCw,
    RotateCcw,
    Shield,
    Settings,
    XCircle,
    Timer,
    AlertTriangle,
} from "lucide-react";

// Types
interface IntegrationsTabProps {
    datasetId: string;
}

interface DatasetVersion {
    id: string;
    version_number: number;
    name: string;
    status: string;
    scan_metrics: {
        sonarqube?: string[];
        trivy?: string[];
    };
}

interface CommitScan {
    id: string;
    commit_sha: string;
    repo_full_name: string;
    status: string;
    error_message: string | null;
    builds_affected: number;
    retry_count: number;
    started_at: string | null;
    completed_at: string | null;
    component_key?: string;
}

interface CommitScansResponse {
    trivy: CommitScan[];
    sonarqube: CommitScan[];
}

// Helpers
/** Format duration from start/end timestamps */
function formatDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt) return "—";
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    const durationMs = end - start;

    if (durationMs < 1000) return `${durationMs}ms`;
    if (durationMs < 60000) return `${(durationMs / 1000).toFixed(1)}s`;
    return `${(durationMs / 60000).toFixed(1)}m`;
}

/** Check if any scans are still running */
function hasRunningScans(scans: CommitScansResponse | null): boolean {
    if (!scans) return false;
    const allScans = [...scans.trivy, ...scans.sonarqube];
    return allScans.some(s => s.status === "scanning" || s.status === "pending");
}

/** Count failed scans */
function countFailedScans(scans: CommitScansResponse | null): number {
    if (!scans) return 0;
    const allScans = [...scans.trivy, ...scans.sonarqube];
    return allScans.filter(s => s.status === "failed").length;
}

/** Get scan statistics */
function getScanStats(scans: CommitScansResponse | null): {
    total: number;
    completed: number;
    pending: number;
    failed: number;
    scanning: number;
} {
    if (!scans) return { total: 0, completed: 0, pending: 0, failed: 0, scanning: 0 };
    const allScans = [...scans.trivy, ...scans.sonarqube];
    return {
        total: allScans.length,
        completed: allScans.filter(s => s.status === "completed").length,
        pending: allScans.filter(s => s.status === "pending").length,
        failed: allScans.filter(s => s.status === "failed").length,
        scanning: allScans.filter(s => s.status === "scanning").length,
    };
}

// =============================================================================
// Component
// =============================================================================

export function IntegrationsTab({ datasetId }: IntegrationsTabProps) {
    const [versions, setVersions] = useState<DatasetVersion[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedVersionId, setExpandedVersionId] = useState<string | null>(null);
    const [commitScans, setCommitScans] = useState<CommitScansResponse | null>(null);
    const [loadingScans, setLoadingScans] = useState(false);
    const [retryingCommit, setRetryingCommit] = useState<string | null>(null);
    const [bulkRetrying, setBulkRetrying] = useState(false);
    const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set());
    const [settings, setSettings] = useState<ApplicationSettings | null>(null);

    // Auto-refresh ref
    const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // URL helpers using settings
    const getSonarQubeUrl = useCallback((componentKey: string | undefined): string | null => {
        if (!componentKey) return null;
        const baseUrl = settings?.sonarqube?.host_url || "http://localhost:9000";
        return `${baseUrl}/dashboard?id=${encodeURIComponent(componentKey)}`;
    }, [settings]);

    const getTrivyReportUrl = useCallback((commitSha: string): string | null => {
        // Trivy doesn't have a web dashboard, but we could show the server URL if configured
        // For now, return null - could be extended to show local report files
        return null;
    }, []);

    // Load settings on mount
    useEffect(() => {
        settingsApi.get().then(setSettings).catch(() => setSettings(null));
    }, []);

    // Load versions with scan_metrics
    const loadVersions = useCallback(async () => {
        try {
            setLoading(true);
            const response = await api.get<{ versions: DatasetVersion[] }>(
                `/datasets/${datasetId}/versions`
            );
            // Filter to versions that have scan metrics configured
            const versionsWithScans = response.data.versions.filter(
                (v) =>
                    (v.scan_metrics?.sonarqube?.length || 0) > 0 ||
                    (v.scan_metrics?.trivy?.length || 0) > 0
            );
            setVersions(versionsWithScans);
        } catch {
            setVersions([]);
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    // Load commit scans for a version
    const loadCommitScans = async (versionId: string, silent = false) => {
        if (expandedVersionId === versionId && !silent) {
            setExpandedVersionId(null);
            setCommitScans(null);
            return;
        }

        if (!silent) setLoadingScans(true);
        try {
            const response = await api.get<CommitScansResponse>(
                `/datasets/${datasetId}/versions/${versionId}/commit-scans`
            );
            setCommitScans(response.data);
            setExpandedVersionId(versionId);
        } catch (error) {
            console.error("Failed to load commit scans:", error);
        } finally {
            setLoadingScans(false);
        }
    };

    // Retry a specific commit scan
    const handleRetry = async (versionId: string, commitSha: string, toolType: string) => {
        setRetryingCommit(`${commitSha}-${toolType}`);
        try {
            await api.post(
                `/datasets/${datasetId}/versions/${versionId}/commits/${commitSha}/retry/${toolType}`
            );
            // Reload scans
            await loadCommitScans(versionId, true);
        } catch (error) {
            console.error("Failed to retry scan:", error);
        } finally {
            setRetryingCommit(null);
        }
    };

    // Bulk retry all failed scans
    const handleBulkRetry = async (versionId: string) => {
        if (!commitScans) return;

        setBulkRetrying(true);
        const failedScans: { commitSha: string; tool: string }[] = [];

        commitScans.trivy.filter(s => s.status === "failed").forEach(s => {
            failedScans.push({ commitSha: s.commit_sha, tool: "trivy" });
        });
        commitScans.sonarqube.filter(s => s.status === "failed").forEach(s => {
            failedScans.push({ commitSha: s.commit_sha, tool: "sonarqube" });
        });

        try {
            // Retry all failed scans in parallel
            await Promise.all(
                failedScans.map(({ commitSha, tool }) =>
                    api.post(`/datasets/${datasetId}/versions/${versionId}/commits/${commitSha}/retry/${tool}`)
                )
            );
            await loadCommitScans(versionId, true);
        } catch (error) {
            console.error("Failed to retry scans:", error);
        } finally {
            setBulkRetrying(false);
        }
    };

    // Toggle error expansion
    const toggleError = (scanId: string) => {
        setExpandedErrors(prev => {
            const next = new Set(prev);
            if (next.has(scanId)) {
                next.delete(scanId);
            } else {
                next.add(scanId);
            }
            return next;
        });
    };

    // Auto-refresh when scans are running
    useEffect(() => {
        if (hasRunningScans(commitScans) && expandedVersionId) {
            refreshIntervalRef.current = setInterval(() => {
                loadCommitScans(expandedVersionId, true);
            }, 5000);
        } else if (refreshIntervalRef.current) {
            clearInterval(refreshIntervalRef.current);
            refreshIntervalRef.current = null;
        }

        return () => {
            if (refreshIntervalRef.current) {
                clearInterval(refreshIntervalRef.current);
            }
        };
    }, [commitScans, expandedVersionId]);

    useEffect(() => {
        loadVersions();
    }, [loadVersions]);

    // Render status badge
    const renderStatus = (status: string) => {
        switch (status) {
            case "completed":
                return (
                    <Badge className="bg-green-500">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Completed
                    </Badge>
                );
            case "scanning":
                return (
                    <Badge className="bg-blue-500">
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        Scanning
                    </Badge>
                );
            case "pending":
                return (
                    <Badge variant="secondary">
                        <Clock className="h-3 w-3 mr-1" />
                        Pending
                    </Badge>
                );
            case "failed":
                return (
                    <Badge variant="destructive">
                        <XCircle className="h-3 w-3 mr-1" />
                        Failed
                    </Badge>
                );
            default:
                return <Badge variant="outline">{status}</Badge>;
        }
    };

    // Render scan table row with expandable error
    const renderScanRow = (scan: CommitScan, toolType: string, versionId: string) => {
        const isExpanded = expandedErrors.has(scan.id);
        const hasError = scan.status === "failed" && scan.error_message;

        return (
            <React.Fragment key={scan.id}>
                <tr className={hasError ? "cursor-pointer hover:bg-muted/50" : ""} onClick={() => hasError && toggleError(scan.id)}>
                    <td className="px-3 py-2 font-mono text-xs">
                        {scan.commit_sha.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                        {scan.repo_full_name}
                    </td>
                    <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                            {renderStatus(scan.status)}
                            {scan.retry_count > 0 && (
                                <span className="text-xs text-muted-foreground">
                                    (retry #{scan.retry_count})
                                </span>
                            )}
                            {hasError && (
                                <AlertTriangle className="h-3 w-3 text-amber-500" />
                            )}
                        </div>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                        <div className="flex items-center gap-1">
                            <Timer className="h-3 w-3" />
                            {formatDuration(scan.started_at, scan.completed_at)}
                        </div>
                    </td>
                    <td className="px-3 py-2">{scan.builds_affected}</td>
                    <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                            {/* SonarQube link for completed scans */}
                            {toolType === "sonarqube" && scan.status === "completed" && scan.component_key && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    asChild
                                    title="View in SonarQube"
                                >
                                    <a
                                        href={getSonarQubeUrl(scan.component_key) || "#"}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <ExternalLink className="h-3 w-3" />
                                    </a>
                                </Button>
                            )}
                            {/* Retry button for failed scans */}
                            {scan.status === "failed" && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleRetry(versionId, scan.commit_sha, toolType);
                                    }}
                                    disabled={retryingCommit === `${scan.commit_sha}-${toolType}`}
                                >
                                    {retryingCommit === `${scan.commit_sha}-${toolType}` ? (
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                        <RotateCcw className="h-3 w-3" />
                                    )}
                                    <span className="ml-1">Retry</span>
                                </Button>
                            )}
                        </div>
                    </td>
                </tr>
                {/* Expandable error row */}
                {isExpanded && hasError && (
                    <tr>
                        <td colSpan={6} className="px-3 py-2 bg-red-50 dark:bg-red-950/20">
                            <div className="text-sm font-mono text-red-700 dark:text-red-400 whitespace-pre-wrap break-all">
                                {scan.error_message}
                            </div>
                        </td>
                    </tr>
                )}
            </React.Fragment>
        );
    };

    // Render scan table
    const renderScanTable = (scans: CommitScan[], toolType: string, versionId: string) => {
        if (scans.length === 0) {
            return (
                <p className="text-sm text-muted-foreground py-4 text-center">
                    No {toolType} scans found
                </p>
            );
        }

        return (
            <table className="min-w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800">
                    <tr>
                        <th className="px-3 py-2 text-left font-medium">Commit</th>
                        <th className="px-3 py-2 text-left font-medium">Repository</th>
                        <th className="px-3 py-2 text-left font-medium">Status</th>
                        <th className="px-3 py-2 text-left font-medium">Duration</th>
                        <th className="px-3 py-2 text-left font-medium">Builds</th>
                        <th className="px-3 py-2 text-left font-medium">Actions</th>
                    </tr>
                </thead>
                <tbody className="divide-y">
                    {scans.map((scan) => renderScanRow(scan, toolType, versionId))}
                </tbody>
            </table>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (versions.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <h3 className="font-semibold mb-2">No Scan-Enabled Versions</h3>
                    <p className="text-muted-foreground">
                        Create a version with SonarQube or Trivy metrics selected to see scan status here.
                    </p>
                </CardContent>
            </Card>
        );
    }

    const failedCount = countFailedScans(commitScans);
    const isAutoRefreshing = hasRunningScans(commitScans);

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold">Commit Scan Status</h2>
                    {isAutoRefreshing && (
                        <Badge variant="outline" className="gap-1">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Auto-refreshing
                        </Badge>
                    )}
                </div>
                <Button variant="outline" size="sm" onClick={loadVersions}>
                    <RefreshCw className="h-4 w-4" />
                </Button>
            </div>

            {/* Version Cards */}
            {versions.map((version) => (
                <Card key={version.id}>
                    <CardHeader
                        className="cursor-pointer"
                        onClick={() => loadCommitScans(version.id)}
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base">
                                    Version {version.version_number}
                                    {version.name && ` - ${version.name}`}
                                </CardTitle>
                                <CardDescription className="flex items-center gap-2 mt-1">
                                    {version.scan_metrics?.trivy?.length ? (
                                        <Badge variant="secondary" className="text-xs">
                                            <Shield className="h-3 w-3 mr-1" />
                                            Trivy
                                        </Badge>
                                    ) : null}
                                    {version.scan_metrics?.sonarqube?.length ? (
                                        <Badge variant="secondary" className="text-xs">
                                            <Settings className="h-3 w-3 mr-1" />
                                            SonarQube
                                        </Badge>
                                    ) : null}
                                </CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge variant="outline">{version.status}</Badge>
                                {loadingScans && expandedVersionId === version.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : expandedVersionId === version.id ? (
                                    <ChevronUp className="h-4 w-4" />
                                ) : (
                                    <ChevronDown className="h-4 w-4" />
                                )}
                            </div>
                        </div>
                    </CardHeader>

                    {/* Expanded Content */}
                    {expandedVersionId === version.id && commitScans && (() => {
                        const stats = getScanStats(commitScans);
                        return (
                            <CardContent className="pt-0">
                                {/* Summary stats bar */}
                                <div className="flex items-center gap-4 mb-4 pb-4 border-b">
                                    <div className="flex items-center gap-2 text-sm">
                                        <span className="text-muted-foreground">Total:</span>
                                        <span className="font-medium">{stats.total}</span>
                                    </div>
                                    {stats.completed > 0 && (
                                        <Badge variant="secondary" className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                                            <CheckCircle2 className="h-3 w-3 mr-1" />
                                            {stats.completed} completed
                                        </Badge>
                                    )}
                                    {stats.scanning > 0 && (
                                        <Badge className="bg-blue-500">
                                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                            {stats.scanning} scanning
                                        </Badge>
                                    )}
                                    {stats.pending > 0 && (
                                        <Badge variant="secondary">
                                            <Clock className="h-3 w-3 mr-1" />
                                            {stats.pending} pending
                                        </Badge>
                                    )}
                                    {stats.failed > 0 && (
                                        <Badge variant="destructive">
                                            <XCircle className="h-3 w-3 mr-1" />
                                            {stats.failed} failed
                                        </Badge>
                                    )}
                                    {/* Bulk retry button */}
                                    {failedCount > 0 && (
                                        <div className="ml-auto">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleBulkRetry(version.id)}
                                                disabled={bulkRetrying}
                                            >
                                                {bulkRetrying ? (
                                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                ) : (
                                                    <RotateCcw className="h-4 w-4 mr-2" />
                                                )}
                                                Retry All Failed
                                            </Button>
                                        </div>
                                    )}
                                </div>
                                {/* Scan Tables */}
                                <div className="space-y-6">
                                    {/* Trivy Scans */}
                                    {version.scan_metrics?.trivy?.length ? (
                                        <div>
                                            <h4 className="font-medium mb-2 flex items-center gap-2">
                                                <Shield className="h-4 w-4" />
                                                Trivy Scans ({commitScans.trivy.length})
                                            </h4>
                                            <div className="border rounded-lg overflow-hidden">
                                                {renderScanTable(commitScans.trivy, "trivy", version.id)}
                                            </div>
                                        </div>
                                    ) : null}

                                    {/* SonarQube Scans */}
                                    {version.scan_metrics?.sonarqube?.length ? (
                                        <div>
                                            <h4 className="font-medium mb-2 flex items-center gap-2">
                                                <Settings className="h-4 w-4" />
                                                SonarQube Scans ({commitScans.sonarqube.length})
                                            </h4>
                                            <div className="border rounded-lg overflow-hidden">
                                                {renderScanTable(commitScans.sonarqube, "sonarqube", version.id)}
                                            </div>
                                        </div>
                                    ) : null}
                                </div>
                            </CardContent>
                        );
                    })()}
                </Card>
            ))}
        </div>
    );
}
