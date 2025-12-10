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
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useDynamicWebSocket } from "@/hooks/use-websocket";
import {
    AlertCircle,
    CheckCircle2,
    Loader2,
    RefreshCw,
    Search,
    Settings,
    Wifi,
    WifiOff,
} from "lucide-react";

interface SonarFeaturesTabProps {
    datasetId: string;
    features: string[];
}

interface PendingScan {
    component_key: string;
    status: "scanning" | "completed" | "failed";
    build_id: string;
    started_at: string | null;
    completed_at: string | null;
    has_metrics: boolean;
    error_message: string | null;
}

export function SonarFeaturesTab({ datasetId, features }: SonarFeaturesTabProps) {
    const [search, setSearch] = useState("");
    const [pendingScans, setPendingScans] = useState<PendingScan[]>([]);
    const [loading, setLoading] = useState(true);

    // Load pending scans
    const loadPendingScans = useCallback(async () => {
        try {
            const response = await api.get<{ items: PendingScan[] }>(
                `/sonar/dataset/${datasetId}/pending`
            );
            setPendingScans(response.data.items || []);
        } catch {
            setPendingScans([]);
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    // Use shared WebSocket hook
    const { isConnected } = useDynamicWebSocket({
        path: `/api/sonar/ws/dataset/${datasetId}`,
        onMessage: (data) => {
            if (data.type === "scan_update") {
                setPendingScans((prev) =>
                    prev.map((scan) =>
                        scan.component_key === data.component_key
                            ? { ...scan, ...data }
                            : scan
                    )
                );
            } else if (data.type === "scan_complete") {
                setPendingScans((prev) =>
                    prev.filter((scan) => scan.component_key !== data.component_key)
                );
            }
        },
    });

    useEffect(() => {
        loadPendingScans();
    }, [loadPendingScans]);

    // Filter features
    const filteredFeatures = features.filter((f) =>
        f.toLowerCase().includes(search.toLowerCase())
    );

    const scanningCount = pendingScans.filter((s) => s.status === "scanning").length;
    const completedCount = pendingScans.filter((s) => s.status === "completed").length;
    const failedCount = pendingScans.filter((s) => s.status === "failed").length;

    return (
        <div className="space-y-6">
            {/* Status Card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Settings className="h-5 w-5" /> SonarQube Features
                            </CardTitle>
                            <CardDescription>
                                {features.length} sonar features selected
                            </CardDescription>
                        </div>
                        <div className="flex items-center gap-2">
                            {isConnected ? (
                                <Badge variant="outline" className="border-green-500 text-green-600">
                                    <Wifi className="mr-1 h-3 w-3" /> Connected
                                </Badge>
                            ) : (
                                <Badge variant="secondary">
                                    <WifiOff className="mr-1 h-3 w-3" /> Disconnected
                                </Badge>
                            )}
                            <Button variant="outline" size="sm" onClick={loadPendingScans}>
                                <RefreshCw className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-3">
                        <div className="flex items-center gap-3 rounded-lg bg-blue-50 px-4 py-3 dark:bg-blue-900/20">
                            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
                            <div>
                                <p className="text-sm font-medium">{scanningCount} Scanning</p>
                                <p className="text-xs text-muted-foreground">In progress</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 rounded-lg bg-green-50 px-4 py-3 dark:bg-green-900/20">
                            <CheckCircle2 className="h-5 w-5 text-green-500" />
                            <div>
                                <p className="text-sm font-medium">{completedCount} Completed</p>
                                <p className="text-xs text-muted-foreground">Ready</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 rounded-lg bg-red-50 px-4 py-3 dark:bg-red-900/20">
                            <AlertCircle className="h-5 w-5 text-red-500" />
                            <div>
                                <p className="text-sm font-medium">{failedCount} Failed</p>
                                <p className="text-xs text-muted-foreground">Errors</p>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    placeholder="Search sonar features..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-10"
                />
            </div>

            {/* Features Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Selected SonarQube Metrics</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="max-h-[400px] overflow-auto">
                        <table className="min-w-full text-sm">
                            <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                <tr>
                                    <th className="px-4 py-3 text-left font-medium">Feature Name</th>
                                    <th className="px-4 py-3 text-left font-medium">Description</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y">
                                {filteredFeatures.length === 0 ? (
                                    <tr>
                                        <td colSpan={2} className="px-4 py-8 text-center text-muted-foreground">
                                            {features.length === 0
                                                ? "No SonarQube features selected"
                                                : "No features match your search"}
                                        </td>
                                    </tr>
                                ) : (
                                    filteredFeatures.map((feature) => {
                                        const metricName = feature.replace("sonar_", "");
                                        return (
                                            <tr key={feature} className="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                                                <td className="px-4 py-2 font-mono text-xs">{feature}</td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {getMetricDescription(metricName)}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Pending Scans Table */}
            {pendingScans.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Pending Scans</CardTitle>
                        <CardDescription>Commits being scanned by SonarQube</CardDescription>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="overflow-auto">
                            <table className="min-w-full text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        <th className="px-4 py-3 text-left font-medium">Component Key</th>
                                        <th className="px-4 py-3 text-left font-medium">Status</th>
                                        <th className="px-4 py-3 text-left font-medium">Started</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {pendingScans.map((scan) => (
                                        <tr key={scan.component_key}>
                                            <td className="px-4 py-2 font-mono text-xs">
                                                {scan.component_key.slice(-15)}
                                            </td>
                                            <td className="px-4 py-2">
                                                {scan.status === "scanning" && (
                                                    <Badge variant="secondary" className="gap-1">
                                                        <Loader2 className="h-3 w-3 animate-spin" /> Scanning
                                                    </Badge>
                                                )}
                                                {scan.status === "completed" && (
                                                    <Badge className="gap-1 bg-green-500">
                                                        <CheckCircle2 className="h-3 w-3" /> Completed
                                                    </Badge>
                                                )}
                                                {scan.status === "failed" && (
                                                    <Badge variant="destructive" className="gap-1">
                                                        <AlertCircle className="h-3 w-3" /> Failed
                                                    </Badge>
                                                )}
                                            </td>
                                            <td className="px-4 py-2 text-muted-foreground">
                                                {scan.started_at
                                                    ? new Date(scan.started_at).toLocaleTimeString()
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
        </div>
    );
}

function getMetricDescription(metric: string): string {
    const descriptions: Record<string, string> = {
        bugs: "Number of bug issues",
        vulnerabilities: "Number of vulnerability issues",
        code_smells: "Number of code smell issues",
        coverage: "Code coverage percentage",
        duplicated_lines_density: "Duplicated lines percentage",
        ncloc: "Non-comment lines of code",
        complexity: "Cyclomatic complexity",
        cognitive_complexity: "Cognitive complexity",
        sqale_index: "Technical debt in minutes",
        reliability_rating: "Reliability rating (A-E)",
        security_rating: "Security rating (A-E)",
        sqale_rating: "Maintainability rating (A-E)",
    };
    return descriptions[metric] || `SonarQube ${metric} metric`;
}
