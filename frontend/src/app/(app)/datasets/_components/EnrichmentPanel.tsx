"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
    AlertCircle,
    CheckCircle2,
    Download,
    Loader2,
    Play,
    Square,
    AlertTriangle,
    Zap,
} from "lucide-react";

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
import type {
    EnrichmentValidateResponse,
    EnrichmentJob,
    EnrichmentWebSocketEvent,
} from "@/types";

interface EnrichmentPanelProps {
    datasetId: string;
    selectedFeatures: string[];
    mappingReady: boolean;
    onEnrichmentComplete?: () => void;
}

type EnrichmentState =
    | "idle"
    | "validating"
    | "validated"
    | "starting"
    | "running"
    | "completed"
    | "failed"
    | "cancelled";

export function EnrichmentPanel({
    datasetId,
    selectedFeatures,
    mappingReady,
    onEnrichmentComplete,
}: EnrichmentPanelProps) {
    const [state, setState] = useState<EnrichmentState>("idle");
    const [validation, setValidation] = useState<EnrichmentValidateResponse | null>(null);
    const [currentJob, setCurrentJob] = useState<EnrichmentJob | null>(null);
    const [progress, setProgress] = useState(0);
    const [processedRows, setProcessedRows] = useState(0);
    const [totalRows, setTotalRows] = useState(0);
    const [currentRepo, setCurrentRepo] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const wsRef = useRef<WebSocket | null>(null);
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

    // Cleanup WebSocket on unmount
    useEffect(() => {
        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
            }
        };
    }, []);

    // Validate dataset
    const handleValidate = useCallback(async () => {
        if (!mappingReady) return;

        setState("validating");
        setError(null);

        try {
            const result = await enrichmentApi.validate(datasetId);
            setValidation(result);
            setState("validated");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Validation failed");
            setState("idle");
        }
    }, [datasetId, mappingReady]);

    // Start enrichment
    const handleStartEnrichment = useCallback(async () => {
        if (!validation?.valid || selectedFeatures.length === 0) return;

        setState("starting");
        setError(null);

        try {
            const response = await enrichmentApi.start(datasetId, {
                selected_features: selectedFeatures,
                auto_import_repos: true,
                skip_existing: true,
            });

            setCurrentJob({
                id: response.job_id,
                dataset_id: datasetId,
                status: "pending",
                total_rows: validation.total_rows,
                processed_rows: 0,
                enriched_rows: 0,
                failed_rows: 0,
                skipped_rows: 0,
                progress_percent: 0,
                selected_features: selectedFeatures,
                repos_auto_imported: [],
            });

            setState("running");
            setTotalRows(validation.total_rows);

            // Connect WebSocket
            connectWebSocket(response.job_id);

        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to start enrichment");
            setState("validated");
        }
    }, [datasetId, validation, selectedFeatures]);

    // Connect to WebSocket for progress
    const connectWebSocket = useCallback((jobId: string) => {
        try {
            const wsUrl = enrichmentApi.getPollingWebSocketUrl(jobId);
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onmessage = (event) => {
                try {
                    const data: EnrichmentWebSocketEvent = JSON.parse(event.data);

                    if (data.type === "progress") {
                        setProgress(data.progress_percent);
                        setProcessedRows(data.processed_rows);
                        setTotalRows(data.total_rows);
                        if ("current_repo" in data && data.current_repo) {
                            setCurrentRepo(data.current_repo);
                        }
                    } else if (data.type === "complete") {
                        setState(data.status === "completed" ? "completed" : "failed");
                        setProgress(100);
                        ws.close();
                        onEnrichmentComplete?.();
                    } else if (data.type === "error") {
                        setError(data.message);
                        setState("failed");
                        ws.close();
                    }
                } catch (e) {
                    console.error("WebSocket message parse error:", e);
                }
            };

            ws.onerror = () => {
                // Fallback to polling
                startPolling(jobId);
            };

            ws.onclose = () => {
                wsRef.current = null;
            };

        } catch (err) {
            // Fallback to polling
            startPolling(jobId);
        }
    }, [onEnrichmentComplete]);

    // Fallback polling
    const startPolling = useCallback((jobId: string) => {
        if (pollingRef.current) return;

        pollingRef.current = setInterval(async () => {
            try {
                const status = await enrichmentApi.getStatus(datasetId);
                setProgress(status.progress_percent);
                setProcessedRows(status.processed_rows);
                setTotalRows(status.total_rows);

                if (["completed", "failed", "cancelled"].includes(status.status)) {
                    setState(status.status as EnrichmentState);
                    if (pollingRef.current) {
                        clearInterval(pollingRef.current);
                        pollingRef.current = null;
                    }
                    onEnrichmentComplete?.();
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, 2000);
    }, [datasetId, onEnrichmentComplete]);

    // Cancel enrichment
    const handleCancel = useCallback(async () => {
        if (!currentJob) return;

        try {
            await enrichmentApi.cancel(datasetId);
            setState("cancelled");

            if (wsRef.current) {
                wsRef.current.close();
            }
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
                pollingRef.current = null;
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to cancel");
        }
    }, [datasetId, currentJob]);

    // Download enriched dataset
    const handleDownload = useCallback(async () => {
        try {
            const blob = await enrichmentApi.download(datasetId);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `enriched_dataset_${datasetId}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Download failed");
        }
    }, [datasetId]);

    // Auto-validate when mapping is ready
    useEffect(() => {
        if (mappingReady && state === "idle") {
            handleValidate();
        }
    }, [mappingReady, state, handleValidate]);

    // Render based on state
    const renderContent = () => {
        switch (state) {
            case "idle":
                return (
                    <div className="flex items-center gap-3 text-muted-foreground">
                        <AlertCircle className="h-5 w-5" />
                        <span>Complete field mapping to enable enrichment</span>
                    </div>
                );

            case "validating":
                return (
                    <div className="flex items-center gap-3 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>Validating dataset...</span>
                    </div>
                );

            case "validated":
                return (
                    <div className="space-y-4">
                        {/* Validation results */}
                        <div className="grid gap-3 md:grid-cols-3">
                            <div className="rounded-lg border p-3">
                                <p className="text-xs text-muted-foreground">Total Rows</p>
                                <p className="text-xl font-bold">{validation?.total_rows.toLocaleString()}</p>
                            </div>
                            <div className="rounded-lg border p-3">
                                <p className="text-xs text-muted-foreground">Repos Found</p>
                                <p className="text-xl font-bold text-emerald-600">
                                    {validation?.repos_found.length}
                                </p>
                            </div>
                            <div className="rounded-lg border p-3">
                                <p className="text-xs text-muted-foreground">Repos to Import</p>
                                <p className="text-xl font-bold text-amber-600">
                                    {validation?.repos_missing.length}
                                </p>
                            </div>
                        </div>

                        {/* Warnings */}
                        {validation?.repos_missing && validation.repos_missing.length > 0 && (
                            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                                <AlertTriangle className="h-4 w-4 mt-0.5" />
                                <div>
                                    <p className="font-medium">
                                        {validation.repos_missing.length} repos will be auto-imported
                                    </p>
                                    <p className="text-xs mt-1">
                                        {validation.repos_missing.slice(0, 3).join(", ")}
                                        {validation.repos_missing.length > 3 && ` +${validation.repos_missing.length - 3} more`}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Invalid repos error */}
                        {validation?.repos_invalid && validation.repos_invalid.length > 0 && (
                            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                                <AlertCircle className="h-4 w-4 mt-0.5" />
                                <div>
                                    <p className="font-medium">Invalid repository names</p>
                                    <p className="text-xs mt-1">{validation.repos_invalid.join(", ")}</p>
                                </div>
                            </div>
                        )}

                        {/* Start button */}
                        <Button
                            onClick={handleStartEnrichment}
                            disabled={selectedFeatures.length === 0 || !validation?.valid}
                            className="w-full gap-2"
                        >
                            <Zap className="h-4 w-4" />
                            Start Enrichment ({selectedFeatures.length} features)
                        </Button>

                        {selectedFeatures.length === 0 && (
                            <p className="text-xs text-center text-muted-foreground">
                                Select at least one feature to enrich
                            </p>
                        )}
                    </div>
                );

            case "starting":
                return (
                    <div className="flex items-center justify-center gap-3 py-4">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>Starting enrichment job...</span>
                    </div>
                );

            case "running":
                return (
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">Progress</span>
                                <span className="font-medium">{progress.toFixed(1)}%</span>
                            </div>
                            <Progress value={progress} />
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <span>
                                    {processedRows.toLocaleString()} / {totalRows.toLocaleString()} rows
                                </span>
                                {currentRepo && <span>Processing: {currentRepo}</span>}
                            </div>
                        </div>

                        <Button
                            variant="destructive"
                            onClick={handleCancel}
                            className="w-full gap-2"
                        >
                            <Square className="h-4 w-4" />
                            Cancel Enrichment
                        </Button>
                    </div>
                );

            case "completed":
                return (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3 text-emerald-600">
                            <CheckCircle2 className="h-6 w-6" />
                            <div>
                                <p className="font-medium">Enrichment Complete!</p>
                                <p className="text-sm text-muted-foreground">
                                    Processed {totalRows.toLocaleString()} rows
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-2">
                            <Button onClick={handleDownload} className="flex-1 gap-2">
                                <Download className="h-4 w-4" />
                                Download Enriched CSV
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => {
                                    setState("validated");
                                    setProgress(0);
                                }}
                            >
                                <Play className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                );

            case "failed":
                return (
                    <div className="space-y-4">
                        <div className="flex items-start gap-3 text-red-600">
                            <AlertCircle className="h-6 w-6 mt-0.5" />
                            <div>
                                <p className="font-medium">Enrichment Failed</p>
                                <p className="text-sm text-muted-foreground">
                                    {error || "An error occurred during enrichment"}
                                </p>
                            </div>
                        </div>

                        <Button
                            variant="outline"
                            onClick={() => {
                                setState("validated");
                                setError(null);
                            }}
                            className="w-full"
                        >
                            Try Again
                        </Button>
                    </div>
                );

            case "cancelled":
                return (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3 text-amber-600">
                            <Square className="h-6 w-6" />
                            <div>
                                <p className="font-medium">Enrichment Cancelled</p>
                                <p className="text-sm text-muted-foreground">
                                    Processed {processedRows.toLocaleString()} of {totalRows.toLocaleString()} rows
                                </p>
                            </div>
                        </div>

                        <Button
                            variant="outline"
                            onClick={() => {
                                setState("validated");
                                setProgress(0);
                            }}
                            className="w-full"
                        >
                            Start New Enrichment
                        </Button>
                    </div>
                );
        }
    };

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            <Zap className="h-5 w-5 text-amber-500" />
                            Feature Enrichment
                        </CardTitle>
                        <CardDescription>
                            Extract features from build data using the pipeline
                        </CardDescription>
                    </div>
                    {state === "running" && (
                        <Badge variant="secondary" className="animate-pulse">
                            Running
                        </Badge>
                    )}
                    {state === "completed" && (
                        <Badge variant="default" className="bg-emerald-500">
                            Complete
                        </Badge>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {error && state !== "failed" && (
                    <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
                        {error}
                    </div>
                )}
                {renderContent()}
            </CardContent>
        </Card>
    );
}
