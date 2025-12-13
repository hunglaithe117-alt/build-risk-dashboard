"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import { useDynamicWebSocket } from "@/hooks/use-websocket";
import {
    AlertCircle,
    CheckCircle2,
    Clock,
    Loader2,
    Play,
    RefreshCw,
    Settings,
    Shield,
    StopCircle,
    Wifi,
    WifiOff,
    XCircle,
} from "lucide-react";

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
    row_count: number;
    row_indices: number[];
    last_scanned: string | null;
    scan_results: Record<string, unknown> | null;
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

// =============================================================================
// Component
// =============================================================================

export function IntegrationsTab({ datasetId }: IntegrationsTabProps) {
    const [tools, setTools] = useState<ToolInfo[]>([]);
    const [commits, setCommits] = useState<UniqueCommit[]>([]);
    const [scans, setScans] = useState<DatasetScan[]>([]);
    const [loading, setLoading] = useState(true);

    // Selection state
    const [selectedTool, setSelectedTool] = useState<string | null>(null);
    const [selectedCommits, setSelectedCommits] = useState<Set<string>>(new Set());
    const [isStartingScan, setIsStartingScan] = useState(false);

    // Load tools
    const loadTools = useCallback(async () => {
        try {
            const response = await api.get<{ tools: ToolInfo[] }>("/integrations/tools");
            setTools(response.data.tools || []);
        } catch {
            setTools([]);
        }
    }, []);

    // Load unique commits
    const loadCommits = useCallback(async () => {
        try {
            const response = await api.get<{ commits: UniqueCommit[]; total: number }>(
                `/integrations/datasets/${datasetId}/commits`
            );
            setCommits(response.data.commits || []);
        } catch {
            setCommits([]);
        }
    }, [datasetId]);

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
            await Promise.all([loadTools(), loadCommits(), loadScans()]);
            setLoading(false);
        };
        load();
    }, [loadTools, loadCommits, loadScans]);

    // Handle start scan
    const handleStartScan = async () => {
        if (!selectedTool || selectedCommits.size === 0) return;

        setIsStartingScan(true);
        try {
            const response = await api.post<DatasetScan>(
                `/integrations/datasets/${datasetId}/scans`,
                {
                    tool_type: selectedTool,
                    selected_commit_shas: Array.from(selectedCommits),
                }
            );
            setScans((prev) => [response.data, ...prev]);
            setSelectedCommits(new Set());
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

    // Toggle commit selection
    const toggleCommit = (sha: string) => {
        setSelectedCommits((prev) => {
            const newSet = new Set(prev);
            if (newSet.has(sha)) {
                newSet.delete(sha);
            } else {
                newSet.add(sha);
            }
            return newSet;
        });
    };

    // Select/deselect all
    const toggleAllCommits = () => {
        if (selectedCommits.size === commits.length) {
            setSelectedCommits(new Set());
        } else {
            setSelectedCommits(new Set(commits.map((c) => c.sha)));
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

            {/* Commit Selection Panel */}
            {selectedTool && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle>Select Commits to Scan</CardTitle>
                                <CardDescription>
                                    {commits.length} unique commits found in dataset
                                </CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge variant="outline">
                                    {selectedCommits.size} selected
                                </Badge>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={toggleAllCommits}
                                >
                                    {selectedCommits.size === commits.length
                                        ? "Deselect All"
                                        : "Select All"}
                                </Button>
                                <Button
                                    size="sm"
                                    disabled={selectedCommits.size === 0 || isStartingScan}
                                    onClick={handleStartScan}
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
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="max-h-[300px] overflow-auto">
                            <table className="min-w-full text-sm">
                                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        <th className="px-4 py-3 text-left w-12">
                                            <Checkbox
                                                checked={selectedCommits.size === commits.length}
                                                onCheckedChange={toggleAllCommits}
                                            />
                                        </th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Commit
                                        </th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Repository
                                        </th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Rows
                                        </th>
                                        <th className="px-4 py-3 text-left font-medium">
                                            Status
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {commits.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={5}
                                                className="px-4 py-8 text-center text-muted-foreground"
                                            >
                                                No commits found in dataset
                                            </td>
                                        </tr>
                                    ) : (
                                        commits.map((commit) => (
                                            <tr
                                                key={commit.sha}
                                                className="hover:bg-slate-50 dark:hover:bg-slate-900/40 cursor-pointer"
                                                onClick={() => toggleCommit(commit.sha)}
                                            >
                                                <td className="px-4 py-2">
                                                    <Checkbox
                                                        checked={selectedCommits.has(commit.sha)}
                                                        onCheckedChange={() =>
                                                            toggleCommit(commit.sha)
                                                        }
                                                    />
                                                </td>
                                                <td className="px-4 py-2 font-mono text-xs">
                                                    {commit.sha.slice(0, 8)}
                                                </td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {commit.repo_full_name}
                                                </td>
                                                <td className="px-4 py-2">
                                                    <Badge variant="secondary">
                                                        {commit.row_count}
                                                    </Badge>
                                                </td>
                                                <td className="px-4 py-2">
                                                    {commit.last_scanned ? (
                                                        <Badge
                                                            variant="outline"
                                                            className="border-green-500 text-green-600"
                                                        >
                                                            <CheckCircle2 className="h-3 w-3 mr-1" />
                                                            Scanned
                                                        </Badge>
                                                    ) : (
                                                        <Badge variant="secondary">Not scanned</Badge>
                                                    )}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
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
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCancelScan(scan.id)}
                                >
                                    <StopCircle className="h-4 w-4" />
                                </Button>
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
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {historyScans.map((scan) => (
                                        <tr key={scan.id}>
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
                                        </tr>
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
        </div>
    );
}
