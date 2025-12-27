"use client";

import { useEffect, useState, useMemo } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Cell,
} from "recharts";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertCircle, BarChart3, Info } from "lucide-react";
import {
    statisticsApi,
    type FeatureDistributionResponse,
    type NumericDistribution,
    type CategoricalDistribution,
} from "@/lib/api/statistics";

interface FeatureDistributionChartProps {
    datasetId: string;
    versionId: string;
    availableFeatures: string[]; // List of feature names to choose from
}

type DistributionData = NumericDistribution | CategoricalDistribution;

export function FeatureDistributionChart({
    datasetId,
    versionId,
    availableFeatures,
}: FeatureDistributionChartProps) {
    const [selectedFeature, setSelectedFeature] = useState<string>(
        availableFeatures.length > 0 ? availableFeatures[0] : ""
    );
    const [data, setData] = useState<FeatureDistributionResponse | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch distributions when selected feature changes
    useEffect(() => {
        if (!selectedFeature) return;

        const fetchData = async () => {
            setIsLoading(true);
            setError(null);
            try {
                // We fetch one feature at a time to keep payload small
                // But the API supports bulk fetching if needed
                const response = await statisticsApi.getDistributions(datasetId, versionId, {
                    features: [selectedFeature],
                    bins: 20, // Default bins for numeric
                    top_n: 15, // Top N for categorical
                });
                setData(response);
            } catch (err) {
                console.error("Failed to fetch distribution:", err);
                setError("Failed to load distribution data");
            } finally {
                setIsLoading(false);
            }
        };

        fetchData();
    }, [datasetId, versionId, selectedFeature]);

    // Initialize selection if not set and features available
    useEffect(() => {
        if (!selectedFeature && availableFeatures.length > 0) {
            setSelectedFeature(availableFeatures[0]);
        }
    }, [availableFeatures, selectedFeature]);

    const currentDist: DistributionData | undefined = data?.distributions[selectedFeature];

    // Prepare chart data
    const chartData = useMemo(() => {
        if (!currentDist) return [];

        if (currentDist.data_type === "integer" || currentDist.data_type === "float" || currentDist.data_type === "numeric") {
            // Numeric: Use bins
            const numDist = currentDist as NumericDistribution;
            return numDist.bins.map((bin) => ({
                name: `${bin.min_value.toFixed(2)} - ${bin.max_value.toFixed(2)}`,
                range: [bin.min_value, bin.max_value],
                count: bin.count,
                percentage: bin.percentage,
                label: `[${bin.min_value.toFixed(1)}, ${bin.max_value.toFixed(1)})`,
            }));
        } else {
            // Categorical: Use values
            const catDist = currentDist as CategoricalDistribution;
            return catDist.values.map((val) => ({
                name: val.value.length > 20 ? val.value.slice(0, 20) + "..." : val.value,
                fullName: val.value,
                count: val.count,
                percentage: val.percentage,
                label: val.value,
            }));
        }
    }, [currentDist]);

    if (availableFeatures.length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Feature Distributions</CardTitle>
                    <CardDescription>No features available for analysis.</CardDescription>
                </CardHeader>
            </Card>
        );
    }

    return (
        <Card className="h-full">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between flex-wrap gap-4">
                    <CardDescription>
                        Value analysis for individual features
                    </CardDescription>
                    <div className="w-[250px]">
                        <Select
                            value={selectedFeature}
                            onValueChange={setSelectedFeature}
                            disabled={isLoading}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Select feature..." />
                            </SelectTrigger>
                            <SelectContent>
                                {availableFeatures.map((f) => (
                                    <SelectItem key={f} value={f}>
                                        {f}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {/* Stats Summary */}
                {currentDist && (
                    <div className="mb-6 grid grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-muted/30 rounded-lg">
                        <div className="space-y-1">
                            <span className="text-xs text-muted-foreground">Type</span>
                            <div className="font-medium flex items-center gap-2">
                                <Badge variant="outline">{currentDist.data_type}</Badge>
                            </div>
                        </div>
                        <div className="space-y-1">
                            <span className="text-xs text-muted-foreground">Total Count</span>
                            <div className="font-medium text-lg">
                                {currentDist.total_count.toLocaleString()}
                            </div>
                        </div>
                        <div className="space-y-1">
                            <span className="text-xs text-muted-foreground">Null / Missing</span>
                            <div className="font-medium text-lg">
                                {currentDist.null_count.toLocaleString()}
                                <span className="text-xs text-muted-foreground ml-1">
                                    ({((currentDist.null_count / (currentDist.total_count || 1)) * 100).toFixed(1)}%)
                                </span>
                            </div>
                        </div>

                        {/* Numeric specific stats */}
                        {(currentDist.data_type === "integer" || currentDist.data_type === "float" || currentDist.data_type === "numeric") && (
                            <div className="space-y-1">
                                <span className="text-xs text-muted-foreground">Mean / Median</span>
                                <div className="font-medium">
                                    {(currentDist as NumericDistribution).stats?.mean.toFixed(2) ?? "-"} / {(currentDist as NumericDistribution).stats?.median.toFixed(2) ?? "-"}
                                </div>
                            </div>
                        )}

                        {/* Categorical specific stats */}
                        {!(currentDist.data_type === "integer" || currentDist.data_type === "float" || currentDist.data_type === "numeric") && (
                            <div className="space-y-1">
                                <span className="text-xs text-muted-foreground">Unique Values</span>
                                <div className="font-medium text-lg">
                                    {(currentDist as CategoricalDistribution).unique_count.toLocaleString()}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Chart Area */}
                <div className="h-[300px] w-full relative">
                    {isLoading ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        </div>
                    ) : error ? (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
                            <AlertCircle className="h-8 w-8 text-destructive" />
                            <p>{error}</p>
                        </div>
                    ) : !currentDist ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground">
                            Select a feature to view distribution
                        </div>
                    ) : chartData.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-2">
                            <Info className="h-8 w-8 opacity-50" />
                            <p>No valid values to display (all values are null or empty)</p>
                        </div>
                    ) : (
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={chartData}
                                margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                                <XAxis
                                    dataKey="name"
                                    tick={{ fontSize: 11 }}
                                    angle={-45}
                                    textAnchor="end"
                                    interval={0}
                                    height={60}
                                />
                                <YAxis />
                                <Tooltip
                                    content={({ active, payload, label }) => {
                                        if (active && payload && payload.length) {
                                            const dataItem = payload[0].payload;
                                            return (
                                                <div className="bg-popover border rounded-md shadow-md p-3 text-sm">
                                                    <p className="font-medium mb-1">{dataItem.fullName || dataItem.label}</p>
                                                    <div className="flex items-center gap-2 text-muted-foreground">
                                                        <span>Count:</span>
                                                        <span className="font-mono font-medium text-foreground">{dataItem.count}</span>
                                                    </div>
                                                    <div className="flex items-center gap-2 text-muted-foreground">
                                                        <span>Percentage:</span>
                                                        <span className="font-mono font-medium text-foreground">{dataItem.percentage.toFixed(1)}%</span>
                                                    </div>
                                                </div>
                                            );
                                        }
                                        return null;
                                    }}
                                />
                                <Bar dataKey="count" fill="currentColor" className="fill-primary" radius={[4, 4, 0, 0]}>
                                    {chartData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
