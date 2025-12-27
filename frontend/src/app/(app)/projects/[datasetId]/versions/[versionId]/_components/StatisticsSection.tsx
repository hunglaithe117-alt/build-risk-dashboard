"use client";

import { useEffect, useState, useCallback } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import {
    AlertCircle,
    BarChart3,
    CheckCircle2,
    Clock,
    Database,
    Loader2,
    RefreshCw,
    TrendingUp,
    XCircle,
    Layers,
} from "lucide-react";
import {
    statisticsApi,
    type VersionStatisticsResponse,
    type FeatureCompleteness,
    type BuildStatusBreakdown,
} from "@/lib/api";
import { FeatureDistributionChart } from "./FeatureDistributionChart";
import { CorrelationMatrixChart } from "./CorrelationMatrixChart";

interface StatisticsTabProps {
    datasetId: string;
    versionId: string;
    versionStatus: string;
}

// Color helper for quality scores
function getScoreColor(score: number): string {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
}

function getScoreBgColor(score: number): string {
    if (score >= 80) return "bg-green-100 dark:bg-green-900/30";
    if (score >= 60) return "bg-yellow-100 dark:bg-yellow-900/30";
    return "bg-red-100 dark:bg-red-900/30";
}

function getStatusColor(status: string): string {
    switch (status) {
        case "completed":
        case "success":
            return "bg-green-500";
        case "failed":
        case "error":
            return "bg-red-500";
        case "partial":
            return "bg-yellow-500";
        case "pending":
            return "bg-gray-400";
        default:
            return "bg-blue-500";
    }
}

// Format duration in human readable format
function formatDuration(seconds: number | null | undefined): string {
    if (!seconds) return "-";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.round((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

export function StatisticsSection({ datasetId, versionId, versionStatus }: StatisticsTabProps) {
    const [statisticsData, setStatisticsData] = useState<VersionStatisticsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchStatistics = useCallback(async () => {
        if (!versionId) return;

        setIsLoading(true);
        setError(null);

        try {
            const responseData = await statisticsApi.getVersionStatistics(datasetId, versionId);
            setStatisticsData(responseData);
        } catch (err) {
            console.error("Failed to fetch statistics:", err);
            setError("Failed to load statistics");
        } finally {
            setIsLoading(false);
        }
    }, [datasetId, versionId]);

    useEffect(() => {
        fetchStatistics();
    }, [fetchStatistics]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
                <AlertCircle className="h-12 w-12 text-destructive" />
                <p className="text-muted-foreground">{error}</p>
                <Button variant="outline" onClick={fetchStatistics}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Retry
                </Button>
            </div>
        );
    }

    if (!statisticsData) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
                <BarChart3 className="h-12 w-12 text-muted-foreground" />
                <p className="text-muted-foreground">No statistics available</p>
            </div>
        );
    }

    const { statistics, build_status_breakdown, feature_completeness } = statisticsData;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold">Version Statistics</h2>
                    <p className="text-sm text-muted-foreground">
                        {statisticsData.version_name} - {versionStatus}
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchStatistics}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Refresh
                </Button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* Total Builds */}
                <SummaryCard
                    icon={Database}
                    label="Total Builds"
                    value={statistics.total_builds}
                    variant="default"
                />

                {/* Enriched Builds */}
                <SummaryCard
                    icon={CheckCircle2}
                    label="Enriched"
                    value={statistics.enriched_builds}
                    subValue={`${statistics.enrichment_rate.toFixed(1)}%`}
                    variant="success"
                />

                {/* Failed Builds */}
                <SummaryCard
                    icon={XCircle}
                    label="Failed"
                    value={statistics.failed_builds}
                    variant={statistics.failed_builds > 0 ? "error" : "default"}
                />

                {/* Processing Time */}
                <SummaryCard
                    icon={Clock}
                    label="Duration"
                    value={formatDuration(statistics.processing_duration_seconds)}
                    variant="default"
                />
            </div>

            {/* Build Status Breakdown + Feature Stats */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Build Status Breakdown */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base flex items-center gap-2">
                            <BarChart3 className="h-4 w-4" />
                            Build Status Breakdown
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <BuildStatusChart breakdowns={build_status_breakdown} />
                    </CardContent>
                </Card>

                {/* Feature Extraction Stats */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base flex items-center gap-2">
                            <Layers className="h-4 w-4" />
                            Feature Extraction
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <p className="text-2xl font-bold">
                                    {statistics.total_features_selected}
                                </p>
                                <p className="text-sm text-muted-foreground">
                                    Features Selected
                                </p>
                            </div>
                            <div>
                                <p className="text-2xl font-bold">
                                    {statistics.avg_features_per_build.toFixed(1)}
                                </p>
                                <p className="text-sm text-muted-foreground">
                                    Avg per Build
                                </p>
                            </div>
                        </div>
                        <div>
                            <p className="text-lg font-semibold">
                                {statistics.total_feature_values_extracted.toLocaleString()}
                            </p>
                            <p className="text-sm text-muted-foreground">
                                Total Values Extracted
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Feature Analysis Section */}
            <div className="space-y-4">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Layers className="h-5 w-5" />
                    Feature Analysis
                </h3>

                <div className="flex flex-col gap-6">
                    {/* Feature Distributions */}
                    <FeatureDistributionChart
                        datasetId={datasetId}
                        versionId={versionId}
                        availableFeatures={feature_completeness.map(f => f.feature_name)}
                    />

                    {/* Correlation Matrix */}
                    <CorrelationMatrixChart
                        datasetId={datasetId}
                        versionId={versionId}
                    />
                </div>
            </div>

            {/* Feature Completeness Chart */}
            {feature_completeness.length > 0 && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">Feature Completeness</CardTitle>
                        <CardDescription>
                            Sorted by completeness (lowest first)
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <FeatureCompletenessChart features={feature_completeness} />
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

// =============================================================================
// Sub-components
// =============================================================================

interface SummaryCardProps {
    icon: React.ElementType;
    label: string;
    value: string | number;
    subValue?: string;
    variant?: "default" | "success" | "warning" | "error";
}

function SummaryCard({
    icon: Icon,
    label,
    value,
    subValue,
    variant = "default",
}: SummaryCardProps) {
    const variantStyles = {
        default: "bg-muted/50",
        success: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
        warning: "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800",
        error: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
    };

    const iconStyles = {
        default: "text-muted-foreground",
        success: "text-green-600",
        warning: "text-yellow-600",
        error: "text-red-600",
    };

    return (
        <Card className={variantStyles[variant]}>
            <CardContent className="pt-4">
                <div className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 ${iconStyles[variant]}`} />
                    <span className="text-sm text-muted-foreground">{label}</span>
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-2xl font-bold">{value}</span>
                    {subValue && (
                        <span className="text-sm text-muted-foreground">({subValue})</span>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

interface QualityScoreGaugeProps {
    score: number;
}

function QualityScoreGauge({ score }: QualityScoreGaugeProps) {
    const roundedScore = Math.round(score);
    const circumference = 2 * Math.PI * 40; // radius = 40
    const strokeDashoffset = circumference - (score / 100) * circumference;

    const getGaugeColor = (scoreValue: number): string => {
        if (scoreValue >= 80) return "stroke-green-500";
        if (scoreValue >= 60) return "stroke-yellow-500";
        return "stroke-red-500";
    };

    return (
        <div className="flex flex-col items-center justify-center">
            <div className="relative w-24 h-24">
                <svg className="w-24 h-24 transform -rotate-90" viewBox="0 0 100 100">
                    {/* Background circle */}
                    <circle
                        cx="50"
                        cy="50"
                        r="40"
                        fill="none"
                        strokeWidth="8"
                        className="stroke-muted"
                    />
                    {/* Progress circle */}
                    <circle
                        cx="50"
                        cy="50"
                        r="40"
                        fill="none"
                        strokeWidth="8"
                        strokeLinecap="round"
                        className={getGaugeColor(score)}
                        style={{
                            strokeDasharray: circumference,
                            strokeDashoffset,
                            transition: "stroke-dashoffset 0.5s ease-in-out",
                        }}
                    />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                    <span className={`text-xl font-bold ${getScoreColor(score)}`}>
                        {roundedScore}
                    </span>
                </div>
            </div>
            <p className="text-sm text-muted-foreground mt-2">Overall Score</p>
        </div>
    );
}

interface ScoreBreakdownItemProps {
    label: string;
    score: number | null | undefined;
    description: string;
}

function ScoreBreakdownItem({ label, score, description }: ScoreBreakdownItemProps) {
    const displayScore = score ?? 0;

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        className={`p-3 rounded-lg ${getScoreBgColor(displayScore)} cursor-help`}
                    >
                        <p className="text-sm font-medium">{label}</p>
                        <p className={`text-2xl font-bold ${getScoreColor(displayScore)}`}>
                            {displayScore.toFixed(1)}%
                        </p>
                    </div>
                </TooltipTrigger>
                <TooltipContent>
                    <p>{description}</p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

interface BuildStatusChartProps {
    breakdowns: BuildStatusBreakdown[];
}

function BuildStatusChart({ breakdowns }: BuildStatusChartProps) {
    if (!breakdowns || breakdowns.length === 0) {
        return (
            <p className="text-sm text-muted-foreground text-center py-4">
                No status data available
            </p>
        );
    }

    const totalBuilds = breakdowns.reduce((sum, breakdown) => sum + breakdown.count, 0);

    return (
        <div className="space-y-3">
            {/* Bar visualization */}
            <div className="flex h-4 rounded-full overflow-hidden bg-muted">
                {breakdowns.map((breakdown, index) => (
                    <div
                        key={breakdown.status}
                        className={getStatusColor(breakdown.status)}
                        style={{ width: `${breakdown.percentage}%` }}
                        title={`${breakdown.status}: ${breakdown.count} (${breakdown.percentage}%)`}
                    />
                ))}
            </div>

            {/* Legend */}
            <div className="grid grid-cols-2 gap-2">
                {breakdowns.map((breakdown) => (
                    <div key={breakdown.status} className="flex items-center gap-2">
                        <div
                            className={`w-3 h-3 rounded-full ${getStatusColor(breakdown.status)}`}
                        />
                        <span className="text-sm capitalize">{breakdown.status}</span>
                        <Badge variant="secondary" className="ml-auto">
                            {breakdown.count}
                        </Badge>
                    </div>
                ))}
            </div>
        </div>
    );
}

interface FeatureCompletenessChartProps {
    features: FeatureCompleteness[];
}

function FeatureCompletenessChart({ features }: FeatureCompletenessChartProps) {
    // Show all features
    const displayFeatures = features;

    const getCompletionColor = (percentage: number): string => {
        if (percentage >= 80) return "bg-green-500";
        if (percentage >= 50) return "bg-yellow-500";
        return "bg-red-500";
    };

    return (
        <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
            {displayFeatures.map((feature) => (
                <div key={feature.feature_name} className="flex items-center gap-3">
                    <div className="w-32 truncate text-sm" title={feature.feature_name}>
                        {feature.feature_name}
                    </div>
                    <div className="flex-1">
                        <Progress
                            value={feature.completeness_pct}
                            className="h-2"
                        />
                    </div>
                    <div className="w-16 text-right text-sm">
                        <span className={getScoreColor(feature.completeness_pct)}>
                            {feature.completeness_pct.toFixed(0)}%
                        </span>
                    </div>
                    <Badge variant="outline" className="w-16 justify-center text-xs">
                        {feature.data_type}
                    </Badge>
                </div>
            ))}
        </div>
    );
}
