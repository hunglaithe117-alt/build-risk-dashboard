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
import { Progress } from "@/components/ui/progress";
import { enrichmentApi } from "@/lib/api";
import type { DatasetRecord, EnrichmentJob } from "@/types";
import {
    AlertCircle,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock,
    GitBranch,
    FileText,
    Github,
    Loader2,
    Play,
    RefreshCw,
    RotateCcw,
    Shield,
    XCircle,
    Zap,
} from "lucide-react";

import { EnrichmentPanel } from "../../../_components/EnrichmentPanel";

interface EnrichmentTabProps {
    datasetId: string;
    dataset: DatasetRecord;
    onEnrichmentStatusChange?: (status: EnrichmentJob | null) => void;
}

interface EnrichmentBuild {
    id: string;
    build_id: string;
    repo_name: string;
    commit_sha: string;
    extraction_status: "pending" | "running" | "completed" | "failed";
    features_count: number;
    error_message?: string;
    created_at: string;
    updated_at: string;
}

type FeatureCategory = "git" | "github" | "build_log" | "sonar" | "trivy" | "repo" | "other";

const CATEGORY_CONFIG: Record<FeatureCategory, { label: string; icon: React.ElementType; color: string }> = {
    git: { label: "Git Features", icon: GitBranch, color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
    github: { label: "GitHub Features", icon: Github, color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" },
    build_log: { label: "Build Log Features", icon: FileText, color: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" },
    sonar: { label: "SonarQube Metrics", icon: Shield, color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" },
    trivy: { label: "Trivy Security", icon: Shield, color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" },
    repo: { label: "Repository Features", icon: GitBranch, color: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    other: { label: "Other Features", icon: Zap, color: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
};

function categorizeFeature(name: string): FeatureCategory {
    if (name.startsWith("git_")) return "git";
    if (name.startsWith("gh_")) return "github";
    if (name.startsWith("tr_log_")) return "build_log";
    if (name.startsWith("tr_")) return "repo";
    if (name.startsWith("sonar_")) return "sonar";
    if (name.startsWith("trivy_")) return "trivy";
    return "other";
}

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; className: string }> = {
    pending: { label: "Pending", icon: Clock, className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    running: { label: "Running", icon: Loader2, className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
    completed: { label: "Completed", icon: CheckCircle2, className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300" },
    failed: { label: "Failed", icon: XCircle, className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" },
};

export function EnrichmentTab({ datasetId, dataset, onEnrichmentStatusChange }: EnrichmentTabProps) {
    const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentJob | null>(null);
    const [jobHistory, setJobHistory] = useState<EnrichmentJob[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(["git", "github", "build_log"]));

    const features = dataset.selected_features || [];
    const mappingReady = Boolean(dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name);

    // Group features by category
    const groupedFeatures = features.reduce((acc, feature) => {
        const category = categorizeFeature(feature);
        if (!acc[category]) acc[category] = [];
        acc[category].push(feature);
        return acc;
    }, {} as Record<FeatureCategory, string[]>);

    // Load enrichment status and history
    const loadEnrichmentData = useCallback(async () => {
        try {
            setLoading(true);
            const [status, history] = await Promise.all([
                enrichmentApi.getStatus(datasetId).catch(() => null),
                enrichmentApi.listJobs(datasetId).catch(() => ({ jobs: [] })),
            ]);
            setEnrichmentStatus(status as EnrichmentJob | null);
            setJobHistory((history as { jobs: EnrichmentJob[] }).jobs || []);
            onEnrichmentStatusChange?.(status as EnrichmentJob | null);
        } catch (err) {
            console.error("Failed to load enrichment data:", err);
        } finally {
            setLoading(false);
        }
    }, [datasetId, onEnrichmentStatusChange]);

    useEffect(() => {
        loadEnrichmentData();
    }, [loadEnrichmentData]);

    const toggleCategory = (category: string) => {
        setExpandedCategories(prev => {
            const next = new Set(prev);
            if (next.has(category)) {
                next.delete(category);
            } else {
                next.add(category);
            }
            return next;
        });
    };

    const isRunning = enrichmentStatus?.status === "running";
    const isCompleted = enrichmentStatus?.status === "completed";

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Enrichment Control Panel */}
            <EnrichmentPanel
                datasetId={datasetId}
                selectedFeatures={features}
                mappingReady={mappingReady}
                onEnrichmentComplete={() => loadEnrichmentData()}
            />

            {/* Current Job Progress */}
            {enrichmentStatus && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    {isRunning && <Loader2 className="h-5 w-5 animate-spin text-blue-500" />}
                                    {isCompleted && <CheckCircle2 className="h-5 w-5 text-green-500" />}
                                    {enrichmentStatus.status === "failed" && <XCircle className="h-5 w-5 text-red-500" />}
                                    Current Job
                                </CardTitle>
                                <CardDescription>
                                    Started {new Date(enrichmentStatus.started_at || "").toLocaleString()}
                                </CardDescription>
                            </div>
                            <Badge className={STATUS_CONFIG[enrichmentStatus.status]?.className}>
                                {STATUS_CONFIG[enrichmentStatus.status]?.label}
                            </Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Progress</span>
                                <span className="font-medium">
                                    {enrichmentStatus.progress_percent?.toFixed(1)}%
                                </span>
                            </div>
                            <Progress value={enrichmentStatus.progress_percent || 0} />
                        </div>
                        <div className="grid grid-cols-3 gap-4 text-center">
                            <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                                <p className="text-2xl font-bold">{enrichmentStatus.processed_rows?.toLocaleString() || 0}</p>
                                <p className="text-xs text-muted-foreground">Processed</p>
                            </div>
                            <div className="rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
                                <p className="text-2xl font-bold text-green-600">{enrichmentStatus.enriched_rows?.toLocaleString() || 0}</p>
                                <p className="text-xs text-muted-foreground">Enriched</p>
                            </div>
                            <div className="rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                                <p className="text-2xl font-bold text-red-600">{enrichmentStatus.failed_rows?.toLocaleString() || 0}</p>
                                <p className="text-xs text-muted-foreground">Failed</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Feature Groups */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Zap className="h-5 w-5 text-amber-500" />
                        Selected Features ({features.length})
                    </CardTitle>
                    <CardDescription>
                        Features grouped by extraction source
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                    {Object.entries(groupedFeatures).map(([category, categoryFeatures]) => {
                        const config = CATEGORY_CONFIG[category as FeatureCategory];
                        const isExpanded = expandedCategories.has(category);
                        const Icon = config.icon;

                        return (
                            <div key={category} className="rounded-lg border">
                                <button
                                    className="flex w-full items-center justify-between p-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                                    onClick={() => toggleCategory(category)}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`rounded-lg p-2 ${config.color}`}>
                                            <Icon className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <p className="font-medium">{config.label}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {categoryFeatures.length} features
                                            </p>
                                        </div>
                                    </div>
                                    {isExpanded ? (
                                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                    ) : (
                                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                    )}
                                </button>
                                {isExpanded && (
                                    <div className="border-t px-3 py-2">
                                        <div className="flex flex-wrap gap-2">
                                            {categoryFeatures.map(feature => (
                                                <Badge key={feature} variant="secondary" className="font-mono text-xs">
                                                    {feature}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                    {features.length === 0 && (
                        <p className="py-8 text-center text-muted-foreground">
                            No features selected. Go to Configuration to add features.
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Job History */}
            {jobHistory.length > 0 && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <CardTitle>Job History</CardTitle>
                            <Button variant="ghost" size="sm" onClick={loadEnrichmentData}>
                                <RefreshCw className="mr-2 h-4 w-4" />
                                Refresh
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="max-h-64 overflow-auto">
                            <table className="min-w-full text-sm">
                                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                    <tr>
                                        <th className="px-4 py-2 text-left font-medium">Status</th>
                                        <th className="px-4 py-2 text-left font-medium">Started</th>
                                        <th className="px-4 py-2 text-left font-medium">Progress</th>
                                        <th className="px-4 py-2 text-left font-medium">Rows</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {jobHistory.slice(0, 10).map((job, idx) => {
                                        const statusConfig = STATUS_CONFIG[job.status];
                                        const StatusIcon = statusConfig?.icon || Clock;
                                        return (
                                            <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                                                <td className="px-4 py-2">
                                                    <Badge className={statusConfig?.className}>
                                                        <StatusIcon className={`mr-1 h-3 w-3 ${job.status === "running" ? "animate-spin" : ""}`} />
                                                        {statusConfig?.label}
                                                    </Badge>
                                                </td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {job.started_at ? new Date(job.started_at).toLocaleString() : "—"}
                                                </td>
                                                <td className="px-4 py-2">
                                                    <div className="flex items-center gap-2">
                                                        <Progress value={job.progress_percent || 0} className="h-2 w-20" />
                                                        <span className="text-xs text-muted-foreground">
                                                            {(job.progress_percent || 0).toFixed(0)}%
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-2 text-muted-foreground">
                                                    {job.enriched_rows?.toLocaleString() || 0} / {job.total_rows?.toLocaleString() || 0}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
