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
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    AlertCircle,
    BarChart3,
    CheckCircle,
    ChevronDown,
    ChevronUp,
    Layers,
    Loader2,
    RefreshCw,
    TrendingUp,
    AlertTriangle,
    Info,
} from "lucide-react";
import {
    statisticsApi,
    qualityApi,
    type VersionStatisticsResponse,
    type FeatureCompleteness,
    type BuildStatusBreakdown,
    type QualityReport,
    type QualityIssue,
} from "@/lib/api";
import { FeatureDistributionChart } from "./FeatureDistributionChart";
import { CorrelationMatrixChart } from "./CorrelationMatrixChart";
import { FeatureDistributionCarousel } from "./FeatureDistributionCarousel";

interface AnalysisSectionProps {
    datasetId: string;
    versionId: string;
    versionStatus: string;
}

// Color helpers
function getScoreColor(score: number): string {
    if (score >= 80) return "text-green-600";
    if (score >= 60) return "text-yellow-600";
    return "text-red-600";
}

function getScoreBadge(score: number): string {
    if (score >= 80) return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
    if (score >= 60) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400";
    return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400";
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

export function AnalysisSection({ datasetId, versionId, versionStatus }: AnalysisSectionProps) {
    const [statistics, setStatistics] = useState<VersionStatisticsResponse | null>(null);
    const [qualityReport, setQualityReport] = useState<QualityReport | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isEvaluating, setIsEvaluating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Section expansions
    const [isFeatureAnalysisOpen, setIsFeatureAnalysisOpen] = useState(true);
    const [isCompletenessOpen, setIsCompletenessOpen] = useState(false);
    const [isIssuesOpen, setIsIssuesOpen] = useState(true);

    const fetchData = useCallback(async () => {
        if (!versionId) return;

        setIsLoading(true);
        setError(null);

        try {
            // Fetch statistics
            const statsData = await statisticsApi.getVersionStatistics(datasetId, versionId);
            setStatistics(statsData);

            // Fetch quality report if version completed
            if (versionStatus === "completed") {
                try {
                    const qualityData = await qualityApi.getReport(datasetId, versionId);
                    if (!("available" in qualityData) || qualityData.available !== false) {
                        setQualityReport(qualityData as QualityReport);
                    }
                } catch {
                    // Quality report not available yet
                }
            }
        } catch (err) {
            console.error("Failed to fetch analysis data:", err);
            setError("Failed to load analysis data");
        } finally {
            setIsLoading(false);
        }
    }, [datasetId, versionId, versionStatus]);

    const handleEvaluate = async () => {
        setIsEvaluating(true);
        try {
            await qualityApi.evaluate(datasetId, versionId);
            await fetchData();
        } catch (err) {
            console.error("Quality evaluation failed:", err);
        } finally {
            setIsEvaluating(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !statistics) {
        return (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
                <AlertCircle className="h-12 w-12 text-destructive" />
                <p className="text-muted-foreground">{error || "No data available"}</p>
                <Button variant="outline" onClick={fetchData}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Retry
                </Button>
            </div>
        );
    }

    const { statistics: stats, build_status_breakdown, feature_completeness } = statistics;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <BarChart3 className="h-5 w-5" />
                        Analysis
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        Quality metrics and statistical analysis
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchData}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Refresh
                </Button>
            </div>

            {/* Quality Scores + Build Status Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Quality Scores */}
                <Card>
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-base flex items-center gap-2">
                                <TrendingUp className="h-4 w-4" />
                                Quality Scores
                            </CardTitle>
                            {qualityReport && (
                                <Badge className={`text-sm ${getScoreBadge(qualityReport.quality_score)}`}>
                                    {qualityReport.quality_score.toFixed(1)}%
                                </Badge>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent>
                        {qualityReport ? (
                            <div className="grid grid-cols-2 gap-3">
                                <ScoreItem label="Completeness" score={qualityReport.completeness_score} weight={40} />
                                <ScoreItem label="Validity" score={qualityReport.validity_score} weight={30} />
                                <ScoreItem label="Consistency" score={qualityReport.consistency_score} weight={20} />
                                <ScoreItem label="Coverage" score={qualityReport.coverage_score} weight={10} />
                            </div>
                        ) : versionStatus === "completed" ? (
                            <div className="text-center py-4">
                                <p className="text-sm text-muted-foreground mb-3">No quality report available</p>
                                <Button size="sm" onClick={handleEvaluate} disabled={isEvaluating}>
                                    {isEvaluating ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Evaluating...
                                        </>
                                    ) : (
                                        "Run Evaluation"
                                    )}
                                </Button>
                            </div>
                        ) : (
                            <p className="text-sm text-muted-foreground text-center py-4">
                                Available after enrichment completes
                            </p>
                        )}
                    </CardContent>
                </Card>

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
                        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                            <div>
                                <p className="text-2xl font-bold">{stats.total_builds}</p>
                                <p className="text-xs text-muted-foreground">Total</p>
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-green-600">{stats.enriched_builds}</p>
                                <p className="text-xs text-muted-foreground">Enriched</p>
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-red-600">{stats.failed_builds}</p>
                                <p className="text-xs text-muted-foreground">Failed</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Feature Analysis - Collapsible */}
            <Collapsible open={isFeatureAnalysisOpen} onOpenChange={setIsFeatureAnalysisOpen}>
                <Card>
                    <CollapsibleTrigger asChild>
                        <CardHeader className="cursor-pointer hover:bg-muted/50">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Layers className="h-4 w-4" />
                                    Feature Analysis
                                </CardTitle>
                                {isFeatureAnalysisOpen ? (
                                    <ChevronUp className="h-4 w-4" />
                                ) : (
                                    <ChevronDown className="h-4 w-4" />
                                )}
                            </div>
                            <CardDescription>
                                Distribution and correlation of extracted features
                            </CardDescription>
                        </CardHeader>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                        <CardContent className="pt-0 space-y-4">
                            {/* Horizontal Carousel with Lazy Loading */}
                            <FeatureDistributionCarousel
                                datasetId={datasetId}
                                versionId={versionId}
                                features={feature_completeness.map(f => f.feature_name)}
                            />

                            {/* Detail Charts Grid */}
                            <div className="flex flex-col gap-6">
                                <FeatureDistributionChart
                                    datasetId={datasetId}
                                    versionId={versionId}
                                    availableFeatures={feature_completeness.map(f => f.feature_name)}
                                />
                                <CorrelationMatrixChart
                                    datasetId={datasetId}
                                    versionId={versionId}
                                />
                            </div>
                        </CardContent>
                    </CollapsibleContent>
                </Card>
            </Collapsible>

            {/* Feature Completeness - Collapsible */}
            {feature_completeness.length > 0 && (
                <Collapsible open={isCompletenessOpen} onOpenChange={setIsCompletenessOpen}>
                    <Card>
                        <CollapsibleTrigger asChild>
                            <CardHeader className="cursor-pointer hover:bg-muted/50">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <CardTitle className="text-base">Feature Completeness</CardTitle>
                                        <CardDescription>
                                            {feature_completeness.length} features • Sorted by completeness
                                        </CardDescription>
                                    </div>
                                    {isCompletenessOpen ? (
                                        <ChevronUp className="h-4 w-4" />
                                    ) : (
                                        <ChevronDown className="h-4 w-4" />
                                    )}
                                </div>
                            </CardHeader>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                            <CardContent className="pt-0">
                                <FeatureCompletenessTable features={feature_completeness} />
                            </CardContent>
                        </CollapsibleContent>
                    </Card>
                </Collapsible>
            )}

            {/* Issues & Recommendations - Collapsible */}
            {qualityReport && (
                <Collapsible open={isIssuesOpen} onOpenChange={setIsIssuesOpen}>
                    <Card>
                        <CollapsibleTrigger asChild>
                            <CardHeader className="cursor-pointer hover:bg-muted/50">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <AlertTriangle className="h-4 w-4" />
                                        <CardTitle className="text-base">Issues & Recommendations</CardTitle>
                                        {qualityReport.issues && qualityReport.issues.length > 0 && (
                                            <Badge variant="destructive">{qualityReport.issues.length}</Badge>
                                        )}
                                    </div>
                                    {isIssuesOpen ? (
                                        <ChevronUp className="h-4 w-4" />
                                    ) : (
                                        <ChevronDown className="h-4 w-4" />
                                    )}
                                </div>
                            </CardHeader>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                            <CardContent className="pt-0">
                                {qualityReport.issues && qualityReport.issues.length > 0 ? (
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {qualityReport.issues.map((issue, idx) => (
                                            <IssueRow key={idx} issue={issue} />
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-center py-4">
                                        <CheckCircle className="h-8 w-8 mx-auto text-green-500 mb-2" />
                                        <p className="text-sm text-muted-foreground">No issues detected</p>
                                    </div>
                                )}
                            </CardContent>
                        </CollapsibleContent>
                    </Card>
                </Collapsible>
            )}
        </div>
    );
}

// =============================================================================
// Sub-components
// =============================================================================

interface ScoreItemProps {
    label: string;
    score: number;
    weight: number;
}

function ScoreItem({ label, score, weight }: ScoreItemProps) {
    return (
        <div className="p-2 rounded-lg bg-muted/30">
            <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted-foreground">{label} ({weight}%)</span>
                <span className={`text-sm font-semibold ${getScoreColor(score)}`}>
                    {score.toFixed(0)}%
                </span>
            </div>
            <Progress value={score} className="h-1.5" />
        </div>
    );
}

interface BuildStatusChartProps {
    breakdowns: BuildStatusBreakdown[];
}

function BuildStatusChart({ breakdowns }: BuildStatusChartProps) {
    if (!breakdowns || breakdowns.length === 0) {
        return <p className="text-sm text-muted-foreground text-center py-2">No data</p>;
    }

    return (
        <div className="space-y-2">
            <div className="flex h-4 rounded-full overflow-hidden bg-muted">
                {breakdowns.map((b) => (
                    <div
                        key={b.status}
                        className={getStatusColor(b.status)}
                        style={{ width: `${b.percentage}%` }}
                        title={`${b.status}: ${b.count}`}
                    />
                ))}
            </div>
            <div className="flex flex-wrap gap-3 text-xs">
                {breakdowns.map((b) => (
                    <div key={b.status} className="flex items-center gap-1">
                        <div className={`w-2 h-2 rounded-full ${getStatusColor(b.status)}`} />
                        <span className="capitalize">{b.status}</span>
                        <Badge variant="secondary" className="h-5">{b.count}</Badge>
                    </div>
                ))}
            </div>
        </div>
    );
}

interface FeatureCompletenessTableProps {
    features: FeatureCompleteness[];
}

function FeatureCompletenessTable({ features }: FeatureCompletenessTableProps) {
    return (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-2">
            {features.map((feature) => (
                <div key={feature.feature_name} className="flex items-center gap-3">
                    <div className="w-40 truncate text-sm font-mono" title={feature.feature_name}>
                        {feature.feature_name}
                    </div>
                    <div className="flex-1">
                        <Progress value={feature.completeness_pct} className="h-2" />
                    </div>
                    <span className={`w-12 text-right text-sm ${getScoreColor(feature.completeness_pct)}`}>
                        {feature.completeness_pct.toFixed(0)}%
                    </span>
                    <Badge variant="outline" className="w-16 justify-center text-xs">
                        {feature.data_type}
                    </Badge>
                </div>
            ))}
        </div>
    );
}

function IssueRow({ issue }: { issue: QualityIssue }) {
    const Icon = issue.severity === "error" ? AlertCircle :
        issue.severity === "warning" ? AlertTriangle : Info;
    const colorClass = issue.severity === "error" ? "text-red-500" :
        issue.severity === "warning" ? "text-yellow-500" : "text-blue-500";

    return (
        <div className="flex items-start gap-2 py-1.5 border-b last:border-0">
            <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${colorClass}`} />
            <div className="flex-1 min-w-0">
                <p className="text-sm">{issue.message}</p>
                {issue.feature_name && (
                    <p className="text-xs text-muted-foreground font-mono">{issue.feature_name}</p>
                )}
            </div>
        </div>
    );
}
