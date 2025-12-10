"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Download,
  FileSpreadsheet,
  Loader2,
  MoreVertical,
  PlayCircle,
  Plus,
  RefreshCw,
  Settings,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
  X,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { datasetsApi, featuresApi } from "@/lib/api";
import type {
  DatasetRecord,
  DatasetTemplateRecord,
  DatasetUpdatePayload,
  FeatureDefinitionSummary,
} from "@/types";
import { useDebounce } from "@/hooks/use-debounce";
import { EnrichmentPanel } from "./_components/EnrichmentPanel";
import { UploadDatasetModal } from "./_components/UploadDatasetModal";
import { createPortal } from "react-dom";

const Portal = ({ children }: { children: React.ReactNode }) => {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  if (!mounted) return null;
  return createPortal(children, document.body);
};

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
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [resumeDataset, setResumeDataset] = useState<DatasetRecord | null>(null);

  // Search and pagination
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 500);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  // Panel state
  const [panelDataset, setPanelDataset] = useState<DatasetRecord | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelSaving, setPanelSaving] = useState(false);

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
        setError(null);
      } catch (err) {
        console.error(err);
        setError("Unable to load datasets from backend API.");
      } finally {
        setLoading(false);
        setTableLoading(false);
      }
    },
    []
  );

  // Load templates
  useEffect(() => {
    datasetsApi.listTemplates().then((res) => {
      setTemplates(res.items || []);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    loadDatasets(1, true);
  }, [loadDatasets]);

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
    router.push(`/datasets/${dataset.id}`);
  };

  const openPanel = async (datasetId: string) => {
    setPanelLoading(true);
    try {
      const dataset = await datasetsApi.get(datasetId);
      setPanelDataset(dataset);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load dataset details.");
    } finally {
      setPanelLoading(false);
    }
  };

  const closePanel = () => {
    setPanelDataset(null);
  };

  const handleDelete = async (dataset: DatasetRecord) => {
    if (!confirm(`Delete dataset "${dataset.name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await datasetsApi.delete(dataset.id);
      setFeedback(`Dataset "${dataset.name}" deleted.`);
      loadDatasets(page, true);
    } catch (err) {
      console.error(err);
      setFeedback("Failed to delete dataset.");
    }
  };

  const handleApplyTemplate = async (datasetId: string, templateId: string) => {
    try {
      await datasetsApi.applyTemplate(datasetId, templateId);
      setFeedback("Template applied successfully.");
      loadDatasets(page, true);
    } catch (err) {
      console.error(err);
      setFeedback("Failed to apply template.");
    }
  };

  const getStatusBadge = (dataset: DatasetRecord) => {
    const hasMapping = dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name;
    const hasFeatures = dataset.selected_features?.length > 0;

    if (!hasMapping) {
      return <Badge variant="secondary">Pending Mapping</Badge>;
    }
    if (!hasFeatures) {
      return <Badge variant="outline" className="border-amber-500 text-amber-600">No Features</Badge>;
    }
    return <Badge variant="outline" className="border-green-500 text-green-600">Ready</Badge>;
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

  if (error) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-red-200 bg-red-50/60 dark:border-red-800 dark:bg-red-900/20">
          <CardHeader>
            <CardTitle className="text-red-700 dark:text-red-300">
              Unable to load data
            </CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Dataset Management</CardTitle>
            <CardDescription>
              Upload CSV datasets and configure feature extraction.
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
            <Button onClick={() => setUploadModalOpen(true)} className="gap-2">
              <Upload className="h-4 w-4" /> Upload CSV
            </Button>
          </div>
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
          <CardTitle>Uploaded Datasets</CardTitle>
          <CardDescription>
            Overview of all datasets available for enrichment
          </CardDescription>
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
                    Features
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
                          onClick={() => setUploadModalOpen(true)}
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
                      onClick={() => router.push(`/datasets/${dataset.id}`)}
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
                        {dataset.selected_features?.length || 0}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {formatDate(dataset.created_at)}
                      </td>
                      <td className="px-6 py-4">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-8 w-8 p-0"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreVertical className="h-4 w-4" />
                              <span className="sr-only">Open menu</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {/* Continue Setup for incomplete datasets */}
                            {(dataset.selected_features?.length || 0) === 0 && (
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setResumeDataset(dataset);
                                  setUploadModalOpen(true);
                                }}
                                className="text-blue-600"
                              >
                                <PlayCircle className="mr-2 h-4 w-4" />
                                Continue Setup
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                openPanel(dataset.id);
                              }}
                            >
                              <Settings className="mr-2 h-4 w-4" />
                              Configure
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-red-600"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(dataset);
                              }}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
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

      {/* Upload Modal */}
      <UploadDatasetModal
        open={uploadModalOpen}
        onOpenChange={(open) => {
          setUploadModalOpen(open);
          if (!open) setResumeDataset(null);
        }}
        onSuccess={handleUploadSuccess}
        existingDataset={resumeDataset || undefined}
      />

      {/* Dataset Detail Panel */}
      {panelDataset && (
        <Portal>
          <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
            <div className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl dark:bg-slate-950">
              <div className="flex items-center justify-between border-b px-6 py-4">
                <div>
                  <p className="text-lg font-semibold">{panelDataset.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {panelDataset.file_name} • {formatNumber(panelDataset.rows)} rows
                  </p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-muted-foreground hover:bg-slate-100"
                  onClick={closePanel}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {panelLoading ? (
                <div className="flex h-64 items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="space-y-6 p-6">
                  {/* Mapping Status */}
                  <div className="space-y-3">
                    <h3 className="font-semibold">Column Mapping</h3>
                    <div className="grid gap-2 text-sm">
                      <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                        <span className="text-muted-foreground">Build ID</span>
                        <span className="font-medium">
                          {panelDataset.mapped_fields?.build_id || (
                            <span className="text-amber-600">Not mapped</span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                        <span className="text-muted-foreground">Repo Name</span>
                        <span className="font-medium">
                          {panelDataset.mapped_fields?.repo_name || (
                            <span className="text-amber-600">Not mapped</span>
                          )}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Selected Features */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold">Selected Features</h3>
                      <span className="text-sm text-muted-foreground">
                        {panelDataset.selected_features?.length || 0} features
                      </span>
                    </div>
                    {panelDataset.selected_features?.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {panelDataset.selected_features.slice(0, 20).map((f) => (
                          <Badge key={f} variant="secondary" className="text-xs">
                            {f}
                          </Badge>
                        ))}
                        {panelDataset.selected_features.length > 20 && (
                          <Badge variant="outline" className="text-xs">
                            +{panelDataset.selected_features.length - 20} more
                          </Badge>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No features selected yet.
                      </p>
                    )}
                  </div>

                  {/* Preview */}
                  <div className="space-y-3">
                    <h3 className="font-semibold">Data Preview</h3>
                    <div className="max-h-64 overflow-auto rounded-lg border">
                      <table className="min-w-full text-xs">
                        <thead className="bg-slate-50 dark:bg-slate-800">
                          <tr>
                            {panelDataset.columns?.slice(0, 6).map((col) => (
                              <th key={col} className="px-3 py-2 text-left font-medium">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {panelDataset.preview?.slice(0, 5).map((row, idx) => (
                            <tr key={idx}>
                              {panelDataset.columns?.slice(0, 6).map((col) => (
                                <td key={col} className="px-3 py-2 text-muted-foreground">
                                  {String(row[col] || "—").slice(0, 30)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Enrichment Panel */}
                  <EnrichmentPanel
                    datasetId={panelDataset.id}
                    mappingReady={Boolean(panelDataset.mapped_fields?.build_id && panelDataset.mapped_fields?.repo_name)}
                    selectedFeatures={panelDataset.selected_features || []}
                  />
                </div>
              )}
            </div>
          </div>
        </Portal>
      )}
    </div>
  );
}
