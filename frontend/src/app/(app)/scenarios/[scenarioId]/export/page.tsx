"use client";

import { useParams } from "next/navigation";
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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Download, FileDown, Loader2, Play, RefreshCw } from "lucide-react";
import {
    trainingScenariosApi,
    TrainingDatasetSplitRecord,
    TrainingScenarioRecord,
} from "@/lib/api/training-scenarios";
import { formatBytes } from "@/lib/utils";
import { toast } from "@/components/ui/use-toast";
import { useSSE } from "@/contexts/sse-context";

export default function ScenarioExportPage() {
    const params = useParams<{ scenarioId: string }>();
    const scenarioId = params.scenarioId;
    const { subscribe } = useSSE();

    const [scenario, setScenario] = useState<TrainingScenarioRecord | null>(null);
    const [splits, setSplits] = useState<TrainingDatasetSplitRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);

    const fetchScenario = useCallback(async () => {
        try {
            const data = await trainingScenariosApi.get(scenarioId);
            setScenario(data);
            return data;
        } catch (err) {
            console.error("Failed to fetch scenario:", err);
            return null;
        }
    }, [scenarioId]);

    const fetchSplits = useCallback(async () => {
        try {
            const data = await trainingScenariosApi.getSplits(scenarioId);
            setSplits(data);
        } catch (err) {
            console.error("Failed to fetch splits:", err);
        }
    }, [scenarioId]);

    const loadData = useCallback(async () => {
        setLoading(true);
        await Promise.all([fetchScenario(), fetchSplits()]);
        setLoading(false);
    }, [fetchScenario, fetchSplits]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // Subscribe to SSE for real-time updates
    useEffect(() => {
        const unsubscribe = subscribe("SCENARIO_UPDATE", (data: { scenario_id?: string }) => {
            if (data.scenario_id === scenarioId) {
                fetchScenario();
                fetchSplits();
            }
        });
        return () => unsubscribe();
    }, [subscribe, scenarioId, fetchScenario, fetchSplits]);

    // Poll while generating
    useEffect(() => {
        if (!scenario || scenario.status !== "splitting") return;

        const interval = setInterval(() => {
            fetchScenario();
            fetchSplits();
        }, 3000);

        return () => clearInterval(interval);
    }, [scenario?.status, fetchScenario, fetchSplits]);

    const handleGenerateDataset = async () => {
        setGenerating(true);
        try {
            await trainingScenariosApi.generateDataset(scenarioId);
            toast({ title: "Dataset generation started" });
            await fetchScenario();
        } catch (err) {
            console.error("Failed to generate dataset:", err);
            toast({ variant: "destructive", title: "Failed to generate dataset" });
        } finally {
            setGenerating(false);
        }
    };

    if (loading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Can generate if status is "processed"
    const canGenerate = scenario?.status === "processed";
    const isGenerating = scenario?.status === "splitting" || generating;
    const isCompleted = scenario?.status === "completed";

    // Show generate button if no splits and can generate
    if (splits.length === 0 && !isCompleted) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Export Dataset</CardTitle>
                    <CardDescription>
                        {canGenerate
                            ? "Generate train/val/test splits from processed builds"
                            : isGenerating
                                ? "Generating dataset..."
                                : "Complete processing phase first to generate dataset"}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="p-8 border rounded-lg bg-muted/50 flex flex-col items-center justify-center gap-4">
                        {isGenerating ? (
                            <>
                                <Loader2 className="h-12 w-12 animate-spin text-purple-500" />
                                <p className="text-muted-foreground text-center">
                                    Generating train/val/test splits...
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    This may take a few minutes depending on the number of builds.
                                </p>
                            </>
                        ) : canGenerate ? (
                            <>
                                <FileDown className="h-12 w-12 text-muted-foreground" />
                                <p className="text-muted-foreground text-center">
                                    Click the button below to generate your train/val/test dataset splits.
                                </p>
                                <Button
                                    size="lg"
                                    onClick={handleGenerateDataset}
                                    disabled={generating}
                                >
                                    {generating ? (
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    ) : (
                                        <Play className="mr-2 h-4 w-4" />
                                    )}
                                    Generate Dataset
                                </Button>
                            </>
                        ) : (
                            <>
                                <FileDown className="h-12 w-12 text-muted-foreground" />
                                <p className="text-muted-foreground text-center">
                                    Dataset generation requires the processing phase to be completed.
                                </p>
                                <Badge variant="outline" className="text-sm">
                                    Current status: {scenario?.status}
                                </Badge>
                            </>
                        )}
                    </div>
                </CardContent>
            </Card>
        );
    }

    // Calculate totals
    const totalRecords = splits.reduce((sum, s) => sum + s.record_count, 0);
    const totalSize = splits.reduce((sum, s) => sum + s.file_size_bytes, 0);

    return (
        <div className="space-y-6">
            {/* Summary Card */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                    <div>
                        <CardTitle>Dataset Summary</CardTitle>
                        <CardDescription>
                            Generated splits ready for download
                        </CardDescription>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" asChild>
                            <a href={`/api/training-scenarios/${scenarioId}/splits/download-all?file_format=parquet`}>
                                <Download className="mr-2 h-4 w-4" />
                                All (Parquet)
                            </a>
                        </Button>
                        <Button variant="outline" size="sm" asChild>
                            <a href={`/api/training-scenarios/${scenarioId}/splits/download-all?file_format=csv`}>
                                <Download className="mr-2 h-4 w-4" />
                                All (CSV)
                            </a>
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleGenerateDataset}
                            disabled={!canGenerate && !isCompleted}
                        >
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Regenerate
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-4">
                        <div className="p-4 border rounded-lg">
                            <p className="text-sm text-muted-foreground">Total Splits</p>
                            <p className="text-2xl font-bold">{splits.length}</p>
                        </div>
                        <div className="p-4 border rounded-lg">
                            <p className="text-sm text-muted-foreground">Total Records</p>
                            <p className="text-2xl font-bold">{totalRecords.toLocaleString()}</p>
                        </div>
                        <div className="p-4 border rounded-lg">
                            <p className="text-sm text-muted-foreground">Features</p>
                            <p className="text-2xl font-bold">{splits[0]?.feature_count || 0}</p>
                        </div>
                        <div className="p-4 border rounded-lg">
                            <p className="text-sm text-muted-foreground">Total Size</p>
                            <p className="text-2xl font-bold">{formatBytes(totalSize)}</p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Splits Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Split Files</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Split</TableHead>
                                <TableHead>Records</TableHead>
                                <TableHead>Features</TableHead>
                                <TableHead>Size</TableHead>
                                <TableHead>Format</TableHead>
                                <TableHead>Generated</TableHead>
                                <TableHead className="text-right">Action</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {splits.map((split) => (
                                <TableRow key={split.id}>
                                    <TableCell>
                                        <Badge variant="outline" className="capitalize">
                                            {split.split_type}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>{split.record_count.toLocaleString()}</TableCell>
                                    <TableCell>{split.feature_count}</TableCell>
                                    <TableCell>{formatBytes(split.file_size_bytes)}</TableCell>
                                    <TableCell>
                                        <Badge variant="secondary">{split.file_format.toUpperCase()}</Badge>
                                    </TableCell>
                                    <TableCell className="text-sm text-muted-foreground">
                                        {split.generated_at
                                            ? new Date(split.generated_at).toLocaleString()
                                            : "-"}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Button size="sm" variant="outline" asChild>
                                            <a
                                                href={`/api/training-scenarios/${scenarioId}/splits/${split.id}/download`}
                                                download={`${split.split_type}.${split.file_format}`}
                                            >
                                                <Download className="mr-2 h-4 w-4" />
                                                Download
                                            </a>
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>

            {/* Class Distribution */}
            {splits.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Class Distribution by Split</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid gap-4 md:grid-cols-3">
                            {splits.map((split) => (
                                <div key={split.id} className="p-4 border rounded-lg">
                                    <p className="font-medium capitalize mb-2">{split.split_type}</p>
                                    <div className="space-y-1 text-sm">
                                        {Object.entries(split.class_distribution || {}).map(([cls, count]) => (
                                            <div key={cls} className="flex justify-between">
                                                <span className="text-muted-foreground">{cls}:</span>
                                                <span className="font-medium">{count}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
