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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { datasetApi } from "@/lib/api";
import type { DatasetJob, DatasetJobStatus } from "@/types/dataset";

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

interface JobCardProps {
  job: DatasetJob;
  onClick?: () => void;
  onRefresh: () => void;
}

function JobCard({ job, onClick, onRefresh }: JobCardProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const isActive = ["pending", "fetching_runs", "processing", "exporting"].includes(
    job.status
  );

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
        "rounded-lg border bg-card p-4 transition-colors",
        onClick && "cursor-pointer hover:bg-muted/50"
      )}
      onClick={onClick}
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
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              className="text-green-600 hover:text-green-700"
            >
              <Download className="h-4 w-4 mr-1" />
              Download
            </Button>
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
    </div>
  );
}
