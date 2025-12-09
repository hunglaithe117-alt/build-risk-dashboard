"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  MoreVertical,
  Plus,
  RefreshCw,
  RotateCcw,
  Settings,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";

import { useRouter } from "next/navigation";

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
import { reposApi } from "@/lib/api";
import type {
  RepoDetail,
  RepoSuggestion,
  RepoSuggestionResponse,
  RepoUpdatePayload,
  RepositoryRecord,
} from "@/types";
import { Badge } from "@/components/ui/badge";
import { useWebSocket } from "@/contexts/websocket-context";
import { ImportRepoModal } from "./_components/ImportRepoModal";

const Portal = ({ children }: { children: React.ReactNode }) => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;
  return createPortal(children, document.body);
};


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
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  // Panel state
  const [panelRepo, setPanelRepo] = useState<RepoDetail | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelForm, setPanelForm] = useState<RepoUpdatePayload>({});
  const [panelNotes, setPanelNotes] = useState("");
  const [panelSaving, setPanelSaving] = useState(false);
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
        setError(null);
      } catch (err) {
        console.error(err);
        setError("Unable to load repositories from backend API.");
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
            // Update status
            const updated = { ...repo, import_status: data.status };
            return updated;
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

  const handleRescan = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (rescanLoading[repo.id]) return;

    setRescanLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.triggerLazySync(repo.id);
      setFeedback("Repository queued for sync (fetching new builds).");
      loadRepositories(page);
    } catch (err: any) {
      console.error(err);
      setFeedback(err.response?.data?.detail || "Failed to trigger sync.");
    } finally {
      setRescanLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const handleReprocess = async (repo: RepositoryRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (reprocessLoading[repo.id]) return;

    setReprocessLoading((prev) => ({ ...prev, [repo.id]: true }));
    try {
      await reposApi.reprocessFeatures(repo.id);
      setFeedback("Builds queued for feature re-extraction.");
      loadRepositories(page);
    } catch (err: any) {
      console.error(err);
      setFeedback(err.response?.data?.detail || "Failed to trigger re-extraction.");
    } finally {
      setReprocessLoading((prev) => ({ ...prev, [repo.id]: false }));
    }
  };

  const openPanel = async (repoId: string) => {
    setPanelLoading(true);
    setPanelRepo(null);
    setPanelForm({}); // Reset form
    setPanelNotes(""); // Reset notes
    try {
      const detail = await reposApi.get(repoId);
      setPanelRepo(detail);
      // Populate form with repo data
      setPanelForm({
        default_branch: detail.default_branch,
        test_frameworks: detail.test_frameworks || [],
        source_languages: detail.source_languages || [],
      });
      setPanelNotes(detail.notes || "");
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load repository details.");
    } finally {
      setPanelLoading(false);
    }
  };

  const closePanel = () => {
    setPanelRepo(null);
    setPanelForm({});
    setPanelNotes("");
  };

  const handlePanelSave = async () => {
    if (!panelRepo) return;
    setPanelSaving(true);
    try {
      const payload: RepoUpdatePayload = {
        ...panelForm,
        notes: panelNotes || undefined,
      };
      const updated = await reposApi.update(panelRepo.id, payload);
      setPanelRepo(updated);
      await loadRepositories(page, true);
      setFeedback("Repository settings updated.");
    } catch (err) {
      console.error(err);
      setFeedback("Unable to save repository settings.");
    } finally {
      setPanelSaving(false);
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
            <Button onClick={() => setModalOpen(true)} className="gap-2">
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
                    Total builds
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
                      onClick={() => router.push(`/admin/repos/${repo.id}/builds`)}
                    >
                      <td className="px-6 py-4 font-medium text-foreground">
                        {repo.full_name}
                      </td>
                      <td className="px-6 py-4">
                        {repo.import_status === "queued" ? (
                          <Badge variant="secondary">Queued</Badge>
                        ) : repo.import_status === "importing" ? (
                          <Badge variant="default" className="bg-blue-500 hover:bg-blue-600"><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Importing</Badge>
                        ) : repo.import_status === "failed" ? (
                          <Badge variant="destructive">Failed</Badge>
                        ) : (
                          <Badge variant="outline" className="border-green-500 text-green-600">Imported</Badge>
                        )}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {formatTimestamp(repo.last_scanned_at)}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">
                        {repo.total_builds_imported.toLocaleString()}
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
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRescan(repo, e as unknown as React.MouseEvent);
                              }}
                              disabled={
                                rescanLoading[repo.id] ||
                                repo.import_status === "queued" ||
                                repo.import_status === "importing"
                              }
                            >
                              {rescanLoading[repo.id] ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="mr-2 h-4 w-4" />
                              )}
                              Sync New Builds
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReprocess(repo, e as unknown as React.MouseEvent);
                              }}
                              disabled={
                                reprocessLoading[repo.id] ||
                                repo.import_status === "queued" ||
                                repo.import_status === "importing" ||
                                repo.total_builds_imported === 0
                              }
                            >
                              {reprocessLoading[repo.id] ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <RotateCcw className="mr-2 h-4 w-4" />
                              )}
                              Re-extract Features
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation();
                                openPanel(repo.id);
                              }}
                            >
                              <Settings className="mr-2 h-4 w-4" />
                              Settings
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

      <ImportRepoModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onImport={() => {
          loadRepositories(page, true);
          setFeedback("Repositories queued for import.");
        }}
      />

      {panelRepo ? (
        <Portal>
          <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
            <div className="h-full w-full max-w-xl bg-white shadow-2xl dark:bg-slate-950">
              <div className="flex items-center justify-between border-b px-6 py-4">
                <div>
                  <p className="text-lg font-semibold">{panelRepo.full_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {panelRepo.ci_provider.replace("_", " ")}
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
                <div className="flex h-full items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="flex h-full flex-col">
                  <div className="flex-1 overflow-y-auto p-6">
                    <div className="space-y-6">
                      <div className="space-y-2">
                        <label className="text-sm font-medium">
                          Default Branch
                        </label>
                        <input
                          type="text"
                          className="w-full rounded-lg border px-3 py-2 text-sm"
                          value={panelForm.default_branch || ""}
                          readOnly
                          disabled
                        />
                        <p className="text-xs text-muted-foreground">
                          Synced from GitHub.
                        </p>
                      </div>

                      <div className="space-y-2">
                        <label className="text-sm font-medium">
                          Test Frameworks
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {panelForm.test_frameworks?.map((fw) => (
                            <Badge key={fw} variant="secondary">
                              {fw}
                            </Badge>
                          ))}
                          {(!panelForm.test_frameworks ||
                            panelForm.test_frameworks.length === 0) && (
                              <span className="text-sm text-muted-foreground">
                                None detected
                              </span>
                            )}
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="text-sm font-medium">
                          Source Languages
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {panelForm.source_languages?.map((l) => (
                            <Badge key={l} variant="secondary">
                              {l}
                            </Badge>
                          ))}
                          {(!panelForm.source_languages ||
                            panelForm.source_languages.length === 0) && (
                              <span className="text-sm text-muted-foreground">
                                None detected
                              </span>
                            )}
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="text-sm font-medium">Notes</label>
                        <textarea
                          className="h-24 w-full rounded-lg border px-3 py-2 text-sm"
                          placeholder="Add internal notes about this repository..."
                          value={panelNotes}
                          onChange={(e) => setPanelNotes(e.target.value)}
                        />
                      </div>

                      <div className="pt-4">
                        <Button
                          onClick={handlePanelSave}
                          disabled={panelSaving}
                          className="w-full"
                        >
                          {panelSaving ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          ) : (
                            <CheckCircle2 className="mr-2 h-4 w-4" />
                          )}
                          Save Changes
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Portal>
      ) : null}
    </div>
  );
}
