"use client";

import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import {
  CheckCircle2,
  Loader2,
  MoreVertical,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState
} from "react";

import { useRouter } from "next/navigation";

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
import { toast } from "@/components/ui/use-toast";
import { useWebSocket } from "@/contexts/websocket-context";
import { reposApi } from "@/lib/api";
import type {
  RepositoryRecord
} from "@/types";
import { ImportProgressDisplay } from "./_components/ImportProgressDisplay";

function formatTimestamp(value?: string) {
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

export default function AdminReposPage() {
  const router = useRouter();
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);


  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);

  const { subscribe } = useWebSocket();

  const loadRepositories = useCallback(
    async (pageNumber = 1, withSpinner = false) => {
      if (withSpinner) {
        setTableLoading(true);
      }
      try {
        const data = await reposApi.list({
          skip: (pageNumber - 1) * PAGE_SIZE,
          limit: PAGE_SIZE,
          q: debouncedSearchQuery || undefined,
        });
        setRepositories(data.items);
        setTotal(data.total);
        setPage(pageNumber);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
        setTableLoading(false);
      }
    },
    [debouncedSearchQuery]
  );

  // WebSocket connection
  useEffect(() => {
    const unsubscribe = subscribe("REPO_UPDATE", (data: any) => {
      setRepositories((prev) => {
        return prev.map((repo) => {
          if (repo.id === data.repo_id) {
            // Update status and stats if available
            return {
              ...repo,
              status: data.status,
              ...(data.stats || {}),
            };
          }
          return repo;
        });
      });

      if (data.status === "imported" || data.status === "failed") {
        // Reload to get fresh data (stats, etc)
        loadRepositories(page);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [subscribe, loadRepositories, page]);

  useEffect(() => {
    loadRepositories(1, true);
  }, [loadRepositories]);



  const [rescanLoading, setRescanLoading] = useState<Record<string, boolean>>({});
  const [reprocessLoading, setReprocessLoading] = useState<Record<string, boolean>>({});
  const [reingestLoading, setReingestLoading] = useState<Record<string, boolean>>({});
  const [startProcessingLoading, setStartProcessingLoading] = useState<Record<string, boolean>>({});
  const [deleteLoading, setDeleteLoading] = useState<Record<string, boolean>>({});

  const handleRescan = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (rescanLoading[repo.id]) return;

    setRescanLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.triggerLazySync(repo.id);
      setFeedback("Repository queued for sync (fetching new builds).");
      loadRepositories(page);
    } catch (err) {
      console.error(err);
    } finally {
      setRescanLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const handleReprocessFailed = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (reprocessLoading[repo.id]) return;

    setReprocessLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.reprocessFailed(repo.id);
      setFeedback("Failed builds queued for retry.");
      loadRepositories(page);
    } catch (err) {
      console.error(err);
    } finally {
      setReprocessLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const handleReingestFailed = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (reingestLoading[repo.id]) return;

    setReingestLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.reingestFailed(repo.id);
      setFeedback("Failed ingestion builds queued for retry.");
      loadRepositories(page);
    } catch (err) {
      console.error(err);
    } finally {
      setReingestLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const handleStartProcessing = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (startProcessingLoading[repo.id]) return;

    setStartProcessingLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.startProcessing(repo.id);
      setFeedback("Processing phase started. Feature extraction will begin shortly.");
      loadRepositories(page);
    } catch (err) {
      console.error(err);
    } finally {
      setStartProcessingLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const handleDelete = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleteLoading[repo.id]) return;

    // Confirmation dialog
    const confirmed = window.confirm(
      `Are you sure you want to delete "${repo.full_name}"?\n\nThis will permanently delete the repository configuration and all associated build data.`
    );
    if (!confirmed) return;

    setDeleteLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.delete(repo.id);
      toast({ title: "Deleted", description: `Repository "${repo.full_name}" deleted.` });
      loadRepositories(page);
    } catch (err) {
      console.error(err);
    } finally {
      setDeleteLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const totalPages = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1;
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

  const handlePageChange = (direction: "prev" | "next") => {
    const targetPage =
      direction === "prev"
        ? Math.max(1, page - 1)
        : Math.min(totalPages, page + 1);
    if (targetPage !== page) {
      void loadRepositories(targetPage, true);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading repositories...</CardTitle>
            <CardDescription>Fetching tracked repositories.</CardDescription>
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
      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Repository & Data Management</CardTitle>
            <CardDescription>
              Connect GitHub repositories and ingest builds.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Input
                placeholder="Search repositories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9"
              />
            </div>
            <Button onClick={() => router.push("/repositories/import")} className="gap-2">
              <Plus className="h-4 w-4" /> Add GitHub Repository
            </Button>
          </div>
        </CardHeader>
      </Card>

      {feedback ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          {feedback}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Connected repositories</CardTitle>
          <CardDescription>
            Overview of every repository currently tracked by BuildGuard
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 dark:bg-slate-900/40">
                <tr>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Repo name
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Import Status
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Last sync time
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Builds Progress
                  </th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {repositories.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-6 text-center text-sm text-muted-foreground"
                    >
                      No repositories have been connected yet.
                    </td>
                  </tr>
                ) : (
                  repositories.map((repo) => (
                    <tr
                      key={repo.id}
                      className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/40"
                      onClick={() => router.push(`/repositories/${repo.id}`)}
                    >
                      <td className="px-6 py-4 font-medium text-foreground">
                        {repo.full_name}
                      </td>
                      <td className="px-6 py-4">
                        {repo.status === "queued" ? (
                          <Badge variant="secondary">Queued</Badge>
                        ) : repo.status === "fetching" ? (
                          <Badge variant="default" className="bg-cyan-500 hover:bg-cyan-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Fetching</Badge>
                        ) : repo.status === "ingesting" ? (
                          <Badge variant="default" className="bg-blue-500 hover:bg-blue-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Ingesting</Badge>
                        ) : repo.status === "ingestion_complete" ? (
                          <Badge variant="default" className="bg-green-500 hover:bg-green-600"><CheckCircle2 className="w-3 h-3 mr-1" /> Ingested</Badge>
                        ) : repo.status === "ingestion_partial" ? (
                          <Badge variant="default" className="bg-amber-500 hover:bg-amber-600">Ingestion Partial</Badge>
                        ) : repo.status === "processing" ? (
                          <Badge variant="default" className="bg-purple-500 hover:bg-purple-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Processing</Badge>
                        ) : repo.status === "partial" ? (
                          <Badge variant="default" className="bg-amber-500 hover:bg-amber-600">Partial</Badge>
                        ) : repo.status === "failed" ? (
                          <Badge variant="destructive">Failed</Badge>
                        ) : (
                          <Badge variant="outline" className="border-green-500 text-green-600">Imported</Badge>
                        )}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {formatTimestamp(repo.last_synced_at)}
                      </td>
                      <td className="px-6 py-4">
                        <ImportProgressDisplay
                          repoId={repo.id}
                          totalFetched={repo.builds_fetched}
                          totalIngested={repo.builds_ingested}
                          totalProcessed={repo.builds_completed}
                          totalFailed={repo.builds_missing_resource + repo.builds_processing_failed}
                          importStatus={repo.status}
                        />
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
                            {/* Start Processing - only when ingestion is complete */}
                            {(repo.status === "ingestion_complete" || repo.status === "ingestion_partial") && (
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleStartProcessing(repo, e as unknown as React.MouseEvent);
                                }}
                                disabled={startProcessingLoading[repo.id]}
                                className="text-green-600 focus:text-green-600 focus:bg-green-50 dark:text-green-400 dark:focus:bg-green-900/20"
                              >
                                {startProcessingLoading[repo.id] ? (
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                  <Play className="mr-2 h-4 w-4" />
                                )}
                                Start Processing
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRescan(repo, e as unknown as React.MouseEvent);
                              }}
                              disabled={
                                rescanLoading[repo.id] ||
                                repo.status === "queued" ||
                                repo.status === "ingesting" ||
                                repo.status === "processing"
                              }
                            >
                              {rescanLoading[repo.id] ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="mr-2 h-4 w-4" />
                              )}
                              Sync New Builds
                            </DropdownMenuItem>
                            {/* Reingest Failed - for ingestion failures */}
                            {(repo.status === "ingestion_partial" || repo.status === "failed") && (
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleReingestFailed(repo, e as unknown as React.MouseEvent);
                                }}
                                disabled={reingestLoading[repo.id]}
                              >
                                {reingestLoading[repo.id] ? (
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                  <RotateCcw className="mr-2 h-4 w-4" />
                                )}
                                Retry Failed Ingestion
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReprocessFailed(repo, e as unknown as React.MouseEvent);
                              }}
                              disabled={
                                reprocessLoading[repo.id] ||
                                repo.status === "queued" ||
                                repo.status === "ingesting" ||
                                repo.status === "ingestion_complete" ||
                                repo.status === "ingestion_partial" ||
                                repo.status === "processing" ||
                                repo.builds_processing_failed === 0
                              }
                            >
                              {reprocessLoading[repo.id] ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <RotateCcw className="mr-2 h-4 w-4" />
                              )}
                              Retry Failed Processing{repo.builds_processing_failed > 0 && ` (${repo.builds_processing_failed})`}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(repo, e as unknown as React.MouseEvent);
                              }}
                              disabled={deleteLoading[repo.id]}
                              className="text-red-600 focus:text-red-600 focus:bg-red-50 dark:text-red-400 dark:focus:bg-red-900/20"
                            >
                              {deleteLoading[repo.id] ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="mr-2 h-4 w-4" />
                              )}
                              Delete Repository
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
              ? `Showing ${pageStart}-${pageEnd} of ${total} repositories`
              : "No repositories to display"}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {tableLoading ? (
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-xs">Refreshing...</span>
              </div>
            ) : null}
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
