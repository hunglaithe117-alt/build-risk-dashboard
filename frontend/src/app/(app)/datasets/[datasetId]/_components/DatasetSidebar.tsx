"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import type { DatasetRecord } from "@/types";
import {
    Edit,
    FileSpreadsheet,
    GitBranch,
    HardDrive,
    Layers,
    RefreshCw,
    Settings,
    Trash2,
    Zap,
} from "lucide-react";

interface DatasetSidebarProps {
    dataset: DatasetRecord;
    onEditConfig?: () => void;
    onDelete?: () => void;
    onRefresh?: () => void;
}

function formatFileSize(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function DatasetSidebar({
    dataset,
    onEditConfig,
    onDelete,
    onRefresh,
}: DatasetSidebarProps) {
    const languagesCount = dataset.source_languages?.length || 0;
    const frameworksCount = dataset.test_frameworks?.length || 0;

    // Count unique repos from validation stats
    const reposCount = dataset.validation_stats?.repos_total || 0;

    return (
        <div className="w-80 flex-shrink-0 space-y-4">
            {/* Quick Stats */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Dataset Info</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 text-muted-foreground">
                            <FileSpreadsheet className="h-4 w-4" />
                            Rows
                        </span>
                        <span className="font-medium">{dataset.rows.toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 text-muted-foreground">
                            <Layers className="h-4 w-4" />
                            Columns
                        </span>
                        <span className="font-medium">{dataset.columns?.length || 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 text-muted-foreground">
                            <GitBranch className="h-4 w-4" />
                            Repositories
                        </span>
                        <span className="font-medium">{reposCount}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 text-muted-foreground">
                            <HardDrive className="h-4 w-4" />
                            File Size
                        </span>
                        <span className="font-medium">{formatFileSize(dataset.size_bytes || 0)}</span>
                    </div>
                </CardContent>
            </Card>

            {/* Configuration Summary */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Settings className="h-4 w-4" />
                        Configuration
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                    <div className="space-y-1">
                        <p className="text-muted-foreground text-xs">Column Mapping</p>
                        <div className="flex gap-1 flex-wrap">
                            {dataset.mapped_fields?.build_id ? (
                                <Badge variant="secondary" className="font-mono text-xs">
                                    build: {dataset.mapped_fields.build_id}
                                </Badge>
                            ) : (
                                <span className="text-amber-600 text-xs">Not mapped</span>
                            )}
                        </div>
                        <div className="flex gap-1 flex-wrap">
                            {dataset.mapped_fields?.repo_name ? (
                                <Badge variant="secondary" className="font-mono text-xs">
                                    repo: {dataset.mapped_fields.repo_name}
                                </Badge>
                            ) : null}
                        </div>
                    </div>
                    {(languagesCount > 0 || frameworksCount > 0) && (
                        <div className="space-y-1">
                            <p className="text-muted-foreground text-xs">Stack</p>
                            <div className="flex flex-wrap gap-1">
                                {dataset.source_languages?.slice(0, 3).map((lang) => (
                                    <Badge key={lang} variant="outline" className="text-xs">
                                        {lang}
                                    </Badge>
                                ))}
                                {languagesCount > 3 && (
                                    <Badge variant="outline" className="text-xs">
                                        +{languagesCount - 3}
                                    </Badge>
                                )}
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Quick Actions */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    <Button
                        variant="outline"
                        className="w-full justify-start gap-2"
                        size="sm"
                        onClick={onRefresh}
                    >
                        <RefreshCw className="h-4 w-4" />
                        Refresh Data
                    </Button>
                    <Button
                        variant="ghost"
                        className="w-full justify-start gap-2 text-red-600 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-900/20"
                        size="sm"
                        onClick={onDelete}
                    >
                        <Trash2 className="h-4 w-4" />
                        Delete Dataset
                    </Button>
                </CardContent>
            </Card>

            {/* Enrichment Info */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Zap className="h-4 w-4" />
                        Enrichment
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-xs text-muted-foreground mb-3">
                        Create enriched versions with extracted features from the Enrichment tab.
                    </p>
                    <Button
                        variant="secondary"
                        className="w-full gap-2"
                        size="sm"
                        onClick={onEditConfig}
                    >
                        <Zap className="h-4 w-4" />
                        Go to Enrichment
                    </Button>
                </CardContent>
            </Card>
        </div>
    );
}
