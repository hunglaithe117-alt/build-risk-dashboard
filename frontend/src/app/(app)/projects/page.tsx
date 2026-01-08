"use client";

import {
  FileSpreadsheet,
  Loader2,
  Trash2,
  Upload,
  RefreshCw,
} from "lucide-react";
import { useRouter } from "next/navigation";
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
import { toast } from "@/components/ui/use-toast";
import { useDebounce } from "@/hooks/use-debounce";
import { datasetsApi } from "@/lib/api";
import type {
  DatasetRecord,
  DatasetTemplateRecord
} from "@/types";
import { useWebSocket } from "@/contexts/websocket-context";



function formatNumber(value: number) {
  return value.toLocaleString("en-US");
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch (err) {
    return value;
  }
}

const PAGE_SIZE = 20;

export default function DatasetsPage() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<DatasetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [resumeDataset, setResumeDataset] = useState<DatasetRecord | null>(null);

  // Search and pagination
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 500);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);



  // Templates
  const [templates, setTemplates] = useState<DatasetTemplateRecord[]>([]);

  const loadDatasets = useCallback(
    async (pageNumber = 1, withSpinner = false) => {
      if (withSpinner) {
        setTableLoading(true);
      }
      try {
        const data = await datasetsApi.list({
          skip: (pageNumber - 1) * PAGE_SIZE,
          limit: PAGE_SIZE,
        });
        setDatasets(data.items || []);
        setTotal(data.total);
        setPage(pageNumber);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
        setTableLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadDatasets(1, true);
  }, [loadDatasets]);

  // WebSocket subscription for real-time dataset updates
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsubscribe = subscribe("DATASET_UPDATE", (data: {
      dataset_id: string;
      validation_status: string;
      validation_progress?: number;
      validation_stats?: any;
      validation_error?: string;
    }) => {
      setDatasets((prev) =>
        prev.map((d) => {
          if (d.id === data.dataset_id) {
            return {
              ...d,
              validation_status: data.validation_status as DatasetRecord["validation_status"],
              validation_progress: data.validation_progress ?? d.validation_progress,
              validation_stats: data.validation_stats ?? d.validation_stats,
              validation_error: data.validation_error ?? d.validation_error,
            };
          }
          return d;
        })
      );

      // Reload to get fresh data when validation completes or fails
      if (data.validation_status === "completed" || data.validation_status === "failed") {
        loadDatasets(page, false);
      }
    });

    return () => unsubscribe();
  }, [subscribe, loadDatasets, page]);

  const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

  const handlePageChange = (direction: "prev" | "next") => {
    const targetPage =
      direction === "prev"
        ? Math.max(1, page - 1)
        : Math.min(totalPages, page + 1);
    if (targetPage !== page) {
      void loadDatasets(targetPage, true);
    }
  };

  const handleUploadSuccess = (dataset: DatasetRecord) => {
    // Navigate directly to dataset detail page
    router.push(`/projects/${dataset.id}`);
  };



  const handleDelete = async (dataset: DatasetRecord) => {
    if (!confirm(`Delete dataset "${dataset.name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await datasetsApi.delete(dataset.id);
      toast({ title: "Deleted", description: `Dataset "${dataset.name}" deleted.` });
      loadDatasets(page, true);
    } catch (err) {
      console.error(err);
    }
  };

  const getStatusBadge = (dataset: DatasetRecord) => {
    const validationStatus = dataset.validation_status;
    const setupStep = dataset.setup_step || 1;

    // Check validation status
    if (validationStatus === "validating") {
      return <Badge variant="outline" className="border-blue-500 text-blue-600">Validating...</Badge>;
    }
    if (validationStatus === "failed") {
      return <Badge variant="destructive">Validation Failed</Badge>;
    }
    if (validationStatus === "completed") {
      return <Badge variant="outline" className="border-green-500 text-green-600">Validated</Badge>;
    }

    // Use setup_step for pending/not-started states
    // Step 2: Validated (ready for enrichment)
    if (setupStep >= 2) {
      return <Badge variant="outline" className="border-green-400 text-green-500">Ready</Badge>;
    }

    // Step 1: Pending config (just uploaded, need to map columns)
    return <Badge variant="outline" className="border-slate-400 text-slate-500">Pending Config</Badge>;
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading datasets...</CardTitle>
            <CardDescription>Fetching your datasets.</CardDescription>
          </CardHeader>
          <CardContent>
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle>Dataset Management</CardTitle>
            <CardDescription>
              Upload CSV datasets and configure feature extraction.
            </CardDescription>
          </div>
          <Button onClick={() => router.push("/projects/upload")} className="gap-2">
            <Upload className="h-4 w-4" /> Upload CSV
          </Button>
        </CardHeader>
      </Card>

      {/* Feedback */}
      {feedback && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          {feedback}
        </div>
      )}

      {/* Datasets Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Uploaded Datasets</CardTitle>
              <CardDescription>
                Overview of all datasets available for enrichment
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Input
                  placeholder="Search datasets..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-9"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadDatasets(page, true)}
                disabled={tableLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${tableLoading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 dark:bg-slate-900/40">
                <tr>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Dataset Name
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Rows
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Versions
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Created
                  </th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {datasets.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-12 text-center text-muted-foreground"
                    >
                      <div className="flex flex-col items-center gap-3">
                        <FileSpreadsheet className="h-12 w-12 text-slate-300" />
                        <p>No datasets uploaded yet.</p>
                        <Button
                          variant="outline"
                          onClick={() => router.push("/projects/upload")}
                        >
                          <Upload className="mr-2 h-4 w-4" /> Upload CSV
                        </Button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  datasets.map((dataset) => (
                    <tr
                      key={dataset.id}
                      className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                      onClick={async () => {
                        if (dataset.validation_status === "completed") {
                          router.push(`/projects/${dataset.id}`);
                        } else {
                          // Open upload modal to continue setup
                          router.push("/projects/upload");
                          // TODO: Support resuming specific dataset via URL param
                          // setResumeDataset(freshDataset);
                          // setUploadModalOpen(true);
                        }
                      }}
                    >
                      <td className="px-6 py-4">
                        <div>
                          <p className="font-medium text-foreground">{dataset.name}</p>
                          <p className="text-xs text-muted-foreground">{dataset.file_name}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        {getStatusBadge(dataset)}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {formatNumber(dataset.rows)}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {dataset.versions_count || 0}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {formatDate(dataset.created_at)}
                      </td>
                      <td className="px-6 py-4">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0 text-red-600 hover:bg-red-50 hover:text-red-700"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(dataset);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                          <span className="sr-only">Delete</span>
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
        <div className="flex flex-col gap-3 border-t border-slate-200 px-6 py-4 text-sm text-muted-foreground dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
          <div>
            {total > 0
              ? `Showing ${pageStart}-${pageEnd} of ${total} datasets`
              : "No datasets to display"}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {tableLoading && (
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-xs">Refreshing...</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePageChange("prev")}
                disabled={page === 1 || tableLoading}
              >
                Previous
              </Button>
              <span className="text-xs text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePageChange("next")}
                disabled={page >= totalPages || tableLoading}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      </Card>


    </div>
  );
}
