"use client";

import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import {
  CheckCircle2,
  Loader2,
  Plus,
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
import { toast } from "@/components/ui/use-toast";
import { useWebSocket } from "@/contexts/websocket-context";
import { reposApi } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type {
  RepositoryRecord
} from "@/types";
import { ImportProgressDisplay } from "./_components/ImportProgressDisplay";


const PAGE_SIZE = 20;

export default function AdminReposPage() {
  const router = useRouter();
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);


  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  // Status filter state
  const [statusFilter, setStatusFilter] = useState<string>("");

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
          status: statusFilter || undefined,
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
    [debouncedSearchQuery, statusFilter]
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



  const [deleteLoading, setDeleteLoading] = useState<Record<string, boolean>>({});

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
        <CardHeader className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle>Repository & Data Management</CardTitle>
            <CardDescription>
              Connect GitHub repositories and ingest builds.
            </CardDescription>
          </div>
          <Button onClick={() => router.push("/repositories/import")} className="gap-2">
            <Plus className="h-4 w-4" /> Add GitHub Repository
          </Button>
        </CardHeader>
      </Card>

      {feedback ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          {feedback}
        </div>
      ) : null}

      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle>Connected repositories</CardTitle>
            <CardDescription>
              Overview of every repository currently tracked by BuildGuard
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
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              <option value="">All Status</option>
              <option value="queued">Queued</option>
              <option value="fetching">Fetching</option>
              <option value="ingesting">Ingesting</option>
              <option value="ingested">Ingested</option>
              <option value="processing">Processing</option>
              <option value="processed">Processed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
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
                        {formatDateTime(repo.last_synced_at)}
                      </td>
                      <td className="px-6 py-4">
                        <ImportProgressDisplay
                          repoId={repo.id}
                          totalFetched={repo.builds_fetched}
                          totalIngested={repo.builds_ingested}
                          totalProcessed={repo.builds_completed}
                          totalFailed={repo.builds_ingestion_failed + repo.builds_processing_failed}
                          importStatus={repo.status}
                        />
                      </td>
                      <td className="px-6 py-4">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-red-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(repo, e as unknown as React.MouseEvent);
                          }}
                          disabled={deleteLoading[repo.id]}
                          title="Delete Repository"
                        >
                          {deleteLoading[repo.id] ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
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
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 text-sm text-muted-foreground dark:border-slate-800">
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
