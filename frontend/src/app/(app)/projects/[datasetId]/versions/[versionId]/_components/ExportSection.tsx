"use client";

import { useState, useEffect, useCallback } from "react";
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Download,
    FileJson,
    FileSpreadsheet,
    Loader2,
    CheckCircle2,
    AlertCircle,
    Clock,
    Lock,
} from "lucide-react";
import { datasetVersionApi } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface ExportSectionProps {
    datasetId: string;
    versionId: string;
    versionStatus: string;
    versionName?: string;
}

type ExportFormat = "csv" | "json";

interface ExportJob {
    id: string;
    status: "pending" | "processing" | "completed" | "failed";
    format: string;
    total_rows: number;
    processed_rows: number;
    file_size?: number;
    created_at?: string;
    completed_at?: string;
}

export function ExportSection({
    datasetId,
    versionId,
    versionStatus,
    versionName = "Version",
}: ExportSectionProps) {
    const [format, setFormat] = useState<ExportFormat>("csv");
    const [isExporting, setIsExporting] = useState(false);
    const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);
    const [isLoadingJobs, setIsLoadingJobs] = useState(false);
    const [previewInfo, setPreviewInfo] = useState<{
        total_rows: number;
        use_async_recommended: boolean;
        sample_features: string[];
    } | null>(null);
    const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);
    const { toast } = useToast();

    const isVersionCompleted = ["processed", "completed"].includes(versionStatus);

    // Fetch preview info and version data
    useEffect(() => {
        async function fetchData() {
            if (!isVersionCompleted) return;
            try {
                // Fetch export preview
                const previewData = await datasetVersionApi.getExportPreview(datasetId, versionId);
                setPreviewInfo(previewData);

                // Fetch version data for selected features
                const versionData = await datasetVersionApi.getVersionData(datasetId, versionId, 1, 1, false);
                setSelectedFeatures(versionData.version.selected_features || []);
            } catch (err) {
                console.error("Failed to fetch export data:", err);
            }
        }
        fetchData();
    }, [datasetId, versionId, isVersionCompleted]);

    // Fetch export jobs
    const fetchExportJobs = useCallback(async () => {
        if (!isVersionCompleted) return;
        setIsLoadingJobs(true);
        try {
            const jobs = await datasetVersionApi.listExportJobs(datasetId, versionId);
            setExportJobs(jobs as ExportJob[]);
        } catch (err) {
            console.error("Failed to fetch export jobs:", err);
        } finally {
            setIsLoadingJobs(false);
        }
    }, [datasetId, versionId, isVersionCompleted]);

    useEffect(() => {
        fetchExportJobs();
    }, [fetchExportJobs]);

    const handleDirectDownload = async () => {
        setIsExporting(true);
        try {
            const blob = await datasetVersionApi.downloadExport(datasetId, versionId, format);
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${versionName}_features.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast({
                title: "Export Complete",
                description: `File downloaded as ${format.toUpperCase()}`,
            });
        } catch (err) {
            console.error("Export failed:", err);
            toast({
                variant: "destructive",
                title: "Export Failed",
                description: "Failed to download export file. Please try again.",
            });
        } finally {
            setIsExporting(false);
        }
    };

    const handleAsyncExport = async () => {
        setIsExporting(true);
        try {
            const result = await datasetVersionApi.createExportJob(datasetId, versionId, format);
            toast({
                title: "Export Job Created",
                description: `Processing ${result.total_rows} rows. Check back shortly.`,
            });
            fetchExportJobs();
        } catch (err) {
            console.error("Failed to create export job:", err);
            toast({
                variant: "destructive",
                title: "Export Failed",
                description: "Failed to create export job. Please try again.",
            });
        } finally {
            setIsExporting(false);
        }
    };

    // Unified export handler - auto-selects sync vs async based on row count
    const ASYNC_THRESHOLD = 1000;
    const handleExport = async () => {
        const shouldUseAsync = previewInfo?.use_async_recommended ||
            (previewInfo?.total_rows && previewInfo.total_rows > ASYNC_THRESHOLD);

        if (shouldUseAsync) {
            await handleAsyncExport();
        } else {
            await handleDirectDownload();
        }
    };

    const handleDownloadJob = async (jobId: string, jobFormat: string) => {
        try {
            const blob = await datasetVersionApi.downloadExportJob(datasetId, jobId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${versionName}_features.${jobFormat}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error("Download failed:", err);
            toast({
                variant: "destructive",
                title: "Download Failed",
                description: "Failed to download export file.",
            });
        }
    };

    const formatFileSize = (bytes?: number): string => {
        if (!bytes) return "—";
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "completed":
                return <Badge className="bg-green-100 text-green-700"><CheckCircle2 className="h-3 w-3 mr-1" />Complete</Badge>;
            case "processing":
            case "pending":
                return <Badge className="bg-blue-100 text-blue-700"><Clock className="h-3 w-3 mr-1 animate-spin" />Processing</Badge>;
            case "failed":
                return <Badge className="bg-red-100 text-red-700"><AlertCircle className="h-3 w-3 mr-1" />Failed</Badge>;
            default:
                return <Badge variant="outline">{status}</Badge>;
        }
    };

    if (!isVersionCompleted) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <Lock className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-lg font-medium">Export Not Available</p>
                    <p className="text-sm text-muted-foreground mt-2">
                        Export is available after feature extraction completes
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Export Card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                            <Download className="h-5 w-5 text-emerald-600" />
                        </div>
                        <div>
                            <CardTitle>Export Features Data</CardTitle>
                            <CardDescription>
                                Download extracted features as CSV or JSON
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Stats */}
                    <div className="grid grid-cols-2 gap-4 p-4 bg-muted/50 rounded-lg">
                        <div>
                            <p className="text-2xl font-bold">{previewInfo?.total_rows?.toLocaleString() || 0}</p>
                            <p className="text-sm text-muted-foreground">Total Rows</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold">{selectedFeatures.length}</p>
                            <p className="text-sm text-muted-foreground">Features</p>
                        </div>
                    </div>

                    {/* Format Selection */}
                    <div className="flex items-center gap-4">
                        <span className="text-sm font-medium w-20">Format:</span>
                        <Select value={format} onValueChange={(v) => setFormat(v as ExportFormat)}>
                            <SelectTrigger className="w-48">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="csv">
                                    <div className="flex items-center gap-2">
                                        <FileSpreadsheet className="h-4 w-4 text-green-600" />
                                        <span>CSV (Comma Separated)</span>
                                    </div>
                                </SelectItem>
                                <SelectItem value="json">
                                    <div className="flex items-center gap-2">
                                        <FileJson className="h-4 w-4 text-blue-600" />
                                        <span>JSON (JavaScript Object)</span>
                                    </div>
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Export Button */}
                    <div className="flex items-center gap-3">
                        <Button
                            onClick={handleExport}
                            disabled={isExporting}
                            className="gap-2"
                        >
                            {isExporting ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Download className="h-4 w-4" />
                            )}
                            {isExporting ? "Exporting..." : "Download"}
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Export Jobs History */}
            {exportJobs.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Export History</CardTitle>
                        <CardDescription>
                            Previous export jobs for this version
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {exportJobs.map((job) => (
                                <div
                                    key={job.id}
                                    className="flex items-center justify-between p-3 border rounded-lg"
                                >
                                    <div className="flex items-center gap-4">
                                        {job.format === "csv" ? (
                                            <FileSpreadsheet className="h-5 w-5 text-green-600" />
                                        ) : (
                                            <FileJson className="h-5 w-5 text-blue-600" />
                                        )}
                                        <div>
                                            <p className="text-sm font-medium">
                                                {job.format.toUpperCase()} Export
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                {job.total_rows.toLocaleString()} rows • {formatFileSize(job.file_size)}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        {getStatusBadge(job.status)}
                                        {job.status === "completed" && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => handleDownloadJob(job.id, job.format)}
                                            >
                                                <Download className="h-4 w-4 mr-1" />
                                                Download
                                            </Button>
                                        )}
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
