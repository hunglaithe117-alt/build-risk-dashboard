"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Download,
    FileJson,
    FileSpreadsheet,
    Loader2,
    CheckCircle2,
    XCircle,
    Clock,
    RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import {
    exportApi,
    ExportPreviewResponse,
    ExportJobResponse,
    ExportJobListItem,
} from "@/lib/api";

interface ExportPanelProps {
    repoId: string;
    repoName?: string;
}

export function ExportPanel({ repoId, repoName }: ExportPanelProps) {
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [preview, setPreview] = useState<ExportPreviewResponse | null>(null);
    const [format, setFormat] = useState<"csv" | "json">("csv");
    const [exporting, setExporting] = useState(false);
    const [currentJob, setCurrentJob] = useState<ExportJobResponse | null>(null);
    const [recentJobs, setRecentJobs] = useState<ExportJobListItem[]>([]);
    const [error, setError] = useState<string | null>(null);

    const loadPreview = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await exportApi.preview(repoId);
            setPreview(data);
        } catch (err: any) {
            setError(err.message || "Failed to load export preview");
        } finally {
            setLoading(false);
        }
    }, [repoId]);

    const loadRecentJobs = useCallback(async () => {
        try {
            const data = await exportApi.listJobs(repoId, 5);
            setRecentJobs(data.items);
        } catch (err) {
            console.error("Failed to load recent jobs", err);
        }
    }, [repoId]);

    useEffect(() => {
        if (open) {
            loadPreview();
            loadRecentJobs();
        }
    }, [open, loadPreview, loadRecentJobs]);

    // Poll for job status when there's an active job
    useEffect(() => {
        if (!currentJob || currentJob.status === "completed" || currentJob.status === "failed") {
            return;
        }

        const interval = setInterval(async () => {
            try {
                const status = await exportApi.getJobStatus(currentJob.job_id);
                setCurrentJob(status);

                if (status.status === "completed" || status.status === "failed") {
                    loadRecentJobs();
                }
            } catch (err) {
                console.error("Failed to poll job status", err);
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [currentJob, loadRecentJobs]);

    const handleExport = async () => {
        setExporting(true);
        setError(null);

        try {
            if (preview?.use_async_recommended) {
                // Large dataset - use async export
                const response = await exportApi.createAsyncJob(repoId, format);
                const status = await exportApi.getJobStatus(response.job_id);
                setCurrentJob(status);
            } else {
                // Small dataset - stream download
                const blob = await exportApi.downloadStream(repoId, format);
                downloadBlob(blob, `${repoName || repoId}_builds.${format}`);
            }
        } catch (err: any) {
            // Check if it's a 413 error (too large)
            if (err.response?.status === 413) {
                // Fallback to async
                try {
                    const response = await exportApi.createAsyncJob(repoId, format);
                    const status = await exportApi.getJobStatus(response.job_id);
                    setCurrentJob(status);
                } catch (asyncErr: any) {
                    setError(asyncErr.message || "Failed to create export job");
                }
            } else {
                setError(err.message || "Failed to export");
            }
        } finally {
            setExporting(false);
        }
    };

    const handleDownloadJob = async (jobId: string) => {
        try {
            const blob = await exportApi.downloadJob(jobId);
            const job = recentJobs.find((j) => j.job_id === jobId);
            const ext = job?.format || "csv";
            downloadBlob(blob, `${repoName || repoId}_builds.${ext}`);
        } catch (err: any) {
            setError(err.message || "Failed to download");
        }
    };

    const downloadBlob = (blob: Blob, filename: string) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    };

    const formatBytes = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                    <Download className="h-4 w-4" />
                    Export
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Export Builds</DialogTitle>
                    <DialogDescription>
                        Export build data with extracted features for analysis.
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                        {error}
                    </div>
                ) : preview ? (
                    <div className="space-y-4">
                        {/* Preview Stats */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm">Export Summary</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="grid grid-cols-3 gap-4 text-sm">
                                    <div>
                                        <p className="text-muted-foreground">Total Builds</p>
                                        <p className="text-xl font-semibold">
                                            {preview.total_rows.toLocaleString()}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-muted-foreground">Features</p>
                                        <p className="text-xl font-semibold">{preview.feature_count}</p>
                                    </div>
                                    <div>
                                        <p className="text-muted-foreground">Export Mode</p>
                                        <Badge variant={preview.use_async_recommended ? "secondary" : "outline"}>
                                            {preview.use_async_recommended ? "Background Job" : "Direct Download"}
                                        </Badge>
                                    </div>
                                </div>

                                {preview.use_async_recommended && (
                                    <p className="text-xs text-muted-foreground">
                                        Large dataset detected (&gt;{preview.async_threshold} rows). Export will be
                                        processed in the background.
                                    </p>
                                )}
                            </CardContent>
                        </Card>

                        {/* Format Selection */}
                        <div className="flex items-center gap-4">
                            <label className="text-sm font-medium">Format:</label>
                            <Select value={format} onValueChange={(v) => setFormat(v as "csv" | "json")}>
                                <SelectTrigger className="w-32">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="csv">
                                        <div className="flex items-center gap-2">
                                            <FileSpreadsheet className="h-4 w-4" />
                                            CSV
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="json">
                                        <div className="flex items-center gap-2">
                                            <FileJson className="h-4 w-4" />
                                            JSON
                                        </div>
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Current Job Progress */}
                        {currentJob && currentJob.status !== "completed" && currentJob.status !== "failed" && (
                            <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-900/20">
                                <CardContent className="pt-4">
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="font-medium">Exporting...</span>
                                            <span className="text-muted-foreground">
                                                {currentJob.processed_rows.toLocaleString()} / {currentJob.total_rows.toLocaleString()} rows
                                            </span>
                                        </div>
                                        <Progress value={currentJob.progress_percent} />
                                        <p className="text-xs text-muted-foreground">
                                            {currentJob.progress_percent.toFixed(1)}% complete
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Completed Job */}
                        {currentJob && currentJob.status === "completed" && (
                            <Card className="border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-900/20">
                                <CardContent className="flex items-center justify-between pt-4">
                                    <div className="flex items-center gap-2">
                                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                                        <div>
                                            <p className="font-medium text-green-700 dark:text-green-300">
                                                Export Complete
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                {currentJob.total_rows.toLocaleString()} rows • {currentJob.file_size_mb} MB
                                            </p>
                                        </div>
                                    </div>
                                    <Button
                                        size="sm"
                                        onClick={() => handleDownloadJob(currentJob.job_id)}
                                        className="gap-2"
                                    >
                                        <Download className="h-4 w-4" />
                                        Download
                                    </Button>
                                </CardContent>
                            </Card>
                        )}

                        {/* Failed Job */}
                        {currentJob && currentJob.status === "failed" && (
                            <Card className="border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20">
                                <CardContent className="flex items-center gap-2 pt-4">
                                    <XCircle className="h-5 w-5 text-red-600" />
                                    <div>
                                        <p className="font-medium text-red-700 dark:text-red-300">Export Failed</p>
                                        <p className="text-xs text-muted-foreground">{currentJob.error_message}</p>
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Recent Exports */}
                        {recentJobs.length > 0 && (
                            <div className="space-y-2">
                                <h4 className="text-sm font-medium text-muted-foreground">Recent Exports</h4>
                                <div className="space-y-2">
                                    {recentJobs.map((job) => (
                                        <div
                                            key={job.job_id}
                                            className="flex items-center justify-between rounded-lg border p-3 text-sm"
                                        >
                                            <div className="flex items-center gap-3">
                                                {job.format === "csv" ? (
                                                    <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                                                ) : (
                                                    <FileJson className="h-4 w-4 text-muted-foreground" />
                                                )}
                                                <div>
                                                    <p className="font-medium">{job.format.toUpperCase()}</p>
                                                    <p className="text-xs text-muted-foreground">
                                                        {job.total_rows.toLocaleString()} rows
                                                        {job.file_size ? ` • ${formatBytes(job.file_size)}` : ""}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <JobStatusBadge status={job.status} />
                                                {job.status === "completed" && job.download_url && (
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => handleDownloadJob(job.job_id)}
                                                    >
                                                        <Download className="h-4 w-4" />
                                                    </Button>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ) : null}

                <DialogFooter className="gap-2">
                    <Button variant="outline" onClick={() => setOpen(false)}>
                        Close
                    </Button>
                    <Button
                        onClick={handleExport}
                        disabled={exporting || !preview || preview.total_rows === 0}
                        className="gap-2"
                    >
                        {exporting ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Exporting...
                            </>
                        ) : (
                            <>
                                <Download className="h-4 w-4" />
                                Export {format.toUpperCase()}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function JobStatusBadge({ status }: { status: string }) {
    switch (status) {
        case "completed":
            return (
                <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    Done
                </Badge>
            );
        case "failed":
            return (
                <Badge variant="destructive" className="gap-1">
                    <XCircle className="h-3 w-3" />
                    Failed
                </Badge>
            );
        case "processing":
            return (
                <Badge variant="secondary" className="gap-1">
                    <RefreshCw className="h-3 w-3 animate-spin" />
                    Processing
                </Badge>
            );
        case "pending":
            return (
                <Badge variant="secondary" className="gap-1">
                    <Clock className="h-3 w-3" />
                    Pending
                </Badge>
            );
        default:
            return <Badge variant="secondary">{status}</Badge>;
    }
}
