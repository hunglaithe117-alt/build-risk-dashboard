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
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  const [modalStep, setModalStep] = useState<1 | 2>(1);
  const [suggestions, setSuggestions] = useState<RepoSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedRepos, setSelectedRepos] = useState<
    Record<string, RepoSuggestion>
  >({});
  const [repoConfigs, setRepoConfigs] = useState<
    Record<string, {
      test_frameworks: string[];
      source_languages: string[];
      ci_provider: string;
    }>
  >({});
  const [searchTerm, setSearchTerm] = useState("");
  const [addingRepos, setAddingRepos] = useState(false);
  const [panelRepo, setPanelRepo] = useState<RepoDetail | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelForm, setPanelForm] = useState<RepoUpdatePayload>({});
  const [panelNotes, setPanelNotes] = useState("");
  const [panelSaving, setPanelSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

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
    []
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

  const loadSuggestions = useCallback(async (query?: string) => {
    setSuggestionsLoading(true);
    const normalized = query?.trim();
    try {
      const data: RepoSuggestionResponse = await reposApi.discover(
        normalized && normalized.length > 0 ? normalized : undefined,
        20
      );
      setSuggestions(data.items);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load repository choices from GitHub.");
    } finally {
      setSuggestionsLoading(false);
    }
  }, []);

  const handleSync = async () => {
    setSuggestionsLoading(true);
    try {
      const data = await reposApi.sync();
      setSuggestions(data.items);
      setFeedback("Repository list updated from GitHub.");
    } catch (err) {
      console.error(err);
      setFeedback("Unable to sync repositories from GitHub.");
    } finally {
      setSuggestionsLoading(false);
    }
  };

  useEffect(() => {
    if (!modalOpen) {
      setModalStep(1);
      setSelectedRepos({});
      setRepoConfigs({});
      setSearchTerm("");
      setIsSearching(false);
      return;
    }
    // Load private repos when modal opens
    loadSuggestions();
  }, [modalOpen, loadSuggestions]);

  useEffect(() => {
    if (!panelRepo) return;
    setPanelForm({
      default_branch: panelRepo.default_branch,
      notes: panelRepo.notes,
      test_frameworks: panelRepo.test_frameworks,
      source_languages: panelRepo.source_languages,
    });
    setPanelNotes(panelRepo.notes ?? "");
  }, [panelRepo]);

  const selectedList = useMemo(
    () => Object.values(selectedRepos),
    [selectedRepos]
  );

  const toggleSelection = (item: RepoSuggestion) => {
    setSelectedRepos((prev) => {
      const next = { ...prev };
      if (next[item.full_name]) {
        delete next[item.full_name];
        // Also remove config when deselecting
        setRepoConfigs((current) => {
          const updated = { ...current };
          delete updated[item.full_name];
          return updated;
        });
      } else {
        next[item.full_name] = item;
        // Initialize default config
        setRepoConfigs((current) => ({
          ...current,
          [item.full_name]: {
            test_frameworks: [],
            source_languages: [],
            ci_provider: "github_actions",
          },
        }));
      }
      return next;
    });
  };

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchTerm.trim();
    if (query.length > 0) {
      setIsSearching(true);
      void loadSuggestions(query);
    }
  };

  const handleAddRepos = async () => {
    if (!selectedList.length) return;
    setAddingRepos(true);
    setFeedback(null);
    try {
      const payloads = selectedList.map(repo => {
        const config = repoConfigs[repo.full_name] || {
          test_frameworks: [],
          source_languages: [],
          ci_provider: "github_actions",
        };
        return {
          full_name: repo.full_name,
          provider: "github",
          installation_id: repo.installation_id,
          test_frameworks: config.test_frameworks,
          source_languages: config.source_languages,
          ci_provider: config.ci_provider,
        }
      });

      // Use bulk import
      await reposApi.importBulk(payloads);

      // Refresh list immediately to show queued repos
      await loadRepositories(page, true);

      setModalOpen(false);
      setFeedback(
        "Repositories queued for import. You can track progress in the list."
      );
    } catch (err) {
      console.error(err);
      setFeedback(
        "Unable to connect selected repositories. Ensure the GitHub App is installed."
      );
    } finally {
      setAddingRepos(false);
    }
  };

  const openPanel = async (repoId: string) => {
    setPanelLoading(true);
    setPanelRepo(null);
    try {
      const detail = await reposApi.get(repoId);
      setPanelRepo(detail);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load repository details.");
    } finally {
      setPanelLoading(false);
    }
  };

  const closePanel = () => {
    setPanelRepo(null);
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
          <Button onClick={() => setModalOpen(true)} className="gap-2">
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
                        <div className="flex gap-2">

                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(event) => {
                              event.stopPropagation();
                              openPanel(repo.id);
                            }}
                          >
                            Settings
                          </Button>
                        </div>
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

      {modalOpen ? (
        <Portal>
          <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-950">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Connect repositories</h2>
                  <p className="text-sm text-muted-foreground">
                    Step {modalStep} of 2
                  </p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-muted-foreground hover:bg-slate-100"
                  onClick={() => setModalOpen(false)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {modalStep === 1 ? (
                <div className="space-y-4">
                  <form className="flex gap-2" onSubmit={handleSearch}>
                    <input
                      type="text"
                      className="flex-1 rounded-lg border px-3 py-2 text-sm"
                      placeholder="Search all your GitHub repositories (owner/repo or keyword)"
                      value={searchTerm}
                      onChange={(event) => setSearchTerm(event.target.value)}
                    />
                    <Button
                      type="submit"
                      variant="secondary"
                      disabled={!searchTerm.trim()}
                    >
                      Search
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleSync}
                      title="Sync available repositories from GitHub"
                    >
                      <RefreshCw className={`h-4 w-4 ${suggestionsLoading ? "animate-spin" : ""}`} />
                    </Button>
                  </form>
                  <p className="text-xs text-muted-foreground">
                    {isSearching
                      ? "Searching your private GitHub repositories..."
                      : "Showing your accessible repositories. Enter a search term to find your private repositories on GitHub."}
                  </p>
                  <div className="max-h-[320px] space-y-3 overflow-y-auto pr-2">
                    {suggestionsLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> Fetching
                        repos...
                      </div>
                    ) : suggestions.length === 0 ? (
                      <div className="flex flex-col items-center justify-center gap-4 py-8 text-center">
                        <div className="rounded-full bg-slate-100 p-3 dark:bg-slate-800">
                          <AlertCircle className="h-6 w-6 text-slate-500" />
                        </div>
                        <div className="space-y-1">
                          <p className="font-medium">No repositories found</p>
                        </div>
                      </div>
                    ) : (
                      suggestions.map((repo) => {
                        const checked = Boolean(selectedRepos[repo.full_name]);
                        return (
                          <label
                            key={repo.full_name}
                            className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 hover:bg-slate-50"
                          >
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={checked}
                              onChange={() => toggleSelection(repo)}
                            />
                            <div>
                              <p className="font-medium">
                                {repo.full_name}{" "}
                                {repo.private ? (
                                  <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                                    Private
                                  </span>
                                ) : null}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                {repo.description || "No description provided."}
                              </p>
                            </div>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Configure test frameworks, source languages, and CI provider for each repository.
                  </p>
                  <div className="max-h-[400px] space-y-4 overflow-y-auto pr-2">
                    {selectedList.map((repo) => {
                      const config = repoConfigs[repo.full_name] || {
                        test_frameworks: [],
                        source_languages: [],
                        ci_provider: "github_actions",
                      };

                      const toggleFramework = (framework: string) => {
                        setRepoConfigs((prev) => ({
                          ...prev,
                          [repo.full_name]: {
                            ...config,
                            test_frameworks: config.test_frameworks.includes(framework)
                              ? config.test_frameworks.filter((f) => f !== framework)
                              : [...config.test_frameworks, framework],
                          },
                        }));
                      };

                      const toggleLanguage = (language: string) => {
                        setRepoConfigs((prev) => ({
                          ...prev,
                          [repo.full_name]: {
                            ...config,
                            source_languages: config.source_languages.includes(language)
                              ? config.source_languages.filter((l) => l !== language)
                              : [...config.source_languages, language],
                          },
                        }));
                      };

                      return (
                        <div key={repo.full_name} className="rounded-xl border p-4 space-y-3">
                          <p className="font-semibold">{repo.full_name}</p>

                          <div>
                            <p className="text-sm font-medium mb-2">Test Frameworks</p>
                            <div className="grid grid-cols-2 gap-2">
                              {["PYTEST", "UNITTEST", "RSPEC", "MINITEST", "TESTUNIT", "CUCUMBER"].map((framework) => (
                                <label
                                  key={framework}
                                  className="flex items-center gap-2 text-sm"
                                >
                                  <input
                                    type="checkbox"
                                    checked={config.test_frameworks.includes(framework)}
                                    onChange={() => toggleFramework(framework)}
                                  />
                                  {framework}
                                </label>
                              ))}
                            </div>
                          </div>

                          <div>
                            <p className="text-sm font-medium mb-2">Source Languages</p>
                            <div className="grid grid-cols-2 gap-2">
                              {["PYTHON", "RUBY"].map((language) => (
                                <label
                                  key={language}
                                  className="flex items-center gap-2 text-sm"
                                >
                                  <input
                                    type="checkbox"
                                    checked={config.source_languages.includes(language)}
                                    onChange={() => toggleLanguage(language)}
                                  />
                                  {language}
                                </label>
                              ))}
                            </div>
                          </div>

                          <div>
                            <p className="text-sm font-medium mb-2">CI Provider</p>
                            <select
                              className="w-full rounded-lg border px-3 py-2 text-sm"
                              value={config.ci_provider}
                              onChange={(e) =>
                                setRepoConfigs((prev) => ({
                                  ...prev,
                                  [repo.full_name]: {
                                    ...config,
                                    ci_provider: e.target.value,
                                  },
                                }))
                              }
                            >
                              <option value="github_actions">GitHub Actions</option>
                            </select>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between">
                <Button variant="ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </Button>
                <div className="flex gap-2">
                  {modalStep === 2 ? (
                    <Button variant="outline" onClick={() => setModalStep(1)}>
                      Back
                    </Button>
                  ) : null}
                  {modalStep === 1 ? (
                    <Button
                      onClick={() => setModalStep(2)}
                      disabled={!selectedList.length}
                    >
                      Next
                    </Button>
                  ) : (
                    <Button onClick={handleAddRepos} disabled={addingRepos}>
                      {addingRepos ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        "Connect"
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

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
