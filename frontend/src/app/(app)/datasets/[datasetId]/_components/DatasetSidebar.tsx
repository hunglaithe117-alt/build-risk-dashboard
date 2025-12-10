"use client";

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
import type { DatasetRecord, EnrichmentJob } from "@/types";
import {
    CheckCircle2,
    Clock,
    Download,
    Edit,
    FileSpreadsheet,
    Layers,
    Loader2,
    Play,
    Settings,
    Trash2,
    Zap,
} from "lucide-react";

interface DatasetSidebarProps {
    dataset: DatasetRecord;
    enrichmentStatus?: EnrichmentJob | null;
    onStartEnrichment?: () => void;
    onDownload?: () => void;
    onEditConfig?: () => void;
    onDelete?: () => void;
    isEnrichmentLoading?: boolean;
}

export function DatasetSidebar({
    dataset,
    enrichmentStatus,
    onStartEnrichment,
    onDownload,
    onEditConfig,
    onDelete,
    isEnrichmentLoading,
}: DatasetSidebarProps) {
    const hasMapping = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );
    const featuresCount = dataset.selected_features?.length || 0;
    const sonarFeatures = dataset.selected_features?.filter(f => f.startsWith("sonar_")).length || 0;
    const regularFeatures = featuresCount - sonarFeatures;

    // Count unique repos from preview data
    const uniqueRepos = new Set(
        dataset.preview?.map(row => row[dataset.mapped_fields?.repo_name || ""] as string).filter(Boolean)
    ).size;

    const isRunning = enrichmentStatus?.status === "running";
    const isCompleted = enrichmentStatus?.status === "completed";

    return (
        <div className="w-80 flex-shrink-0 space-y-4">
            {/* Quick Stats */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Quick Stats</CardTitle>
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
                            <Zap className="h-4 w-4" />
                            Features
                        </span>
                        <span className="font-medium">{featuresCount}</span>
                    </div>
                    {uniqueRepos > 0 && (
                        <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-2 text-muted-foreground">
                                <Settings className="h-4 w-4" />
                                Repositories
                            </span>
                            <span className="font-medium">{uniqueRepos}</span>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Enrichment Status */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Enrichment Status</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    {isRunning ? (
                        <>
                            <div className="flex items-center gap-2">
                                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                                <span className="text-sm font-medium text-blue-600">Running</span>
                            </div>
                            <Progress value={enrichmentStatus?.progress_percent || 0} className="h-2" />
                            <p className="text-xs text-muted-foreground">
                                {enrichmentStatus?.processed_rows?.toLocaleString() || 0} / {enrichmentStatus?.total_rows?.toLocaleString() || 0} rows
                            </p>
                        </>
                    ) : isCompleted ? (
                        <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                            <span className="text-sm font-medium text-green-600">Completed</span>
                        </div>
                    ) : enrichmentStatus?.status === "failed" ? (
                        <div className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-red-500" />
                            <span className="text-sm font-medium text-red-600">Failed</span>
                        </div>
                    ) : (
                        <div className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">Not started</span>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Quick Actions */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Quick Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    <Button
                        className="w-full justify-start gap-2"
                        size="sm"
                        onClick={onStartEnrichment}
                        disabled={!hasMapping || featuresCount === 0 || isRunning || isEnrichmentLoading}
                    >
                        {isEnrichmentLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4" />
                        )}
                        Start Enrichment
                    </Button>
                    <Button
                        variant="outline"
                        className="w-full justify-start gap-2"
                        size="sm"
                        onClick={onDownload}
                    >
                        <Download className="h-4 w-4" />
                        Download CSV
                    </Button>
                    <Button
                        variant="outline"
                        className="w-full justify-start gap-2"
                        size="sm"
                        onClick={onEditConfig}
                    >
                        <Edit className="h-4 w-4" />
                        Edit Configuration
                    </Button>
                    <Button
                        variant="ghost"
                        className="w-full justify-start gap-2 text-red-600 hover:bg-red-50 hover:text-red-700"
                        size="sm"
                        onClick={onDelete}
                    >
                        <Trash2 className="h-4 w-4" />
                        Delete Dataset
                    </Button>
                </CardContent>
            </Card>

            {/* Configuration Summary */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">Configuration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                    <div className="space-y-1">
                        <p className="text-muted-foreground">Build ID</p>
                        {dataset.mapped_fields?.build_id ? (
                            <Badge variant="secondary" className="font-mono text-xs">
                                {dataset.mapped_fields.build_id}
                            </Badge>
                        ) : (
                            <span className="text-amber-600 text-xs">Not mapped</span>
                        )}
                    </div>
                    <div className="space-y-1">
                        <p className="text-muted-foreground">Repo Name</p>
                        {dataset.mapped_fields?.repo_name ? (
                            <Badge variant="secondary" className="font-mono text-xs">
                                {dataset.mapped_fields.repo_name}
                            </Badge>
                        ) : (
                            <span className="text-amber-600 text-xs">Not mapped</span>
                        )}
                    </div>
                    <div className="space-y-1">
                        <p className="text-muted-foreground">Features</p>
                        <div className="flex flex-wrap gap-1">
                            <Badge variant="outline" className="text-xs">
                                {regularFeatures} regular
                            </Badge>
                            {sonarFeatures > 0 && (
                                <Badge variant="outline" className="text-xs">
                                    {sonarFeatures} sonar
                                </Badge>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
