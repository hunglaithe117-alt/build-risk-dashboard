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
import { Progress } from "@/components/ui/progress";
import { enrichmentApi } from "@/lib/api";
import type { EnrichmentJob } from "@/types";
import {
    AlertCircle,
    CheckCircle2,
    Download,
    Loader2,
    Play,
    Search,
    Zap,
} from "lucide-react";

import { EnrichmentPanel } from "../../_components/EnrichmentPanel";

interface DatasetFeaturesTabProps {
    datasetId: string;
    features: string[];
    mappingReady: boolean;
}

type FeatureCategory = "git" | "github" | "build_log" | "repo" | "other";

function categorizeFeature(name: string): FeatureCategory {
    if (name.startsWith("git_")) return "git";
    if (name.startsWith("gh_")) return "github";
    if (name.startsWith("tr_log_")) return "build_log";
    if (name.startsWith("tr_")) return "repo";
    return "other";
}

const CATEGORY_LABELS: Record<FeatureCategory, string> = {
    git: "Git Features",
    github: "GitHub Features",
    build_log: "Build Log Features",
    repo: "Repository Features",
    other: "Other Features",
};

const CATEGORY_COLORS: Record<FeatureCategory, string> = {
    git: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
    github: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
    build_log: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
    repo: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
    other: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

export function DatasetFeaturesTab({
    datasetId,
    features,
    mappingReady,
}: DatasetFeaturesTabProps) {
    const [search, setSearch] = useState("");
    const [enrichmentStatus, setEnrichmentStatus] = useState<EnrichmentJob | null>(null);
    const [loading, setLoading] = useState(true);

    // Load enrichment status
    const loadStatus = useCallback(async () => {
        try {
            const status = await enrichmentApi.getStatus(datasetId);
            setEnrichmentStatus(status as unknown as EnrichmentJob);
        } catch {
            // No enrichment job yet
        } finally {
            setLoading(false);
        }
    }, [datasetId]);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    // Filter features
    const filteredFeatures = features.filter((f) =>
        f.toLowerCase().includes(search.toLowerCase())
    );

    // Group by category
    const groupedFeatures = filteredFeatures.reduce((acc, feature) => {
        const category = categorizeFeature(feature);
        if (!acc[category]) acc[category] = [];
        acc[category].push(feature);
        return acc;
    }, {} as Record<FeatureCategory, string[]>);

    const isRunning = enrichmentStatus?.status === "running";
    const isCompleted = enrichmentStatus?.status === "completed";

    return (
        <div className="space-y-6">
            {/* Enrichment Panel - shows validation, start button, progress */}
            <EnrichmentPanel
                datasetId={datasetId}
                selectedFeatures={features}
                mappingReady={mappingReady}
                onEnrichmentComplete={() => loadStatus()}
            />

            {/* Status Card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Zap className="h-5 w-5 text-amber-500" /> Feature Extraction
                            </CardTitle>
                            <CardDescription>
                                {features.length} regular features selected
                            </CardDescription>
                        </div>
                        {isRunning && (
                            <Badge variant="secondary" className="animate-pulse">
                                <Loader2 className="mr-1 h-3 w-3 animate-spin" /> Running
                            </Badge>
                        )}
                        {isCompleted && (
                            <Badge className="bg-green-500">
                                <CheckCircle2 className="mr-1 h-3 w-3" /> Complete
                            </Badge>
                        )}
                    </div>
                </CardHeader>
                {enrichmentStatus && (
                    <CardContent>
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Progress</span>
                                <span className="font-medium">
                                    {enrichmentStatus.progress_percent?.toFixed(1)}%
                                </span>
                            </div>
                            <Progress value={enrichmentStatus.progress_percent || 0} />
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <span>
                                    {enrichmentStatus.processed_rows?.toLocaleString() || 0} /{" "}
                                    {enrichmentStatus.total_rows?.toLocaleString() || 0} rows
                                </span>
                                <span>
                                    {enrichmentStatus.enriched_rows?.toLocaleString() || 0} enriched,{" "}
                                    {enrichmentStatus.failed_rows?.toLocaleString() || 0} failed
                                </span>
                            </div>
                        </div>
                    </CardContent>
                )}
            </Card>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    placeholder="Search features..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-10"
                />
            </div>

            {/* Features Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="max-h-[500px] overflow-auto">
                        <table className="min-w-full text-sm">
                            <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
                                <tr>
                                    <th className="px-4 py-3 text-left font-medium">Feature Name</th>
                                    <th className="px-4 py-3 text-left font-medium">Category</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y">
                                {filteredFeatures.length === 0 ? (
                                    <tr>
                                        <td colSpan={2} className="px-4 py-8 text-center text-muted-foreground">
                                            {features.length === 0
                                                ? "No regular features selected"
                                                : "No features match your search"}
                                        </td>
                                    </tr>
                                ) : (
                                    filteredFeatures.map((feature) => {
                                        const category = categorizeFeature(feature);
                                        return (
                                            <tr key={feature} className="hover:bg-slate-50 dark:hover:bg-slate-900/40">
                                                <td className="px-4 py-2 font-mono text-xs">{feature}</td>
                                                <td className="px-4 py-2">
                                                    <Badge className={CATEGORY_COLORS[category]}>
                                                        {CATEGORY_LABELS[category]}
                                                    </Badge>
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
    );
}
