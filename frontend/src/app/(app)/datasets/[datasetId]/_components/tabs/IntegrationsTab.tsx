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
    Shield,
    Wifi,
    WifiOff,
} from "lucide-react";

interface IntegrationsTabProps {
    datasetId: string;
    sonarFeatures: string[];
    trivyFeatures: string[];
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

interface IntegrationTool {
    id: string;
    name: string;
    description: string;
    icon: React.ReactNode;
    status: "connected" | "coming_soon" | "not_configured";
    featuresCount?: number;
}

export function IntegrationsTab({
    datasetId,
    sonarFeatures,
    trivyFeatures
}: IntegrationsTabProps) {
    const [search, setSearch] = useState("");
    const [pendingScans, setPendingScans] = useState<PendingScan[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeIntegration, setActiveIntegration] = useState<string | null>("sonarqube");

    // Define available integrations
    const integrations: IntegrationTool[] = [
        {
            id: "sonarqube",
            name: "SonarQube",
            description: "Code quality & security analysis",
            icon: <Settings className="h-6 w-6" />,
            status: sonarFeatures.length > 0 ? "connected" : "not_configured",
            featuresCount: sonarFeatures.length,
        },
        {
            id: "trivy",
            name: "Trivy",
            description: "Container & dependency scanning",
            icon: <Shield className="h-6 w-6" />,
            status: trivyFeatures.length > 0 ? "connected" : "not_configured",
            featuresCount: trivyFeatures.length,
        },
    ];

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
    const filteredFeatures = sonarFeatures.filter((f) =>
        f.toLowerCase().includes(search.toLowerCase())
    );

    const scanningCount = pendingScans.filter((s) => s.status === "scanning").length;
    const completedCount = pendingScans.filter((s) => s.status === "completed").length;
    const failedCount = pendingScans.filter((s) => s.status === "failed").length;

    return (
        <div className="space-y-6">
            {/* Integration Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {integrations.map((integration) => (
                    <Card
                        key={integration.id}
                        className={`cursor-pointer transition-all hover:shadow-md ${activeIntegration === integration.id
                            ? "ring-2 ring-primary"
                            : ""
                            }`}
                        onClick={() => setActiveIntegration(integration.id)}
                    >
                        <CardContent className="pt-6">
                            <div className="flex items-start justify-between">
                                <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                                    {integration.icon}
                                </div>
                                {integration.status === "connected" && (
                                    <Badge className="bg-green-500">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        Connected
                                    </Badge>
                                )}
                                {integration.status === "not_configured" && (
                                    <Badge variant="outline">Not Configured</Badge>
                                )}
                            </div>
                            <h3 className="mt-4 font-semibold">{integration.name}</h3>
                            <p className="text-sm text-muted-foreground mt-1">
                                {integration.description}
                            </p>
                            {integration.featuresCount !== undefined && integration.featuresCount > 0 && (
                                <p className="text-sm text-primary mt-2">
                                    {integration.featuresCount} metrics selected
                                </p>
                            )}
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Active Integration Details */}
            {activeIntegration === "sonarqube" && (
                <div className="space-y-6">
                    {/* SonarQube Status Card */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="flex items-center gap-2">
                                        <Settings className="h-5 w-5" /> SonarQube
                                    </CardTitle>
                                    <CardDescription>
                                        {sonarFeatures.length} metrics selected
                                    </CardDescription>
                                </div>
                                <div className="flex items-center gap-2">
                                    {isConnected ? (
                                        <Badge variant="outline" className="border-green-500 text-green-600">
                                            <Wifi className="mr-1 h-3 w-3" /> Live
                                        </Badge>
                                    ) : (
                                        <Badge variant="secondary">
                                            <WifiOff className="mr-1 h-3 w-3" /> Offline
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

                    {/* Search Features */}
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            placeholder="Search SonarQube metrics..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-10"
                        />
                    </div>

                    {/* Metrics Table */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Selected Metrics</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="max-h-[400px] overflow-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-medium">Metric</th>
                                            <th className="px-4 py-3 text-left font-medium">Description</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                        {filteredFeatures.length === 0 ? (
                                            <tr>
                                                <td colSpan={2} className="px-4 py-8 text-center text-muted-foreground">
                                                    {sonarFeatures.length === 0
                                                        ? "No SonarQube metrics selected"
                                                        : "No metrics match your search"}
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

                    {/* Pending Scans */}
                    {pendingScans.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle>Pending Scans</CardTitle>
                                <CardDescription>Commits being analyzed</CardDescription>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="overflow-auto">
                                    <table className="min-w-full text-sm">
                                        <thead className="bg-slate-50 dark:bg-slate-800">
                                            <tr>
                                                <th className="px-4 py-3 text-left font-medium">Component</th>
                                                <th className="px-4 py-3 text-left font-medium">Status</th>
                                                <th className="px-4 py-3 text-left font-medium">Started</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {pendingScans.map((scan) => (
                                                <tr key={scan.component_key}>
                                                    <td className="px-4 py-2 font-mono text-xs">
                                                        {scan.component_key.slice(-20)}
                                                    </td>
                                                    <td className="px-4 py-2">
                                                        {scan.status === "scanning" && (
                                                            <Badge variant="secondary" className="gap-1">
                                                                <Loader2 className="h-3 w-3 animate-spin" /> Scanning
                                                            </Badge>
                                                        )}
                                                        {scan.status === "completed" && (
                                                            <Badge className="gap-1 bg-green-500">
                                                                <CheckCircle2 className="h-3 w-3" /> Done
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
            )}

            {/* Trivy Details */}
            {activeIntegration === "trivy" && (
                <div className="space-y-6">
                    {/* Trivy Status Card */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="flex items-center gap-2">
                                        <Shield className="h-5 w-5" /> Trivy
                                    </CardTitle>
                                    <CardDescription>
                                        {trivyFeatures.length} metrics selected
                                    </CardDescription>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline" className="border-blue-500 text-blue-600">
                                        Container & Dependency Scanning
                                    </Badge>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="grid gap-4 md:grid-cols-3">
                                <div className="flex items-center gap-3 rounded-lg bg-red-50 px-4 py-3 dark:bg-red-900/20">
                                    <AlertCircle className="h-5 w-5 text-red-500" />
                                    <div>
                                        <p className="text-sm font-medium">Vulnerabilities</p>
                                        <p className="text-xs text-muted-foreground">Critical & High</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 rounded-lg bg-amber-50 px-4 py-3 dark:bg-amber-900/20">
                                    <AlertCircle className="h-5 w-5 text-amber-500" />
                                    <div>
                                        <p className="text-sm font-medium">Misconfigurations</p>
                                        <p className="text-xs text-muted-foreground">Security issues</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 rounded-lg bg-purple-50 px-4 py-3 dark:bg-purple-900/20">
                                    <Shield className="h-5 w-5 text-purple-500" />
                                    <div>
                                        <p className="text-sm font-medium">Secrets</p>
                                        <p className="text-xs text-muted-foreground">Detected secrets</p>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Search Trivy Features */}
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            placeholder="Search Trivy metrics..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-10"
                        />
                    </div>

                    {/* Trivy Metrics Table */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Selected Metrics</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="max-h-[400px] overflow-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-medium">Metric</th>
                                            <th className="px-4 py-3 text-left font-medium">Description</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                        {trivyFeatures.filter(f => f.toLowerCase().includes(search.toLowerCase())).length === 0 ? (
                                            <tr>
                                                <td colSpan={2} className="px-4 py-8 text-center text-muted-foreground">
                                                    {trivyFeatures.length === 0
                                                        ? "No Trivy metrics selected"
                                                        : "No metrics match your search"}
                                                </td>
                                            </tr>
                                        ) : (
                                            trivyFeatures
                                                .filter(f => f.toLowerCase().includes(search.toLowerCase()))
                                                .map((feature) => {
                                                    const metricName = feature.replace("trivy_", "");
                                                    return (
                                                        <tr key={feature} className="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                                                            <td className="px-4 py-2 font-mono text-xs">{feature}</td>
                                                            <td className="px-4 py-2 text-muted-foreground">
                                                                {getTrivyMetricDescription(metricName)}
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
                </div>
            )}

            {/* Loading */}
            {loading && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
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

function getTrivyMetricDescription(metric: string): string {
    const descriptions: Record<string, string> = {
        vuln_critical: "Number of critical vulnerabilities",
        vuln_high: "Number of high severity vulnerabilities",
        vuln_medium: "Number of medium severity vulnerabilities",
        vuln_low: "Number of low severity vulnerabilities",
        vuln_total: "Total number of vulnerabilities",
        misconfig_critical: "Number of critical misconfigurations",
        misconfig_high: "Number of high severity misconfigurations",
        misconfig_medium: "Number of medium severity misconfigurations",
        misconfig_low: "Number of low severity misconfigurations",
        misconfig_total: "Total number of misconfigurations",
        secrets_count: "Number of detected secrets",
        scan_duration_ms: "Scan duration in milliseconds",
        packages_scanned: "Number of packages scanned",
        files_scanned: "Number of files scanned",
        has_critical: "Whether critical vulnerabilities exist",
        has_high: "Whether high severity vulnerabilities exist",
        top_vulnerable_packages: "List of most vulnerable packages",
    };
    return descriptions[metric] || `Trivy ${metric} metric`;
}

