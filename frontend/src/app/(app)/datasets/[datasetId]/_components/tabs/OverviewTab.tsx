"use client";

import { useState } from "react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { DatasetRecord } from "@/types";
import {
    ChevronDown,
    ChevronRight,
    Database,
    GitBranch,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    BarChart3,
    TrendingUp,
    TrendingDown,
    Calendar,
    FileSpreadsheet,
    Layers,
    HardDrive,
    MapPin,
    Github,
    ExternalLink,
    Settings,
} from "lucide-react";

interface OverviewTabProps {
    dataset: DatasetRecord;
    onRefresh: () => void;
}

function formatDate(value?: string | null) {
    if (!value) return "—";
    try {
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(value));
    } catch {
        return value;
    }
}

function formatFileSize(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
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

function ValidationStatCard({
    label,
    value,
    total,
    variant = "default",
}: {
    label: string;
    value: number;
    total?: number;
    variant?: "success" | "warning" | "error" | "default";
}) {
    const colors = {
        success: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-600",
        warning: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-600",
        error: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-600",
        default: "bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 text-slate-600",
    };

    return (
        <div className={`p-4 rounded-lg border ${colors[variant]}`}>
            <p className="text-2xl font-bold">{value.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">
                {label}
                {total !== undefined && ` / ${total.toLocaleString()}`}
            </p>
        </div>
    );
}

export function OverviewTab({ dataset, onRefresh }: OverviewTabProps) {
    const [previewExpanded, setPreviewExpanded] = useState(true);
    const [reposExpanded, setReposExpanded] = useState(true);

    const stats = dataset.stats || { missing_rate: 0, duplicate_rate: 0, build_coverage: 0 };
    const validationStats = dataset.validation_stats;

    // Get unique repos from preview data
    const repoField = dataset.mapped_fields?.repo_name || "";
    const uniqueRepos = Array.from(
        new Set(
            dataset.preview
                ?.map(row => row[repoField] as string)
                .filter(Boolean) || []
        )
    ).slice(0, 10);

    const reposCount = dataset.validation_stats?.repos_total || uniqueRepos.length;
    const languages = dataset.source_languages || [];
    const frameworks = dataset.test_frameworks || [];

    return (
        <div className="space-y-6">
            {/* Dataset Info Card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Database className="h-5 w-5" />
                        Dataset Info
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800">
                            <FileSpreadsheet className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <p className="text-2xl font-bold">{dataset.rows.toLocaleString()}</p>
                                <p className="text-xs text-muted-foreground">Rows</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800">
                            <Layers className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <p className="text-2xl font-bold">{dataset.columns?.length || 0}</p>
                                <p className="text-xs text-muted-foreground">Columns</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800">
                            <GitBranch className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <p className="text-2xl font-bold">{reposCount}</p>
                                <p className="text-xs text-muted-foreground">Repositories</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800">
                            <HardDrive className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <p className="text-2xl font-bold">{formatFileSize(dataset.size_bytes || 0)}</p>
                                <p className="text-xs text-muted-foreground">File Size</p>
                            </div>
                        </div>
                    </div>

                    {/* Column Mapping */}
                    <div className="mt-4 pt-4 border-t">
                        <div className="flex items-center gap-2 mb-3">
                            <MapPin className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm font-medium">Column Mapping</span>
                        </div>
                        <div className="grid gap-2 md:grid-cols-2">
                            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                                <span className="text-sm text-muted-foreground">Build ID</span>
                                <div className="flex items-center gap-2">
                                    {dataset.mapped_fields?.build_id ? (
                                        <>
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            <Badge variant="secondary" className="font-mono text-xs">
                                                {dataset.mapped_fields.build_id}
                                            </Badge>
                                        </>
                                    ) : (
                                        <>
                                            <XCircle className="h-4 w-4 text-amber-500" />
                                            <span className="text-amber-600 text-sm">Not mapped</span>
                                        </>
                                    )}
                                </div>
                            </div>
                            <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                                <span className="text-sm text-muted-foreground">Repo Name</span>
                                <div className="flex items-center gap-2">
                                    {dataset.mapped_fields?.repo_name ? (
                                        <>
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            <Badge variant="secondary" className="font-mono text-xs">
                                                {dataset.mapped_fields.repo_name}
                                            </Badge>
                                        </>
                                    ) : (
                                        <>
                                            <XCircle className="h-4 w-4 text-amber-500" />
                                            <span className="text-amber-600 text-sm">Not mapped</span>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Languages & Frameworks */}
                    {(languages.length > 0 || frameworks.length > 0) && (
                        <div className="mt-4 pt-4 border-t">
                            <div className="flex items-center gap-2 mb-3">
                                <Settings className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm font-medium">Languages & Frameworks</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {languages.map((lang: string) => (
                                    <Badge key={lang} variant="secondary">{lang}</Badge>
                                ))}
                                {frameworks.map((fw: string) => (
                                    <Badge key={fw} variant="outline">{fw}</Badge>
                                ))}
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Data Quality Metrics */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <BarChart3 className="h-5 w-5" />
                        Data Quality
                    </CardTitle>
                    <CardDescription>
                        Quality indicators calculated during upload and validation
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid md:grid-cols-3 gap-4">
                        <QualityMeter
                            label="Missing Rate"
                            value={stats.missing_rate}
                            description="Cells without values in key columns"
                            invertColor={true}
                        />
                        <QualityMeter
                            label="Duplicate Rate"
                            value={stats.duplicate_rate}
                            description="Rows with identical build IDs"
                            invertColor={true}
                        />
                        <QualityMeter
                            label="Build Coverage"
                            value={stats.build_coverage}
                            description="Builds verified in CI provider"
                            invertColor={false}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Validation Statistics */}
            {validationStats && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <GitBranch className="h-5 w-5" />
                            Validation Results
                        </CardTitle>
                        <CardDescription className="flex items-center gap-4">
                            <span>Build verification summary from CI provider</span>
                            {dataset.validation_completed_at && (
                                <span className="flex items-center gap-1 text-xs">
                                    <Calendar className="h-3 w-3" />
                                    {formatDate(dataset.validation_completed_at)}
                                </span>
                            )}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                            <ValidationStatCard
                                label="Total Repos"
                                value={validationStats.repos_total}
                                variant="default"
                            />
                            <ValidationStatCard
                                label="Valid Repos"
                                value={validationStats.repos_valid}
                                variant="success"
                            />
                            <ValidationStatCard
                                label="Builds Found"
                                value={validationStats.builds_found}
                                variant="success"
                            />
                            <ValidationStatCard
                                label="Builds Not Found"
                                value={validationStats.builds_not_found}
                                variant={validationStats.builds_not_found > 0 ? "warning" : "default"}
                            />
                        </div>

                        {validationStats.builds_total > 0 && (
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                                {validationStats.builds_found > validationStats.builds_not_found ? (
                                    <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
                                ) : validationStats.builds_not_found > 0 ? (
                                    <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
                                ) : (
                                    <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                                )}
                                <div className="text-sm">
                                    <span className="font-medium">
                                        {((validationStats.builds_found / validationStats.builds_total) * 100).toFixed(1)}%
                                    </span>
                                    <span className="text-muted-foreground ml-1">
                                        of builds were found and verified in CI provider
                                    </span>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Repositories (Collapsible) */}
            {uniqueRepos.length > 0 && (
                <Card>
                    <CardHeader
                        className="cursor-pointer hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors rounded-t-lg"
                        onClick={() => setReposExpanded(!reposExpanded)}
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <Github className="h-5 w-5" />
                                    Repositories ({uniqueRepos.length})
                                </CardTitle>
                                <CardDescription>
                                    Unique repositories from this dataset
                                </CardDescription>
                            </div>
                            {reposExpanded ? (
                                <ChevronDown className="h-5 w-5 text-muted-foreground" />
                            ) : (
                                <ChevronRight className="h-5 w-5 text-muted-foreground" />
                            )}
                        </div>
                    </CardHeader>
                    {reposExpanded && (
                        <CardContent>
                            <div className="space-y-2">
                                {uniqueRepos.map(repo => (
                                    <div
                                        key={repo}
                                        className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-2 dark:bg-slate-800"
                                    >
                                        <div className="flex items-center gap-3">
                                            <Github className="h-4 w-4 text-muted-foreground" />
                                            <span className="font-mono text-sm">{repo}</span>
                                        </div>
                                        <a
                                            href={`https://github.com/${repo}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-muted-foreground hover:text-foreground"
                                        >
                                            <ExternalLink className="h-4 w-4" />
                                        </a>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    )}
                </Card>
            )}

            {/* Data Preview (Collapsible) */}
            <Card>
                <CardHeader
                    className="cursor-pointer hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors rounded-t-lg"
                    onClick={() => setPreviewExpanded(!previewExpanded)}
                >
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Database className="h-5 w-5" />
                                Data Preview
                            </CardTitle>
                            <CardDescription>
                                Sample data from your dataset ({dataset.rows?.toLocaleString()} total rows)
                            </CardDescription>
                        </div>
                        {previewExpanded ? (
                            <ChevronDown className="h-5 w-5 text-muted-foreground" />
                        ) : (
                            <ChevronRight className="h-5 w-5 text-muted-foreground" />
                        )}
                    </div>
                </CardHeader>
                {previewExpanded && (
                    <CardContent className="p-0">
                        <div className="max-h-80 overflow-auto border-t">
                            <table className="min-w-full text-sm">
                                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        {dataset.columns?.map((col) => {
                                            const isMapped = col === dataset.mapped_fields?.build_id ||
                                                col === dataset.mapped_fields?.repo_name;
                                            return (
                                                <th
                                                    key={col}
                                                    className={`px-4 py-2 text-left font-medium whitespace-nowrap ${isMapped ? "text-blue-600 dark:text-blue-400" : ""
                                                        }`}
                                                >
                                                    {col}
                                                    {isMapped && (
                                                        <Badge variant="outline" className="ml-2 text-[10px] px-1 py-0">
                                                            mapped
                                                        </Badge>
                                                    )}
                                                </th>
                                            );
                                        })}
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {dataset.preview?.slice(0, 5).map((row, idx) => (
                                        <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                                            {dataset.columns?.map((col) => (
                                                <td key={col} className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                                                    {String(row[col] ?? "—").slice(0, 50)}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                )}
            </Card>
        </div>
    );
}
