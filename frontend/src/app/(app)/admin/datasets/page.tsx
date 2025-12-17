"use client";

import {
  FileSpreadsheet,
  Loader2,
  MoreVertical,
  PlayCircle,
  Settings,
  Trash2,
  Upload,
  X
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { datasetsApi } from "@/lib/api";
import type {
  DatasetRecord,
  DatasetTemplateRecord
} from "@/types";
import { createPortal } from "react-dom";
import { EnrichmentPanel } from "./_components/EnrichmentPanel";
import { UploadDatasetModal } from "./_components/UploadDatasetModal/index";

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

  useEffect(() => {
    loadDatasets(1, true);
  }, [loadDatasets]);

  // Auto-refresh if any dataset is validating (repo or build)
  useEffect(() => {
    const hasValidating = datasets.some(
      d => d.repo_validation_status === "validating" || d.validation_status === "validating"
    );
    if (!hasValidating) return;

    const interval = setInterval(() => {
      loadDatasets(page, false);
    }, 3000); // Refresh every 3 seconds

    return () => clearInterval(interval);
  }, [datasets, page, loadDatasets]);

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
    router.push(`/admin/datasets/${dataset.id}`);
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

  const getStatusBadge = (dataset: DatasetRecord) => {
    const validationStatus = dataset.validation_status;
    const repoValidationStatus = dataset.repo_validation_status;
    const setupStep = dataset.setup_step || 1;

    // Check repo validation status first (during upload phase)
    if (repoValidationStatus === "validating") {
      return <Badge variant="outline" className="border-purple-500 text-purple-600">Validating Repos...</Badge>;
    }
    if (repoValidationStatus === "failed") {
      return <Badge variant="destructive">Repo Validation Failed</Badge>;
    }

    // Check build validation status (takes priority after repos validated)
    if (validationStatus === "validating") {
      return <Badge variant="outline" className="border-blue-500 text-blue-600">Validating Builds...</Badge>;
    }
    if (validationStatus === "cancelled") {
      return <Badge variant="outline" className="border-amber-500 text-amber-600">Cancelled</Badge>;
    }
    if (validationStatus === "failed") {
      return <Badge variant="destructive">Validation Failed</Badge>;
    }
    if (validationStatus === "completed") {
      return <Badge variant="outline" className="border-green-500 text-green-600">Validated</Badge>;
    }

    // Use setup_step for pending/not-started states
    // Step 3: Ready for validation (Step 2 completed, repos configured)
    if (setupStep >= 3) {
      return <Badge variant="outline" className="border-blue-400 text-blue-500">Ready for Validation</Badge>;
    }
    // Step 2: Configuring repos (Step 1 completed, need to configure repos)
    if (setupStep === 2) {
      return <Badge variant="outline" className="border-amber-400 text-amber-500">Configuring Repos</Badge>;
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
                    Enrichments
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
                      onClick={async () => {
                        if (dataset.validation_status === "completed") {
                          router.push(`/admin/datasets/${dataset.id}`);
                        } else {
                          // Open upload modal to continue setup
                          try {
                            const freshDataset = await datasetsApi.get(dataset.id);
                            setResumeDataset(freshDataset);
                            setUploadModalOpen(true);
                          } catch (err) {
                            console.error("Failed to fetch dataset:", err);
                            setFeedback("Failed to load dataset.");
                          }
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
                        {dataset.enrichment_jobs_count || 0}
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
                            {/* Continue Setup for incomplete datasets (validation not completed) */}
                            {dataset.validation_status !== "completed" && (
                              <DropdownMenuItem
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  // Fetch fresh data to get latest setup_step
                                  try {
                                    const freshDataset = await datasetsApi.get(dataset.id);
                                    setResumeDataset(freshDataset);
                                    setUploadModalOpen(true);
                                  } catch (err) {
                                    console.error("Failed to fetch dataset:", err);
                                    setFeedback("Failed to load dataset.");
                                  }
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
        onDatasetCreated={() => loadDatasets(page, false)}
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

                  {/* Languages & Frameworks */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold">Source Languages</h3>
                      <span className="text-sm text-muted-foreground">
                        {panelDataset.source_languages?.length || 0} languages
                      </span>
                    </div>
                    {(panelDataset.source_languages?.length || 0) > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {panelDataset.source_languages?.map((lang) => (
                          <Badge key={lang} variant="secondary" className="text-xs">
                            {lang}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No languages configured.
                      </p>
                    )}

                    <div className="flex items-center justify-between pt-2">
                      <h3 className="font-semibold">Test Frameworks</h3>
                      <span className="text-sm text-muted-foreground">
                        {panelDataset.test_frameworks?.length || 0} frameworks
                      </span>
                    </div>
                    {(panelDataset.test_frameworks?.length || 0) > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {panelDataset.test_frameworks?.map((fw) => (
                          <Badge key={fw} variant="outline" className="text-xs">
                            {fw}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No frameworks configured.
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
