"use client";

import { useEffect, useState } from "react";
import {
    AlertCircle,
    CheckCircle2,
    TrendingDown,
    TrendingUp,
    Loader2,
    ShieldCheck,
} from "lucide-react";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buildApi } from "@/lib/api";
import { useRepo } from "../repo-context";
import type { UnifiedBuild } from "@/types";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from "recharts";

export function AnalyticsTab() {
    const { repoId, repo } = useRepo();
    const [builds, setBuilds] = useState<UnifiedBuild[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function loadBuilds() {
            try {
                // Load more builds for analytics
                const response = await buildApi.getUnifiedBuilds(repoId, {
                    skip: 0,
                    limit: 100,
                });
                setBuilds(response.items);
            } catch (err) {
                console.error("Failed to load builds for analytics:", err);
            } finally {
                setLoading(false);
            }
        }
        loadBuilds();
    }, [repoId]);

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Calculate risk statistics
    const buildsWithPredictions = builds.filter((b) => b.predicted_label);
    const riskCounts = { LOW: 0, MEDIUM: 0, HIGH: 0 };
    buildsWithPredictions.forEach((b) => {
        if (b.predicted_label === "LOW") riskCounts.LOW++;
        else if (b.predicted_label === "MEDIUM") riskCounts.MEDIUM++;
        else if (b.predicted_label === "HIGH") riskCounts.HIGH++;
    });

    const totalPredicted = buildsWithPredictions.length;
    const predictionCoverage =
        builds.length > 0 ? (totalPredicted / builds.length) * 100 : 0;

    // Calculate average confidence
    const avgConfidence =
        buildsWithPredictions.length > 0
            ? buildsWithPredictions.reduce(
                (sum, b) => sum + (b.prediction_confidence || 0),
                0
            ) / buildsWithPredictions.length
            : 0;

    // Group builds by date for trend analysis
    const buildsByDate: Record<string, { LOW: number; MEDIUM: number; HIGH: number }> = {};
    buildsWithPredictions.forEach((b) => {
        if (b.created_at) {
            const date = b.created_at.split("T")[0];
            if (!buildsByDate[date]) {
                buildsByDate[date] = { LOW: 0, MEDIUM: 0, HIGH: 0 };
            }
            if (b.predicted_label === "LOW") buildsByDate[date].LOW++;
            else if (b.predicted_label === "MEDIUM") buildsByDate[date].MEDIUM++;
            else if (b.predicted_label === "HIGH") buildsByDate[date].HIGH++;
        }
    });

    // Sort dates and get last 30 days
    const sortedDates = Object.keys(buildsByDate).sort().slice(-30);

    // Calculate risk trend (is it improving or worsening?)
    const recentBuilds = sortedDates.slice(-7);
    const olderBuilds = sortedDates.slice(0, Math.max(0, sortedDates.length - 7));

    const recentHighRisk = recentBuilds.reduce((sum, d) => sum + buildsByDate[d].HIGH, 0);
    const olderHighRisk = olderBuilds.reduce((sum, d) => sum + buildsByDate[d].HIGH, 0);
    const isImproving = recentHighRisk < olderHighRisk;

    // Risk by branch
    const riskByBranch: Record<string, { LOW: number; MEDIUM: number; HIGH: number; total: number }> = {};
    buildsWithPredictions.forEach((b) => {
        const branch = b.branch || "unknown";
        if (!riskByBranch[branch]) {
            riskByBranch[branch] = { LOW: 0, MEDIUM: 0, HIGH: 0, total: 0 };
        }
        if (b.predicted_label === "LOW") riskByBranch[branch].LOW++;
        else if (b.predicted_label === "MEDIUM") riskByBranch[branch].MEDIUM++;
        else if (b.predicted_label === "HIGH") riskByBranch[branch].HIGH++;
        riskByBranch[branch].total++;
    });

    // Get top 5 branches by build count
    const topBranches = Object.entries(riskByBranch)
        .sort((a, b) => b[1].total - a[1].total)
        .slice(0, 5);

    return (
        <div className="space-y-6">
            {/* Key Metrics Row */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Prediction Coverage
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {predictionCoverage.toFixed(1)}%
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {totalPredicted} of {builds.length} builds
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Avg Confidence
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {(avgConfidence * 100).toFixed(1)}%
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Model prediction certainty
                        </p>
                    </CardContent>
                </Card>

                <Card className={riskCounts.HIGH > 0 ? "border-red-200 bg-red-50/30 dark:border-red-900 dark:bg-red-950/20" : ""}>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            High Risk Builds
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className={`text-2xl font-bold ${riskCounts.HIGH > 0 ? "text-red-600" : ""}`}>
                            {riskCounts.HIGH}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {totalPredicted > 0 ? ((riskCounts.HIGH / totalPredicted) * 100).toFixed(1) : 0}% of predictions
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Risk Trend
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            {sortedDates.length >= 2 ? (
                                <>
                                    {isImproving ? (
                                        <TrendingDown className="h-5 w-5 text-green-500" />
                                    ) : (
                                        <TrendingUp className="h-5 w-5 text-red-500" />
                                    )}
                                    <span className={`text-lg font-bold ${isImproving ? "text-green-600" : "text-red-600"}`}>
                                        {isImproving ? "Improving" : "Worsening"}
                                    </span>
                                </>
                            ) : (
                                <span className="text-muted-foreground">Not enough data</span>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Compared to last period
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Risk Distribution */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                    <CardHeader>
                        <CardTitle>Risk Distribution</CardTitle>
                        <CardDescription>
                            Breakdown of predicted risk levels
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {totalPredicted > 0 ? (
                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-medium flex items-center gap-2">
                                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            Low Risk
                                        </span>
                                        <span className="text-sm text-muted-foreground">
                                            {riskCounts.LOW} ({((riskCounts.LOW / totalPredicted) * 100).toFixed(1)}%)
                                        </span>
                                    </div>
                                    <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-green-500 transition-all"
                                            style={{ width: `${(riskCounts.LOW / totalPredicted) * 100}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-medium flex items-center gap-2">
                                            <AlertCircle className="h-4 w-4 text-amber-500" />
                                            Medium Risk
                                        </span>
                                        <span className="text-sm text-muted-foreground">
                                            {riskCounts.MEDIUM} ({((riskCounts.MEDIUM / totalPredicted) * 100).toFixed(1)}%)
                                        </span>
                                    </div>
                                    <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-amber-500 transition-all"
                                            style={{ width: `${(riskCounts.MEDIUM / totalPredicted) * 100}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-medium flex items-center gap-2">
                                            <AlertCircle className="h-4 w-4 text-red-500" />
                                            High Risk
                                        </span>
                                        <span className="text-sm text-muted-foreground">
                                            {riskCounts.HIGH} ({((riskCounts.HIGH / totalPredicted) * 100).toFixed(1)}%)
                                        </span>
                                    </div>
                                    <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-red-500 transition-all"
                                            style={{ width: `${(riskCounts.HIGH / totalPredicted) * 100}%` }}
                                        />
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-8 text-center">
                                <ShieldCheck className="h-10 w-10 text-muted-foreground/50 mb-3" />
                                <p className="text-muted-foreground">
                                    No prediction data available yet
                                </p>
                            </div>
                        )}
                    </CardContent>
                </Card>

                <Card className="col-span-full">
                    <CardHeader>
                        <CardTitle>Risk Over Time</CardTitle>
                        <CardDescription>
                            Build risk levels over the last 30 days
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {sortedDates.length > 0 ? (
                            <ResponsiveContainer width="100%" height={300}>
                                <AreaChart
                                    data={sortedDates.map((date) => ({
                                        date: new Date(date).toLocaleDateString("vi-VN", { month: "2-digit", day: "2-digit" }),
                                        LOW: buildsByDate[date].LOW,
                                        MEDIUM: buildsByDate[date].MEDIUM,
                                        HIGH: buildsByDate[date].HIGH,
                                    }))}
                                    margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                                >
                                    <defs>
                                        <linearGradient id="colorLow" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0.1} />
                                        </linearGradient>
                                        <linearGradient id="colorMed" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.1} />
                                        </linearGradient>
                                        <linearGradient id="colorHigh" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                                    <XAxis
                                        dataKey="date"
                                        tick={{ fontSize: 11 }}
                                        className="text-muted-foreground"
                                    />
                                    <YAxis
                                        tick={{ fontSize: 11 }}
                                        className="text-muted-foreground"
                                        allowDecimals={false}
                                    />
                                    <Tooltip
                                        contentStyle={{
                                            backgroundColor: "hsl(var(--popover))",
                                            border: "1px solid hsl(var(--border))",
                                            borderRadius: "8px",
                                            fontSize: "12px",
                                        }}
                                    />
                                    <Legend />
                                    <Area
                                        type="monotone"
                                        dataKey="LOW"
                                        stackId="1"
                                        stroke="#22c55e"
                                        fill="url(#colorLow)"
                                        name="Low Risk"
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="MEDIUM"
                                        stackId="1"
                                        stroke="#f59e0b"
                                        fill="url(#colorMed)"
                                        name="Medium Risk"
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="HIGH"
                                        stackId="1"
                                        stroke="#ef4444"
                                        fill="url(#colorHigh)"
                                        name="High Risk"
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-12 text-center">
                                <ShieldCheck className="h-10 w-10 text-muted-foreground/50 mb-3" />
                                <p className="text-muted-foreground">
                                    No time-series data available
                                </p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Risk by Branch */}
            <Card>
                <CardHeader>
                    <CardTitle>Risk by Branch</CardTitle>
                    <CardDescription>
                        Top 5 branches by build count with risk breakdown
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {topBranches.length > 0 ? (
                        <div className="space-y-4">
                            {topBranches.map(([branch, data]) => (
                                <div key={branch} className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-medium truncate max-w-[200px]" title={branch}>
                                            {branch}
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <Badge variant="outline" className="border-green-300 text-green-600 text-xs">
                                                {data.LOW} low
                                            </Badge>
                                            <Badge variant="outline" className="border-amber-300 text-amber-600 text-xs">
                                                {data.MEDIUM} med
                                            </Badge>
                                            <Badge variant="outline" className="border-red-300 text-red-600 text-xs">
                                                {data.HIGH} high
                                            </Badge>
                                        </div>
                                    </div>
                                    <div className="flex gap-0.5 h-2 bg-slate-100 dark:bg-slate-800 rounded overflow-hidden">
                                        <div
                                            className="bg-green-500"
                                            style={{ width: `${(data.LOW / data.total) * 100}%` }}
                                        />
                                        <div
                                            className="bg-amber-500"
                                            style={{ width: `${(data.MEDIUM / data.total) * 100}%` }}
                                        />
                                        <div
                                            className="bg-red-500"
                                            style={{ width: `${(data.HIGH / data.total) * 100}%` }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-center">
                            <ShieldCheck className="h-10 w-10 text-muted-foreground/50 mb-3" />
                            <p className="text-muted-foreground">
                                No branch data available
                            </p>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
