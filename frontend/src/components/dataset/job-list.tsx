"use client";

import { useState, useEffect } from "react";
import {
  Download,
  Loader2,
  MoreHorizontal,
  Trash2,
  XCircle,
  CheckCircle2,
  Clock,
  AlertCircle,
  RefreshCw,
  Eye,
  X,
  Info,
  FileText,
  Calendar,
  GitBranch,
  Hash,
  Layers,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { datasetApi } from "@/lib/api";
import type { DatasetJob, DatasetJobStatus } from "@/types/dataset";
import { ColumnDistribution, ColumnHeaderStats } from "./column-distribution";

const STATUS_CONFIG: Record<
  DatasetJobStatus,
  { label: string; color: string; icon: React.ReactNode }
> = {
  pending: {
    label: "Pending",
    color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300",
    icon: <Clock className="h-3.5 w-3.5" />,
  },
  fetching_runs: {
    label: "Fetching",
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  processing: {
    label: "Processing",
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  exporting: {
    label: "Exporting",
    color: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
  },
  completed: {
    label: "Completed",
    color: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
  },
  failed: {
    label: "Failed",
    color: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
    icon: <AlertCircle className="h-3.5 w-3.5" />,
  },
  cancelled: {
    label: "Cancelled",
    color: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300",
    icon: <XCircle className="h-3.5 w-3.5" />,
  },
};

interface JobListProps {
  jobs: DatasetJob[];
  onRefresh: () => void;
  onJobClick?: (job: DatasetJob) => void;
  isLoading?: boolean;
}

export function JobList({ jobs, onRefresh, onJobClick, isLoading }: JobListProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Your Dataset Jobs</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isLoading}
        >
          <RefreshCw
            className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {jobs.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p>No dataset jobs yet.</p>
          <p className="text-sm">Create your first custom dataset above.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onClick={() => onJobClick?.(job)}
              onRefresh={onRefresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Preview Modal Component
interface PreviewDialogProps {
  job: DatasetJob | null;
  open: boolean;
  onClose: () => void;
}

function PreviewDialog({ job, open, onClose }: PreviewDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"table" | "distribution">("table");
  const [previewData, setPreviewData] = useState<{
    columns: string[];
    rows: Record<string, unknown>[];
    total_rows: number;
    preview_rows: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && job && job.status === "completed") {
      loadPreview();
    }
  }, [open, job]);

  const loadPreview = async () => {
    if (!job) return;
    
    setIsLoading(true);
    setError(null);
    try {
      // Load more rows for distribution analysis
      const data = await datasetApi.previewJob(job.id, 100);
      setPreviewData(data);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || "Failed to load preview");
    } finally {
      setIsLoading(false);
    }
  };

  const formatCellValue = (value: unknown): string => {
    if (value === null || value === undefined) return "-";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") {
      if (Number.isInteger(value)) return value.toString();
      return value.toFixed(4);
    }
    if (Array.isArray(value)) return value.join(", ");
    return String(value);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50" 
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
      />
      
      {/* Modal */}
      <div className="relative bg-background rounded-lg shadow-lg w-full max-w-6xl max-h-[85vh] mx-4 flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            <h2 className="text-lg font-semibold">Dataset Preview</h2>
            {job && (
              <span className="text-sm font-normal text-muted-foreground">
                - {job.repo_url.split("/").slice(-2).join("/")}
              </span>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Tabs */}
        <div className="px-4 pt-2 border-b">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "table" | "distribution")}>
            <TabsList>
              <TabsTrigger value="table" className="gap-2">
                <Eye className="h-4 w-4" />
                Table View
              </TabsTrigger>
              <TabsTrigger value="distribution" className="gap-2">
                <BarChart3 className="h-4 w-4" />
                Distribution
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-12 text-red-500">
              <AlertCircle className="h-5 w-5 mr-2" />
              {error}
            </div>
          ) : previewData ? (
            <>
              {activeTab === "table" && (
                <div className="space-y-3 h-full">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                      Showing {previewData.preview_rows} of {previewData.total_rows} rows
                    </span>
                    <span>{previewData.columns.length} columns</span>
                  </div>

                  <ScrollArea className="h-[450px] border rounded-md">
                    <Table>
                      <TableHeader className="sticky top-0 bg-background z-10">
                        <TableRow>
                          {previewData.columns.map((col) => (
                            <TableHead
                              key={col}
                              className="whitespace-nowrap font-mono text-xs align-top py-2"
                            >
                              <ColumnHeaderStats 
                                columnName={col} 
                                values={previewData.rows.map(row => row[col])} 
                              />
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {previewData.rows.map((row, idx) => (
                          <TableRow key={idx}>
                            {previewData.columns.map((col) => (
                              <TableCell
                                key={col}
                                className="whitespace-nowrap font-mono text-xs"
                              >
                                {formatCellValue(row[col])}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <ScrollBar orientation="horizontal" />
                  </ScrollArea>
                </div>
              )}

              {activeTab === "distribution" && (
                <ScrollArea className="h-[500px]">
                  <ColumnDistribution 
                    columns={previewData.columns} 
                    rows={previewData.rows} 
                  />
                </ScrollArea>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              No data to preview
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t">
          {job && job.status === "completed" && (
            <Button
              variant="default"
              onClick={() => window.open(datasetApi.getDownloadUrl(job.id), "_blank")}
            >
              <Download className="h-4 w-4 mr-2" />
              Download Full CSV
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

// Job Detail Dialog Component
interface JobDetailDialogProps {
  job: DatasetJob | null;
  open: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

function JobDetailDialog({ job, open, onClose, onRefresh }: JobDetailDialogProps) {
  const [activeTab, setActiveTab] = useState<"details" | "preview" | "distribution">("details");
  const [isLoading, setIsLoading] = useState(false);
  const [previewData, setPreviewData] = useState<{
    columns: string[];
    rows: Record<string, unknown>[];
    total_rows: number;
    preview_rows: number;
  } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  useEffect(() => {
    if (open && job && job.status === "completed" && (activeTab === "preview" || activeTab === "distribution")) {
      loadPreview();
    }
  }, [open, job, activeTab]);

  const loadPreview = async () => {
    if (!job) return;
    
    setIsLoading(true);
    setPreviewError(null);
    try {
      // Load more rows for distribution analysis
      const data = await datasetApi.previewJob(job.id, 100);
      setPreviewData(data);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setPreviewError(error.response?.data?.detail || "Failed to load preview");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!job || !confirm("Are you sure you want to cancel this job?")) return;
    
    setIsCancelling(true);
    try {
      await datasetApi.cancelJob(job.id);
      onRefresh();
      onClose();
    } catch (error) {
      console.error("Failed to cancel job:", error);
    } finally {
      setIsCancelling(false);
    }
  };

  const handleDelete = async () => {
    if (!job || !confirm("Are you sure you want to delete this job?")) return;
    
    setIsDeleting(true);
    try {
      await datasetApi.deleteJob(job.id);
      onRefresh();
      onClose();
    } catch (error) {
      console.error("Failed to delete job:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const formatCellValue = (value: unknown): string => {
    if (value === null || value === undefined) return "-";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") {
      if (Number.isInteger(value)) return value.toString();
      return value.toFixed(4);
    }
    if (Array.isArray(value)) return value.join(", ");
    return String(value);
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const formatFileSize = (bytes?: number | null) => {
    if (!bytes) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!open || !job) return null;

  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const isActive = ["pending", "fetching_runs", "processing", "exporting"].includes(job.status);
  const repoName = job.repo_url.split("/").slice(-2).join("/");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={(e) => {
        e.stopPropagation();
        onClose();
      }} />
      
      {/* Modal */}
      <div className="relative bg-background rounded-lg shadow-lg w-full max-w-4xl max-h-[85vh] mx-4 flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-3">
            <FileText className="h-5 w-5" />
            <div>
              <h2 className="text-lg font-semibold font-mono">{repoName}</h2>
              <p className="text-xs text-muted-foreground">Job ID: {job.id}</p>
            </div>
            <Badge
              variant="outline"
              className={cn("text-xs flex items-center gap-1", statusConfig.color)}
            >
              {statusConfig.icon}
              {statusConfig.label}
            </Badge>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "details" | "preview" | "distribution")} className="flex-1 flex flex-col overflow-hidden">
          <div className="px-4 pt-2 border-b">
            <TabsList>
              <TabsTrigger value="details" className="gap-2">
                <Info className="h-4 w-4" />
                Details
              </TabsTrigger>
              {job.status === "completed" && (
                <>
                  <TabsTrigger value="preview" className="gap-2">
                    <Eye className="h-4 w-4" />
                    Preview Data
                  </TabsTrigger>
                  <TabsTrigger value="distribution" className="gap-2">
                    <BarChart3 className="h-4 w-4" />
                    Distribution
                  </TabsTrigger>
                </>
              )}
            </TabsList>
          </div>

          {/* Details Tab */}
          <TabsContent value="details" className="flex-1 overflow-auto p-4 mt-0">
            <div className="space-y-6">
              {/* Progress for active jobs */}
              {isActive && job.total_builds > 0 && (
                <div className="space-y-2 p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{job.current_phase}</span>
                    <span>
                      {job.processed_builds}/{job.total_builds} builds
                    </span>
                  </div>
                  <Progress value={job.progress_percent} />
                </div>
              )}

              {/* Error message */}
              {job.status === "failed" && job.error_message && (
                <div className="p-4 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg">
                  <div className="flex items-start gap-2 text-red-600 dark:text-red-400">
                    <AlertCircle className="h-5 w-5 mt-0.5" />
                    <div>
                      <p className="font-medium">Job Failed</p>
                      <p className="text-sm mt-1">{job.error_message}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Job Info Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <GitBranch className="h-3 w-3" /> Repository
                  </p>
                  <p className="font-mono text-sm">{job.repo_url}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Hash className="h-3 w-3" /> Max Builds
                  </p>
                  <p className="text-sm">{job.max_builds || "All"}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> Created
                  </p>
                  <p className="text-sm">{formatDate(job.created_at)}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> Completed
                  </p>
                  <p className="text-sm">{formatDate(job.completed_at)}</p>
                </div>
              </div>

              {/* Output Info (for completed jobs) */}
              {job.status === "completed" && (
                <div className="p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-lg">
                  <div className="flex items-center gap-2 text-green-600 dark:text-green-400 mb-3">
                    <CheckCircle2 className="h-5 w-5" />
                    <span className="font-medium">Job Completed Successfully</span>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Rows</p>
                      <p className="font-semibold">{job.output_row_count || 0}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">File Size</p>
                      <p className="font-semibold">{formatFileSize(job.output_file_size)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Downloads</p>
                      <p className="font-semibold">{job.download_count || 0}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Selected Features */}
              <div className="space-y-2">
                <p className="text-sm font-medium flex items-center gap-1">
                  <Layers className="h-4 w-4" />
                  Selected Features ({job.selected_features.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {job.selected_features.map((feature) => (
                    <Badge key={feature} variant="secondary" className="text-xs font-mono">
                      {feature}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Resolved Features (if different) */}
              {job.resolved_features && job.resolved_features.length > job.selected_features.length && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-muted-foreground">
                    Resolved Features (including dependencies: {job.resolved_features.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.resolved_features
                      .filter((f) => !job.selected_features.includes(f))
                      .map((feature) => (
                        <Badge key={feature} variant="outline" className="text-xs font-mono text-muted-foreground">
                          {feature}
                        </Badge>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </TabsContent>

          {/* Preview Tab */}
          <TabsContent value="preview" className="flex-1 overflow-hidden p-4 mt-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : previewError ? (
              <div className="flex items-center justify-center py-12 text-red-500">
                <AlertCircle className="h-5 w-5 mr-2" />
                {previewError}
              </div>
            ) : previewData ? (
              <div className="space-y-3 h-full">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>
                    Showing {previewData.preview_rows} of {previewData.total_rows} rows
                  </span>
                  <span>{previewData.columns.length} columns</span>
                </div>

                <ScrollArea className="h-[350px] border rounded-md">
                  <Table>
                    <TableHeader className="sticky top-0 bg-background z-10">
                      <TableRow>
                        {previewData.columns.map((col) => (
                          <TableHead key={col} className="whitespace-nowrap font-mono text-xs align-top py-2">
                            <ColumnHeaderStats 
                              columnName={col} 
                              values={previewData.rows.map(row => row[col])} 
                            />
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {previewData.rows.map((row, idx) => (
                        <TableRow key={idx}>
                          {previewData.columns.map((col) => (
                            <TableCell key={col} className="whitespace-nowrap font-mono text-xs">
                              {formatCellValue(row[col])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </div>
            ) : (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                No data to preview
              </div>
            )}
          </TabsContent>

          {/* Distribution Tab */}
          <TabsContent value="distribution" className="flex-1 overflow-hidden p-4 mt-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : previewError ? (
              <div className="flex items-center justify-center py-12 text-red-500">
                <AlertCircle className="h-5 w-5 mr-2" />
                {previewError}
              </div>
            ) : previewData ? (
              <ScrollArea className="h-[400px]">
                <ColumnDistribution 
                  columns={previewData.columns} 
                  rows={previewData.rows} 
                />
              </ScrollArea>
            ) : (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                No data to analyze
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Footer */}
        <div className="flex justify-between gap-2 p-4 border-t">
          <div className="flex gap-2">
            {isActive && (
              <Button
                variant="outline"
                onClick={handleCancel}
                disabled={isCancelling}
                className="text-orange-600 hover:text-orange-700"
              >
                {isCancelling ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <XCircle className="h-4 w-4 mr-2" />}
                Cancel Job
              </Button>
            )}
            {!isActive && (
              <Button
                variant="outline"
                onClick={handleDelete}
                disabled={isDeleting}
                className="text-red-600 hover:text-red-700"
              >
                {isDeleting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Trash2 className="h-4 w-4 mr-2" />}
                Delete
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            {job.status === "completed" && (
              <Button
                variant="default"
                onClick={() => window.open(datasetApi.getDownloadUrl(job.id), "_blank")}
              >
                <Download className="h-4 w-4 mr-2" />
                Download CSV
              </Button>
            )}
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface JobCardProps {
  job: DatasetJob;
  onClick?: () => void;
  onRefresh: () => void;
}

function JobCard({ job, onClick, onRefresh }: JobCardProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const isActive = ["pending", "fetching_runs", "processing", "exporting"].includes(
    job.status
  );

  const handleCardClick = () => {
    setShowDetail(true);
  };

  const handlePreview = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowPreview(true);
  };

  const handleCancel = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to cancel this job?")) return;

    setIsCancelling(true);
    try {
      await datasetApi.cancelJob(job.id);
      onRefresh();
    } catch (error) {
      console.error("Failed to cancel job:", error);
    } finally {
      setIsCancelling(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this job?")) return;

    setIsDeleting(true);
    try {
      await datasetApi.deleteJob(job.id);
      onRefresh();
    } catch (error) {
      console.error("Failed to delete job:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(datasetApi.getDownloadUrl(job.id), "_blank");
  };

  // Extract repo name from URL
  const repoName = job.repo_url.split("/").slice(-2).join("/");

  // Format file size
  const formatFileSize = (bytes?: number | null) => {
    if (!bytes) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Format date
  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 transition-colors cursor-pointer hover:bg-muted/50"
      )}
      onClick={handleCardClick}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm font-medium truncate">
              {repoName}
            </span>
            <Badge
              variant="outline"
              className={cn("text-xs flex items-center gap-1", statusConfig.color)}
            >
              {statusConfig.icon}
              {statusConfig.label}
            </Badge>
          </div>

          <div className="text-xs text-muted-foreground space-y-1">
            <p>
              {job.selected_features.length} features selected •{" "}
              {job.max_builds ? `Max ${job.max_builds} builds` : "All builds"}
            </p>
            <p>Created: {formatDate(job.created_at)}</p>
          </div>

          {/* Progress bar for active jobs */}
          {isActive && job.total_builds > 0 && (
            <div className="mt-3 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{job.current_phase}</span>
                <span className="font-medium">
                  {job.processed_builds}/{job.total_builds} builds
                </span>
              </div>
              <Progress value={job.progress_percent} />
            </div>
          )}

          {/* Completed job info */}
          {job.status === "completed" && (
            <div className="mt-2 text-xs text-muted-foreground">
              <span className="text-green-600 dark:text-green-400">
                ✓ {job.output_row_count} rows
              </span>
              <span className="mx-2">•</span>
              <span>{formatFileSize(job.output_file_size)}</span>
              <span className="mx-2">•</span>
              <span>{job.download_count} downloads</span>
            </div>
          )}

          {/* Error message */}
          {job.status === "failed" && job.error_message && (
            <div className="mt-2 text-xs text-red-600 dark:text-red-400">
              Error: {job.error_message}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {job.status === "completed" && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handlePreview}
                className="text-blue-600 hover:text-blue-700"
              >
                <Eye className="h-4 w-4 mr-1" />
                Preview
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="text-green-600 hover:text-green-700"
              >
                <Download className="h-4 w-4 mr-1" />
                Download
              </Button>
            </>
          )}
          {isActive && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={isCancelling}
              className="text-orange-600 hover:text-orange-700"
            >
              {isCancelling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
            </Button>
          )}
          {!isActive && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDelete}
              disabled={isDeleting}
              className="text-red-600 hover:text-red-700"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Preview Dialog */}
      <PreviewDialog
        job={job}
        open={showPreview}
        onClose={() => setShowPreview(false)}
      />

      {/* Job Detail Dialog */}
      <JobDetailDialog
        job={job}
        open={showDetail}
        onClose={() => setShowDetail(false)}
        onRefresh={onRefresh}
      />
    </div>
  );
}
