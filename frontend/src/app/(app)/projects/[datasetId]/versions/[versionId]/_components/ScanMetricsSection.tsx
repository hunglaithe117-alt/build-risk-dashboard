"use client";

import { useEffect, useState } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    ChevronDown,
    ChevronUp,
    Loader2,
    Shield,
    Bug,
    AlertTriangle,
    Zap,
    FileWarning,
    Lock,
} from "lucide-react";
import {
    statisticsApi,
    type ScanMetricsStatisticsResponse,
    type MetricSummary,
} from "@/lib/api";

interface ScanMetricsSectionProps {
    datasetId: string;
    versionId: string;
    versionStatus: string;
}

// Severity color helpers
function getSeverityColor(severity: "critical" | "high" | "medium" | "low"): string {
    switch (severity) {
        case "critical":
            return "bg-red-600 text-white";
        case "high":
            return "bg-orange-500 text-white";
        case "medium":
            return "bg-yellow-500 text-black";
        case "low":
            return "bg-green-500 text-white";
    }
}

function getSeverityDot(severity: "critical" | "high" | "medium" | "low"): string {
    switch (severity) {
        case "critical":
            return "bg-red-600";
        case "high":
            return "bg-orange-500";
        case "medium":
            return "bg-yellow-500";
        case "low":
            return "bg-green-500";
    }
}

function getRatingLabel(rating: number | null): string {
    if (rating === null) return "N/A";
    if (rating <= 1.5) return "A";
    if (rating <= 2.5) return "B";
    if (rating <= 3.5) return "C";
    if (rating <= 4.5) return "D";
    return "E";
}

function getRatingColor(rating: number | null): string {
    if (rating === null) return "bg-gray-200 text-gray-600";
    if (rating <= 1.5) return "bg-green-100 text-green-800";
    if (rating <= 2.5) return "bg-lime-100 text-lime-800";
    if (rating <= 3.5) return "bg-yellow-100 text-yellow-800";
    if (rating <= 4.5) return "bg-orange-100 text-orange-800";
    return "bg-red-100 text-red-800";
}

export function ScanMetricsSection({
    datasetId,
    versionId,
    versionStatus,
}: ScanMetricsSectionProps) {
    const [scanMetrics, setScanMetrics] = useState<ScanMetricsStatisticsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isOpen, setIsOpen] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchScanMetrics = async () => {
            if (!versionId) return;

            // Only fetch if version is processed
            if (!["processed", "completed"].includes(versionStatus)) {
                setIsLoading(false);
                return;
            }

            setIsLoading(true);
            setError(null);

            try {
                const data = await statisticsApi.getScanMetrics(datasetId, versionId);
                setScanMetrics(data);
            } catch (err) {
                console.error("Failed to fetch scan metrics:", err);
                setError("Failed to load scan metrics");
            } finally {
                setIsLoading(false);
            }
        };

        fetchScanMetrics();
    }, [datasetId, versionId, versionStatus]);

    // Don't render if not processed yet
    if (!["processed", "completed"].includes(versionStatus)) {
        return null;
    }

    if (isLoading) {
        return (
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Shield className="h-4 w-4" />
                        Scan Metrics
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error || !scanMetrics) {
        return null;
    }

    const { scan_summary, trivy_summary, sonar_summary } = scanMetrics;

    // If no scans at all, don't show section
    if (scan_summary.builds_with_any_scan === 0) {
        return null;
    }

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <Card>
                <CollapsibleTrigger asChild>
                    <CardHeader className="cursor-pointer hover:bg-muted/50">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Shield className="h-4 w-4" />
                                    Scan Metrics
                                    {trivy_summary.has_critical_count > 0 && (
                                        <Badge variant="destructive" className="ml-2">
                                            {trivy_summary.has_critical_count} Critical
                                        </Badge>
                                    )}
                                </CardTitle>
                                <CardDescription>
                                    Security and code quality metrics from Trivy & SonarQube
                                </CardDescription>
                            </div>
                            {isOpen ? (
                                <ChevronUp className="h-4 w-4" />
                            ) : (
                                <ChevronDown className="h-4 w-4" />
                            )}
                        </div>
                    </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                    <CardContent className="pt-0 space-y-4">
                        {/* Coverage Summary */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                            <div className="p-3 rounded-lg bg-muted/30">
                                <p className="text-2xl font-bold">{scan_summary.total_builds}</p>
                                <p className="text-xs text-muted-foreground">Total Builds</p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/30">
                                <p className="text-2xl font-bold">{scan_summary.builds_with_trivy}</p>
                                <p className="text-xs text-muted-foreground">Trivy Scans</p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/30">
                                <p className="text-2xl font-bold">{scan_summary.builds_with_sonar}</p>
                                <p className="text-xs text-muted-foreground">SonarQube Scans</p>
                            </div>
                            <div className="p-3 rounded-lg bg-muted/30">
                                <p className="text-2xl font-bold text-green-600">
                                    {scan_summary.trivy_coverage_pct}%
                                </p>
                                <p className="text-xs text-muted-foreground">Coverage</p>
                            </div>
                        </div>

                        {/* Two-column layout for Trivy and SonarQube */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Trivy Card */}
                            {trivy_summary.total_scans > 0 && (
                                <TrivyCard trivy={trivy_summary} />
                            )}

                            {/* SonarQube Card */}
                            {sonar_summary.total_scans > 0 && (
                                <SonarCard sonar={sonar_summary} />
                            )}
                        </div>
                    </CardContent>
                </CollapsibleContent>
            </Card>
        </Collapsible>
    );
}

// =============================================================================
// Sub-components
// =============================================================================

interface TrivyCardProps {
    trivy: ScanMetricsStatisticsResponse["trivy_summary"];
}

function TrivyCard({ trivy }: TrivyCardProps) {
    return (
        <div className="p-4 rounded-lg border bg-card">
            <div className="flex items-center gap-2 mb-3">
                <Shield className="h-4 w-4 text-blue-500" />
                <h4 className="font-semibold">Trivy Security</h4>
                <Badge variant="outline" className="ml-auto">
                    {trivy.total_scans} scans
                </Badge>
            </div>

            {/* Vulnerabilities */}
            <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Vulnerabilities
                    <span className="ml-auto text-muted-foreground">
                        Total: {trivy.vuln_total.sum}
                    </span>
                </div>
                <div className="flex gap-1.5">
                    <SeverityBadge
                        severity="critical"
                        value={trivy.vuln_critical.sum}
                    />
                    <SeverityBadge
                        severity="high"
                        value={trivy.vuln_high.sum}
                    />
                    <SeverityBadge
                        severity="medium"
                        value={trivy.vuln_medium.sum}
                    />
                    <SeverityBadge
                        severity="low"
                        value={trivy.vuln_low.sum}
                    />
                </div>
            </div>

            {/* Misconfigurations */}
            <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <FileWarning className="h-3.5 w-3.5" />
                    Misconfigurations
                    <span className="ml-auto text-muted-foreground">
                        Total: {trivy.misconfig_total.sum}
                    </span>
                </div>
                <div className="flex gap-1.5">
                    <SeverityBadge
                        severity="critical"
                        value={trivy.misconfig_critical.sum}
                    />
                    <SeverityBadge
                        severity="high"
                        value={trivy.misconfig_high.sum}
                    />
                    <SeverityBadge
                        severity="medium"
                        value={trivy.misconfig_medium.sum}
                    />
                    <SeverityBadge
                        severity="low"
                        value={trivy.misconfig_low.sum}
                    />
                </div>
            </div>

            {/* Secrets */}
            {trivy.secrets_count.sum > 0 && (
                <div className="flex items-center gap-2 text-sm p-2 rounded bg-red-50 dark:bg-red-900/20">
                    <Lock className="h-3.5 w-3.5 text-red-500" />
                    <span>Secrets Detected:</span>
                    <Badge variant="destructive">{trivy.secrets_count.sum}</Badge>
                </div>
            )}

            {/* Stats */}
            <div className="mt-3 pt-3 border-t text-xs text-muted-foreground grid grid-cols-2 gap-2">
                <div>
                    Avg Scan: {(trivy.scan_duration_ms.avg / 1000).toFixed(1)}s
                </div>
                <div>
                    Builds with Critical: {trivy.has_critical_count}
                </div>
            </div>
        </div>
    );
}

interface SonarCardProps {
    sonar: ScanMetricsStatisticsResponse["sonar_summary"];
}

function SonarCard({ sonar }: SonarCardProps) {
    return (
        <div className="p-4 rounded-lg border bg-card">
            <div className="flex items-center gap-2 mb-3">
                <Zap className="h-4 w-4 text-purple-500" />
                <h4 className="font-semibold">SonarQube Quality</h4>
                <Badge variant="outline" className="ml-auto">
                    {sonar.total_scans} scans
                </Badge>
            </div>

            {/* Main Metrics */}
            <div className="grid grid-cols-2 gap-3 mb-4">
                <MetricItem
                    icon={<Bug className="h-3.5 w-3.5" />}
                    label="Bugs"
                    value={sonar.bugs.sum}
                    avg={sonar.bugs.avg}
                />
                <MetricItem
                    icon={<FileWarning className="h-3.5 w-3.5" />}
                    label="Code Smells"
                    value={sonar.code_smells.sum}
                    avg={sonar.code_smells.avg}
                />
                <MetricItem
                    icon={<AlertTriangle className="h-3.5 w-3.5" />}
                    label="Vulnerabilities"
                    value={sonar.vulnerabilities.sum}
                    avg={sonar.vulnerabilities.avg}
                />
                <MetricItem
                    icon={<Lock className="h-3.5 w-3.5" />}
                    label="Security Hotspots"
                    value={sonar.security_hotspots.sum}
                    avg={sonar.security_hotspots.avg}
                />
            </div>

            {/* Ratings */}
            <div className="flex gap-2 mb-3">
                <RatingBadge label="Reliability" rating={sonar.reliability_rating_avg} />
                <RatingBadge label="Security" rating={sonar.security_rating_avg} />
                <RatingBadge label="Maintainability" rating={sonar.maintainability_rating_avg} />
            </div>

            {/* Complexity & Duplication */}
            <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Avg Complexity</span>
                    <span className="font-medium">{sonar.complexity.avg.toFixed(0)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Avg Duplication</span>
                    <span className="font-medium">{sonar.duplicated_lines_density.avg.toFixed(1)}%</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Avg Lines of Code</span>
                    <span className="font-medium">{sonar.ncloc.avg.toFixed(0)}</span>
                </div>
            </div>

            {/* Quality Gate */}
            <div className="mt-3 pt-3 border-t text-xs text-muted-foreground flex justify-between">
                <span>Quality Gate Passed: {sonar.alert_status_ok_count}</span>
                {sonar.alert_status_error_count > 0 && (
                    <span className="text-red-500">
                        Failed: {sonar.alert_status_error_count}
                    </span>
                )}
            </div>
        </div>
    );
}

function SeverityBadge({
    severity,
    value,
}: {
    severity: "critical" | "high" | "medium" | "low";
    value: number;
}) {
    if (value === 0) {
        return (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <div className={`w-2 h-2 rounded-full ${getSeverityDot(severity)} opacity-30`} />
                <span className="capitalize">{severity}: 0</span>
            </div>
        );
    }

    return (
        <Badge className={`${getSeverityColor(severity)} text-xs`}>
            {severity.charAt(0).toUpperCase()}: {value}
        </Badge>
    );
}

function MetricItem({
    icon,
    label,
    value,
    avg,
}: {
    icon: React.ReactNode;
    label: string;
    value: number;
    avg: number;
}) {
    return (
        <div className="p-2 rounded bg-muted/30">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                {icon}
                {label}
            </div>
            <div className="text-lg font-semibold">{value}</div>
            <div className="text-xs text-muted-foreground">avg: {avg.toFixed(1)}</div>
        </div>
    );
}

function RatingBadge({
    label,
    rating,
}: {
    label: string;
    rating: number | null;
}) {
    return (
        <div className="flex flex-col items-center">
            <span className="text-xs text-muted-foreground mb-1">{label}</span>
            <Badge className={getRatingColor(rating)}>
                {getRatingLabel(rating)}
            </Badge>
        </div>
    );
}
