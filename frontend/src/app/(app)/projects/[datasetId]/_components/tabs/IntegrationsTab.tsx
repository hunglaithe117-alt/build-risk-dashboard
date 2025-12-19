"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
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
import { api, datasetScanApi } from "@/lib/api";
import { useDynamicWebSocket } from "@/hooks/use-websocket";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Clock,
    Code,
    Loader2,
    Play,
    RefreshCw,
    RotateCcw,
    Settings,
    Shield,
    StopCircle,
    Wifi,
    WifiOff,
    XCircle,
    Eye,
    Download,
} from "lucide-react";
import { ScanConfigModal } from "./ScanConfigModal";

// =============================================================================
// Types
// =============================================================================

interface IntegrationsTabProps {
    datasetId: string;
}

interface ToolInfo {
    type: string;
    display_name: string;
    description: string;
    scan_mode: string;
    is_available: boolean;
    config: Record<string, unknown>;
    scan_types: string[];
    metric_count: number;
}

interface UniqueCommit {
    sha: string;
    repo_full_name: string;
}

interface DatasetScan {
    id: string;
    dataset_id: string;
    tool_type: string;
    status: string;
    total_commits: number;
    scanned_commits: number;
    failed_commits: number;
    pending_commits: number;
    progress_percentage: number;
    started_at: string | null;
    completed_at: string | null;
    results_summary?: Record<string, unknown>;
    error_message?: string | null;
}

interface FailedResult {
    id: string;
    commit_sha: string;
    repo_full_name: string;
    error_message: string | null;
    retry_count: number;
    override_config: string | null;
}

// =============================================================================
// Component
// =============================================================================

export function IntegrationsTab({ datasetId }: IntegrationsTabProps) {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";

    const [tools, setTools] = useState<ToolInfo[]>([]);
    const [scans, setScans] = useState<DatasetScan[]>([]);
    const [loading, setLoading] = useState(true);

    // Selection state
    const [selectedTool, setSelectedTool] = useState<string | null>(null);
    const [isStartingScan, setIsStartingScan] = useState(false);

    // Config modal state
    const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
    const [configModalMode, setConfigModalMode] = useState<"start" | "retry">("start");
    const [retryResultId, setRetryResultId] = useState<string | null>(null);
    const [retryScanId, setRetryScanId] = useState<string | null>(null);
    const [retryCommitSha, setRetryCommitSha] = useState<string | null>(null);

    // Expanded scan state for showing failed results
    const [expandedScanId, setExpandedScanId] = useState<string | null>(null);
    const [failedResults, setFailedResults] = useState<FailedResult[]>([]);
    const [loadingFailedResults, setLoadingFailedResults] = useState(false);

    // Load tools
    const loadTools = useCallback(async () => {
        try {
            const response = await api.get<{ tools: ToolInfo[] }>("/integrations/tools");
            setTools(response.data.tools || []);
        } catch {
            setTools([]);
        }
    }, []);

    // Load scans (active + history)
    const loadScans = useCallback(async () => {
        try {
            const response = await api.get<{ scans: DatasetScan[]; total: number }>(
                `/integrations/datasets/${datasetId}/scans?limit=20`
            );
            setScans(response.data.scans || []);
        } catch {
            setScans([]);
        }
    }, [datasetId]);

    // WebSocket for real-time updates
    const { isConnected } = useDynamicWebSocket({
        path: `/api/integrations/ws/dataset/${datasetId}`,
        onMessage: (data) => {
            if (data.type === "scan_update" && data.scan) {
                setScans((prev) =>
                    prev.map((scan) =>
                        scan.id === data.scan.id ? { ...scan, ...data.scan } : scan
                    )
                );
            }
        },
    });

    // Initial load
    useEffect(() => {
        const load = async () => {
            setLoading(true);
            await Promise.all([loadTools(), loadScans()]);
            setLoading(false);
        };
        load();
    }, [loadTools, loadScans]);

    // Handle start scan with config
    const handleStartScan = async (scanConfig: string | null = null) => {
        if (!selectedTool) return;

        setIsStartingScan(true);
        try {
            const response = await api.post<DatasetScan>(
                `/integrations/datasets/${datasetId}/scans`,
                {
                    tool_type: selectedTool,
                    scan_config: scanConfig,
                }
            );
            setScans((prev) => [response.data, ...prev]);
        } catch (error) {
            console.error("Failed to start scan:", error);
        } finally {
            setIsStartingScan(false);
        }
    };

    // Handle cancel scan
    const handleCancelScan = async (scanId: string) => {
        try {
            await api.delete(`/integrations/datasets/${datasetId}/scans/${scanId}`);
            setScans((prev) =>
                prev.map((s) => (s.id === scanId ? { ...s, status: "cancelled" } : s))
            );
        } catch (error) {
            console.error("Failed to cancel scan:", error);
        }
    };



    // Open config modal for starting scan
    const openStartScanModal = () => {
        setConfigModalMode("start");
        setRetryResultId(null);
        setRetryScanId(null);
        setRetryCommitSha(null);
        setIsConfigModalOpen(true);
    };

    // Handle config modal submit
    const handleConfigSubmit = async (config: string | null) => {
        if (configModalMode === "start") {
            await handleStartScan(config);
        } else if (retryResultId && retryScanId) {
            await handleRetryResult(retryResultId, retryScanId, config);
        }
        setIsConfigModalOpen(false);
    };

    // Load failed results for a scan
    const loadFailedResults = async (scanId: string) => {
        if (expandedScanId === scanId) {
            setExpandedScanId(null);
            return;
        }

        setLoadingFailedResults(true);
        try {
            const response = await api.get<{ results: FailedResult[] }>(
                `/integrations/datasets/${datasetId}/scans/${scanId}/failed`
            );
            setFailedResults(response.data.results);
            setExpandedScanId(scanId);
        } catch (error) {
            console.error("Failed to load failed results:", error);
        } finally {
            setLoadingFailedResults(false);
        }
    };

    // Open retry modal for a specific result
    const openRetryModal = (resultId: string, scanId: string, commitSha: string) => {
        setConfigModalMode("retry");
        setRetryResultId(resultId);
        setRetryScanId(scanId);
        setRetryCommitSha(commitSha);
        setIsConfigModalOpen(true);
    };

    // Handle retry result
    const handleRetryResult = async (resultId: string, scanId: string, overrideConfig: string | null) => {
        try {
            await api.post(
                `/integrations/datasets/${datasetId}/scans/${scanId}/results/${resultId}/retry`,
                { override_config: overrideConfig }
            );
            // Reload scans and failed results
            await loadScans();
            if (expandedScanId === scanId) {
                await loadFailedResults(scanId);
            }
        } catch (error) {
            console.error("Failed to retry result:", error);
        }
    };

    const activeScans = scans.filter(
        (s) => s.status === "running" || s.status === "pending" || s.status === "partial"
    );
    const historyScans = scans.filter(
        (s) => s.status === "completed" || s.status === "failed" || s.status === "cancelled"
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Connection Status */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Dataset Scanning</h2>
                <div className="flex items-center gap-2">
                    {isConnected ? (
                        <Badge variant="outline" className="border-green-500 text-green-600">
                            <Wifi className="mr-1 h-3 w-3" /> Live Updates
                        </Badge>
                    ) : (
                        <Badge variant="secondary">
                            <WifiOff className="mr-1 h-3 w-3" /> Offline
                        </Badge>
                    )}
                    <Button variant="outline" size="sm" onClick={() => loadScans()}>
                        <RefreshCw className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Tool Selection Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {tools.map((tool) => (
                    <Card
                        key={tool.type}
                        className={`cursor-pointer transition-all hover:shadow-md ${selectedTool === tool.type ? "ring-2 ring-primary" : ""
                            } ${!tool.is_available ? "opacity-60" : ""}`}
                        onClick={() => tool.is_available && setSelectedTool(tool.type)}
                    >
                        <CardContent className="pt-6">
                            <div className="flex items-start justify-between">
                                <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                                    {tool.type === "sonarqube" ? (
                                        <Settings className="h-6 w-6" />
                                    ) : (
                                        <Shield className="h-6 w-6" />
                                    )}
                                </div>
                                {tool.is_available ? (
                                    <Badge className="bg-green-500">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        Available
                                    </Badge>
                                ) : (
                                    <Badge variant="outline">Not Configured</Badge>
                                )}
                            </div>
                            <h3 className="mt-4 font-semibold">{tool.display_name}</h3>
                            <p className="text-sm text-muted-foreground mt-1">
                                {tool.description}
                            </p>
                            <div className="flex items-center gap-2 mt-2">
                                <Badge variant="secondary" className="text-xs">
                                    {tool.scan_mode === "sync" ? "Instant" : "Async"}
                                </Badge>
                                <span className="text-sm text-muted-foreground">
                                    {tool.metric_count} metrics
                                </span>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Start Scan Panel - Admin only */}
            {isAdmin && selectedTool && (
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <h3 className="font-semibold">Ready to Scan</h3>
                                <p className="text-sm text-muted-foreground">
                                    All validated builds in this dataset will be scanned
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={openStartScanModal}
                                >
                                    <Code className="h-4 w-4 mr-1" />
                                    Configure
                                </Button>
                                <Button
                                    size="sm"
                                    disabled={isStartingScan}
                                    onClick={() => handleStartScan(null)}
                                >
                                    {isStartingScan ? (
                                        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                    ) : (
                                        <Play className="h-4 w-4 mr-1" />
                                    )}
                                    Start Scan
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Active Scans */}
            {activeScans.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Loader2 className="h-5 w-5 animate-spin" />
                            Active Scans
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {activeScans.map((scan) => (
                            <div
                                key={scan.id}
                                className="flex items-center gap-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-900"
                            >
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Badge>
                                            {scan.tool_type === "sonarqube"
                                                ? "SonarQube"
                                                : "Trivy"}
                                        </Badge>
                                        <span className="text-sm text-muted-foreground">
                                            {scan.scanned_commits}/{scan.total_commits} commits
                                        </span>
                                        {scan.status === "partial" && (
                                            <Badge variant="outline" className="text-amber-600">
                                                <Clock className="h-3 w-3 mr-1" />
                                                Waiting webhook
                                            </Badge>
                                        )}
                                    </div>
                                    <Progress value={scan.progress_percentage} className="h-2" />
                                    <p className="text-xs text-muted-foreground mt-1">
                                        {Math.round(scan.progress_percentage)}% complete
                                    </p>
                                </div>
                                {isAdmin && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleCancelScan(scan.id)}
                                    >
                                        <StopCircle className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        ))}
                    </CardContent>
                </Card>
            )}

            {/* Scan History */}
            {historyScans.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Scan History</CardTitle>
                        <CardDescription>Previous scans for this dataset</CardDescription>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="overflow-auto">
                            <table className="min-w-full text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        <th className="px-4 py-3 text-left font-medium">Tool</th>
                                        <th className="px-4 py-3 text-left font-medium">Status</th>
                                        <th className="px-4 py-3 text-left font-medium">Commits</th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Completed
                                        </th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {historyScans.map((scan) => (
                                        <React.Fragment key={scan.id}>
                                            <tr>
                                                <td className="px-4 py-3">
                                                    <Badge variant="outline">
                                                        {scan.tool_type === "sonarqube"
                                                            ? "SonarQube"
                                                            : "Trivy"}
                                                    </Badge>
                                                </td>
                                                <td className="px-4 py-3">
                                                    {scan.status === "completed" && (
                                                        <Badge className="bg-green-500">
                                                            <CheckCircle2 className="h-3 w-3 mr-1" />
                                                            Completed
                                                        </Badge>
                                                    )}
                                                    {scan.status === "failed" && (
                                                        <Badge variant="destructive">
                                                            <XCircle className="h-3 w-3 mr-1" />
                                                            Failed
                                                        </Badge>
                                                    )}
                                                    {scan.status === "cancelled" && (
                                                        <Badge variant="secondary">
                                                            <AlertCircle className="h-3 w-3 mr-1" />
                                                            Cancelled
                                                        </Badge>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <span className="text-green-600">
                                                        {scan.scanned_commits}
                                                    </span>
                                                    {scan.failed_commits > 0 && (
                                                        <span className="text-red-600 ml-1">
                                                            / {scan.failed_commits} failed
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-muted-foreground">
                                                    {scan.completed_at
                                                        ? new Date(scan.completed_at).toLocaleString()
                                                        : "—"}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="flex gap-1">
                                                        {/* View Results */}
                                                        {scan.scanned_commits > 0 && (
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                onClick={() => window.open(`/projects/${datasetId}/scans/${scan.id}/results`, '_blank')}
                                                                title="View Results"
                                                            >
                                                                <Eye className="h-4 w-4" />
                                                            </Button>
                                                        )}
                                                        {/* Export Results */}
                                                        {scan.scanned_commits > 0 && (
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                onClick={() => datasetScanApi.exportResults(datasetId, scan.id)}
                                                                title="Export CSV"
                                                            >
                                                                <Download className="h-4 w-4" />
                                                            </Button>
                                                        )}
                                                        {/* Failed Results Toggle */}
                                                        {scan.failed_commits > 0 && (
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                onClick={() => loadFailedResults(scan.id)}
                                                                disabled={loadingFailedResults}
                                                                title="View Failed"
                                                            >
                                                                {expandedScanId === scan.id ? (
                                                                    <ChevronUp className="h-4 w-4" />
                                                                ) : (
                                                                    <ChevronDown className="h-4 w-4" />
                                                                )}
                                                            </Button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                            {/* Expanded Failed Results */}
                                            {expandedScanId === scan.id && failedResults.length > 0 && (
                                                <tr>
                                                    <td colSpan={5} className="bg-slate-50/50 dark:bg-slate-900/50 p-4">
                                                        <div className="space-y-2">
                                                            <h4 className="font-medium text-sm mb-3">
                                                                Failed Commits ({failedResults.length})
                                                            </h4>
                                                            {failedResults.map((result) => (
                                                                <div
                                                                    key={result.id}
                                                                    className="flex items-start justify-between p-3 rounded-lg bg-white dark:bg-slate-800 border"
                                                                >
                                                                    <div className="flex-1">
                                                                        <div className="flex items-center gap-2 mb-1">
                                                                            <span className="font-mono text-sm">
                                                                                {result.commit_sha.slice(0, 8)}
                                                                            </span>
                                                                            <span className="text-muted-foreground text-sm">
                                                                                {result.repo_full_name}
                                                                            </span>
                                                                            {result.retry_count > 0 && (
                                                                                <Badge variant="secondary" className="text-xs">
                                                                                    Retried {result.retry_count}x
                                                                                </Badge>
                                                                            )}
                                                                        </div>
                                                                        {result.error_message && (
                                                                            <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded mt-2">
                                                                                <AlertCircle className="h-3 w-3 inline mr-1" />
                                                                                {result.error_message}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                    {isAdmin && (
                                                                        <div className="flex gap-2 ml-4">
                                                                            <Button
                                                                                variant="outline"
                                                                                size="sm"
                                                                                onClick={() => openRetryModal(result.id, scan.id, result.commit_sha)}
                                                                            >
                                                                                <Code className="h-4 w-4 mr-1" />
                                                                                Config
                                                                            </Button>
                                                                            <Button
                                                                                size="sm"
                                                                                onClick={() => handleRetryResult(result.id, scan.id, null)}
                                                                            >
                                                                                <RotateCcw className="h-4 w-4 mr-1" />
                                                                                Retry
                                                                            </Button>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Empty State */}
            {tools.length === 0 && (
                <Card>
                    <CardContent className="py-12 text-center">
                        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                        <h3 className="font-semibold mb-2">No Integration Tools Available</h3>
                        <p className="text-muted-foreground">
                            Configure SonarQube or enable Trivy in your environment settings.
                        </p>
                    </CardContent>
                </Card>
            )}

            {/* Config Modal */}
            <ScanConfigModal
                isOpen={isConfigModalOpen}
                onClose={() => setIsConfigModalOpen(false)}
                onSubmit={handleConfigSubmit}
                toolType={selectedTool || "sonarqube"}
                mode={configModalMode}
                commitSha={retryCommitSha || undefined}
            />
        </div>
    );
}
