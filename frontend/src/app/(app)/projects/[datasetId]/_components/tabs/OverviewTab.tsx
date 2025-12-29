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
import { Button } from "@/components/ui/button";
import type { DatasetRecord } from "@/types";
import { api, datasetsApi } from "@/lib/api";
import { toast } from "@/components/ui/use-toast";
import {
    BarChart3,
    TrendingUp,
    TrendingDown,
    FileSpreadsheet,
    Layers,
    HardDrive,
    GitBranch,
    MapPin,
    CheckCircle2,
    XCircle,
    Settings,
    Clock,
    Database,
    GitCommit,
    AlertTriangle,
    Github,
    ExternalLink,
    RefreshCw,
    AlertCircle,
} from "lucide-react";

interface OverviewTabProps {
    dataset: DatasetRecord;
    onRefresh: () => void;
}

interface BuildsStats {
    status_breakdown: Record<string, number>;
    conclusion_breakdown: Record<string, number>;
    builds_per_repo: { repo: string; count: number }[];
    avg_duration_seconds?: number;
    total_builds: number;
    found_builds: number;
}

function formatFileSize(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function QualityMeter({
    label,
    value,
    description,
    invertColor = false,
    icon: Icon,
}: {
    label: string;
    value: number;
    description: string;
    invertColor?: boolean;
    icon?: React.ElementType;
}) {
    const getColor = (val: number, invert: boolean) => {
        if (invert) {
            if (val <= 5) return { bg: "bg-green-500", text: "text-green-600", label: "Excellent" };
            if (val <= 15) return { bg: "bg-amber-500", text: "text-amber-600", label: "Fair" };
            return { bg: "bg-red-500", text: "text-red-600", label: "Poor" };
        } else {
            if (val >= 80) return { bg: "bg-green-500", text: "text-green-600", label: "Excellent" };
            if (val >= 50) return { bg: "bg-amber-500", text: "text-amber-600", label: "Fair" };
            return { bg: "bg-red-500", text: "text-red-600", label: "Poor" };
        }
    };

    const colorInfo = getColor(value, invertColor);
    const IconComponent = Icon || (invertColor ? TrendingDown : TrendingUp);

    return (
        <div className="p-4 rounded-lg border bg-card">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <IconComponent className={`h-4 w-4 ${colorInfo.text}`} />
                    <span className="text-sm font-medium">{label}</span>
                </div>
                <Badge variant="outline" className={colorInfo.text}>
                    {colorInfo.label}
                </Badge>
            </div>
            <div className="flex items-baseline gap-2 mb-2">
                <span className={`text-3xl font-bold ${colorInfo.text}`}>{value.toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden mb-2">
                <div
                    className={`h-full transition-all ${colorInfo.bg}`}
                    style={{ width: `${Math.min(value, 100)}%` }}
                />
            </div>
            <p className="text-xs text-muted-foreground">{description}</p>
        </div>
    );
}

function StatCard({
    icon: Icon,
    label,
    value,
    subValue,
    variant = "default",
}: {
    icon: React.ElementType;
    label: string;
    value: number | string;
    subValue?: string;
    variant?: "default" | "success" | "warning" | "error";
}) {
    const colors = {
        default: "bg-slate-50 dark:bg-slate-800 text-slate-600",
        success: "bg-green-50 dark:bg-green-900/20 text-green-600",
        warning: "bg-amber-50 dark:bg-amber-900/20 text-amber-600",
        error: "bg-red-50 dark:bg-red-900/20 text-red-600",
    };

    return (
        <div className={`p-4 rounded-lg border ${colors[variant]} flex flex-col justify-between`}>
            <div>
                <p className="text-3xl font-bold tracking-tight mb-1">{typeof value === "number" ? value.toLocaleString() : value}</p>
                <p className="text-sm font-medium text-muted-foreground">{label}</p>
            </div>
            {subValue && (
                <div className="mt-4 flex items-center gap-2 text-xs opacity-80">
                    <Icon className="h-3.5 w-3.5" />
                    <span>{subValue}</span>
                </div>
            )}
        </div>
    );
}

export function OverviewTab({ dataset, onRefresh }: OverviewTabProps) {
    const [stats, setStats] = useState<BuildsStats | null>(null);
    const [isRetrying, setIsRetrying] = useState(false);

    const stats_metadata = dataset.stats || { missing_rate: 0, duplicate_rate: 0, build_coverage: 0 };
    const reposCount = dataset.validation_stats?.repos_total || (new Set(dataset.preview?.map(r => r[dataset.mapped_fields?.repo_name || ""]))).size || 0;
    const languages = dataset.source_languages || [];
    const frameworks = dataset.test_frameworks || [];

    const isValidated = dataset.validation_status === "completed";
    const isValidationFailed = dataset.validation_status === "failed";
    const validationStats = dataset.validation_stats;

    // Get unique repos from preview data for manual tab
    const repoField = dataset.mapped_fields?.repo_name || "";
    const uniqueRepos = Array.from(
        new Set(
            dataset.preview
                ?.map(row => row[repoField] as string)
                .filter(Boolean) || []
        )
    );

    const handleRetryValidation = async () => {
        setIsRetrying(true);
        try {
            await datasetsApi.startValidation(dataset.id);
            toast({
                title: "Validation Started",
                description: "Dataset validation has been restarted.",
            });
            onRefresh();
        } catch (err) {
            console.error("Failed to restart validation", err);
            toast({
                title: "Retry Failed",
                description: "Failed to restart validation. Please try again.",
                variant: "destructive",
            });
        } finally {
            setIsRetrying(false);
        }
    };

    useEffect(() => {
        const loadStats = async () => {
            if (!isValidated) return;
            try {
                const res = await api.get<BuildsStats>(`/datasets/${dataset.id}/builds/stats`);
                setStats(res.data);
            } catch (err) {
                console.error("Failed to load build stats", err);
            }
        };
        loadStats();
    }, [dataset.id, isValidated]);

    return (
        <div className="space-y-6">
            {/* key metrics grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardContent className="p-6 flex flex-col items-center text-center gap-2">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-full mb-1">
                            <FileSpreadsheet className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <p className="text-3xl font-bold">{dataset.rows.toLocaleString()}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Rows</p>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-6 flex flex-col items-center text-center gap-2">
                        <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-full mb-1">
                            <Layers className="h-6 w-6 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <p className="text-3xl font-bold">{dataset.columns?.length || 0}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Columns</p>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-6 flex flex-col items-center text-center gap-2">
                        <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-full mb-1">
                            <GitBranch className="h-6 w-6 text-orange-600 dark:text-orange-400" />
                        </div>
                        <div>
                            <p className="text-3xl font-bold">{reposCount}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Repositories</p>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-6 flex flex-col items-center text-center gap-2">
                        <div className="p-2 bg-slate-100 dark:bg-slate-800 rounded-full mb-1">
                            <HardDrive className="h-6 w-6 text-slate-600 dark:text-slate-400" />
                        </div>
                        <div>
                            <p className="text-3xl font-bold">{formatFileSize(dataset.size_bytes || 0)}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Size</p>
                        </div>
                    </CardContent>
                </Card>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
                {/* Column Mapping Status */}
                <Card className="md:col-span-1">
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <MapPin className="h-5 w-5" />
                            Configuration
                        </CardTitle>
                        <CardDescription>
                            Key column mappings
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-3">
                            <div>
                                <p className="text-sm font-medium mb-1.5 text-muted-foreground">Build ID Column</p>
                                <div className="flex items-center gap-2 p-2 rounded-md bg-slate-50 dark:bg-slate-800/50 border">
                                    {dataset.mapped_fields?.build_id ? (
                                        <>
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            <code className="text-xs font-mono">{dataset.mapped_fields.build_id}</code>
                                        </>
                                    ) : (
                                        <>
                                            <XCircle className="h-4 w-4 text-amber-500" />
                                            <span className="text-xs text-amber-600 italic">Not mapped</span>
                                        </>
                                    )}
                                </div>
                            </div>
                            <div>
                                <p className="text-sm font-medium mb-1.5 text-muted-foreground">Repository Name Column</p>
                                <div className="flex items-center gap-2 p-2 rounded-md bg-slate-50 dark:bg-slate-800/50 border">
                                    {dataset.mapped_fields?.repo_name ? (
                                        <>
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            <code className="text-xs font-mono">{dataset.mapped_fields.repo_name}</code>
                                        </>
                                    ) : (
                                        <>
                                            <XCircle className="h-4 w-4 text-amber-500" />
                                            <span className="text-xs text-amber-600 italic">Not mapped</span>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Languages & Frameworks */}
                        {(languages.length > 0 || frameworks.length > 0) && (
                            <div className="pt-4 border-t">
                                <div className="flex items-center gap-2 mb-3">
                                    <Settings className="h-4 w-4 text-muted-foreground" />
                                    <span className="text-sm font-medium">Stack Detection</span>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {languages.map((lang: string) => (
                                        <Badge key={lang} variant="secondary" className="text-xs">{lang}</Badge>
                                    ))}
                                    {frameworks.map((fw: string) => (
                                        <Badge key={fw} variant="outline" className="text-xs">{fw}</Badge>
                                    ))}
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Data Quality Metrics */}
                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <BarChart3 className="h-5 w-5" />
                            Data Quality Scores
                        </CardTitle>
                        <CardDescription>
                            Quality indicators calculated during analysis
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid sm:grid-cols-3 gap-4">
                        <QualityMeter
                            label="Missing Rate"
                            value={stats_metadata.missing_rate}
                            description="Cells without values"
                            invertColor={true}
                        />
                        <QualityMeter
                            label="Duplicate Rate"
                            value={stats_metadata.duplicate_rate}
                            description="Duplicate rows"
                            invertColor={true}
                        />
                        <QualityMeter
                            label="Build Coverage"
                            value={stats_metadata.build_coverage}
                            description="Verified in CI"
                            invertColor={false}
                        />
                    </CardContent>
                </Card>
            </div>

            {/* --- VALIDATION STATUS SECTION --- */}
            <div className="pt-6 border-t">
                <div className="flex items-center gap-2 mb-4">
                    <CheckCircle2 className="h-5 w-5 text-blue-600" />
                    <h3 className="text-lg font-semibold">Validation Statistics</h3>
                </div>

                {isValidationFailed ? (
                    <div className="flex flex-col items-center justify-center py-8 border rounded-lg border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-900/20">
                        <AlertCircle className="h-12 w-12 text-red-500 mb-4" />
                        <h3 className="text-lg font-semibold text-red-700 dark:text-red-400">Validation Failed</h3>
                        {dataset.validation_error && (
                            <p className="text-sm text-red-600 dark:text-red-400 text-center max-w-md mt-2 px-4">
                                {dataset.validation_error}
                            </p>
                        )}
                        <Button
                            variant="outline"
                            className="mt-4 gap-2 border-red-300 text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/40"
                            onClick={handleRetryValidation}
                            disabled={isRetrying}
                        >
                            <RefreshCw className={`h-4 w-4 ${isRetrying ? "animate-spin" : ""}`} />
                            {isRetrying ? "Restarting..." : "Retry Validation"}
                        </Button>
                    </div>
                ) : !isValidated ? (
                    <div className="flex flex-col items-center justify-center py-6 border rounded-lg border-dashed bg-slate-50 dark:bg-slate-900/50">
                        <AlertTriangle className="h-10 w-10 text-amber-500 mb-4" />
                        <h3 className="text-lg font-semibold">Validation Pending</h3>
                        <p className="text-sm text-muted-foreground text-center max-w-sm mt-2">
                            Metrics will appear here once validation is complete.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-6">
                        {/* Consolidated Validation Metrics (Single Row) */}
                        {validationStats && stats && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <StatCard
                                    icon={CheckCircle2}
                                    label="Verified Builds"
                                    value={validationStats.builds_found}
                                    subValue={`${((validationStats.builds_found / validationStats.builds_total) * 100).toFixed(1)}% of total`}
                                    variant="success"
                                />
                                <StatCard
                                    icon={AlertTriangle}
                                    label="Missing Builds"
                                    value={validationStats.builds_not_found}
                                    subValue={validationStats.builds_not_found > 0 ? "Action Required" : "All Clear"}
                                    variant={validationStats.builds_not_found > 0 ? "warning" : "default"}
                                />
                                <StatCard
                                    icon={Clock}
                                    label="Avg Duration"
                                    value={stats.avg_duration_seconds ? formatDuration(stats.avg_duration_seconds) : "N/A"}
                                    subValue="Per Build"
                                    variant="default"
                                />
                                <StatCard
                                    icon={Github}
                                    label="Valid Repos"
                                    value={validationStats.repos_valid}
                                    subValue={`of ${validationStats.repos_total} total`}
                                    variant="default"
                                />
                            </div>
                        )}

                        {/* Charts */}
                        <div className="grid md:grid-cols-2 gap-6">
                            {/* Conclusion Breakdown */}
                            {stats && Object.keys(stats.conclusion_breakdown).length > 0 && (
                                <Card>
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                                            <GitCommit className="h-4 w-4" />
                                            Build Conclusions
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(stats.conclusion_breakdown).map(([conclusion, count]) => (
                                                <div key={conclusion} className="flex items-center gap-1.5 px-3 py-1.5 border rounded-md text-sm">
                                                    <Badge variant={conclusion === "success" ? "default" : "secondary"}
                                                        className={conclusion === "success" ? "bg-green-500 hover:bg-green-600" : conclusion === "failure" ? "bg-red-500 hover:bg-red-600" : "bg-slate-200 text-slate-700"}>
                                                        {conclusion}
                                                    </Badge>
                                                    <span className="font-mono">{count}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Top Repos */}
                            {stats && stats.builds_per_repo.length > 0 && (
                                <Card>
                                    <CardHeader className="pb-2">
                                        <CardTitle className=" text-sm font-medium flex items-center gap-2">
                                            <GitBranch className="h-4 w-4" />
                                            Top Repositories by Volume
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-3">
                                            {stats.builds_per_repo.slice(0, 5).map((item) => (
                                                <div key={item.repo} className="flex items-center justify-between text-sm">
                                                    <span className="font-mono truncate max-w-[70%] text-muted-foreground">{item.repo}</span>
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-20 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(item.count / stats.builds_per_repo[0].count) * 100}%` }} />
                                                        </div>
                                                        <span className="font-medium w-8 text-right">{item.count}</span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* --- REPOSITORIES & SOURCE PREVIEW --- */}
            <div className="pt-6 border-t grid md:grid-cols-1 gap-6">
                {/* Repositories */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Github className="h-5 w-5" />
                            Active Repositories
                        </CardTitle>
                        <CardDescription>
                            All repositories extracted from the source data ({uniqueRepos.length} total)
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {uniqueRepos.length > 0 ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {uniqueRepos.map((repo) => (
                                    <div
                                        key={repo}
                                        className="flex items-center justify-between rounded-lg border p-3 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                                    >
                                        <div className="flex items-center gap-3 overflow-hidden">
                                            <Github className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                            <span className="font-mono text-sm truncate" title={repo}>{repo}</span>
                                        </div>
                                        <a
                                            href={`https://github.com/${repo}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="ml-2 text-muted-foreground hover:text-foreground"
                                        >
                                            <ExternalLink className="h-3 w-3" />
                                        </a>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="text-center py-12 text-muted-foreground">
                                No repositories found. Please check your data mapping.
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Source Preview */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5" />
                            Raw Data Preview
                        </CardTitle>
                        <CardDescription>
                            Previewing first 10 rows of uploaded CSV. Total rows: {dataset.rows?.toLocaleString()}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="overflow-x-auto border-t">
                            <table className="min-w-full text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-800/50">
                                    <tr>
                                        {dataset.columns?.map((col) => {
                                            const isMapped = col === dataset.mapped_fields?.build_id ||
                                                col === dataset.mapped_fields?.repo_name;
                                            return (
                                                <th
                                                    key={col}
                                                    className={`px-4 py-3 text-left font-medium whitespace-nowrap border-b ${isMapped ? "text-blue-600 dark:text-blue-400" : "text-muted-foreground"
                                                        }`}
                                                >
                                                    <div className="flex items-center gap-2">
                                                        {col}
                                                        {isMapped && (
                                                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-5 border-blue-200 text-blue-600">
                                                                Mapped
                                                            </Badge>
                                                        )}
                                                    </div>
                                                </th>
                                            );
                                        })}
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {dataset.preview?.slice(0, 10).map((row, idx) => (
                                        <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                                            {dataset.columns?.map((col) => (
                                                <td key={col} className="px-4 py-2.5 text-muted-foreground whitespace-nowrap max-w-[300px] truncate">
                                                    {String(row[col] ?? "—")}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
