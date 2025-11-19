"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";

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
  GithubImportJob,
  RepoDetail,
  RepoSuggestion,
  RepoSuggestionResponse,
  RepoUpdatePayload,
  RepoSyncStatus,
  RepositoryRecord,
} from "@/types";

const STATUS_COLORS: Record<RepoSyncStatus, string> = {
  healthy: "bg-emerald-50 text-emerald-700",
  error: "bg-red-50 text-red-600",
  disabled: "bg-slate-100 text-slate-600",
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

export default function AdminReposPage() {
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalStep, setModalStep] = useState<1 | 2>(1);
  const [suggestions, setSuggestions] = useState<RepoSuggestion[]>([]);
  const [initialSuggestions, setInitialSuggestions] = useState<RepoSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedRepos, setSelectedRepos] = useState<
    Record<string, RepoSuggestion>
  >({});
  const [branchPreferences, setBranchPreferences] = useState<
    Record<string, string[]>
  >({});
  const [searchTerm, setSearchTerm] = useState("");
  const [addingRepos, setAddingRepos] = useState(false);
  const [panelRepo, setPanelRepo] = useState<RepoDetail | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelTab, setPanelTab] = useState<"settings" | "history">("settings");
  const [panelForm, setPanelForm] = useState<RepoUpdatePayload>({});
  const [panelBranches, setPanelBranches] = useState<string[]>([]);
  const [panelNotes, setPanelNotes] = useState("");
  const [panelSaving, setPanelSaving] = useState(false);
  const [jobs, setJobs] = useState<GithubImportJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [tableActionId, setTableActionId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const loadRepositories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await reposApi.list();
      setRepositories(data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Unable to load repositories from backend API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRepositories();
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
      if (!normalized) {
        setInitialSuggestions(data.items);
      }
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
      setInitialSuggestions(data.items);
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
      setBranchPreferences({});
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

      monitoring_enabled: panelRepo.monitoring_enabled,

      default_branch: panelRepo.default_branch,

      sync_status: panelRepo.sync_status,

      webhook_status: panelRepo.webhook_status,

      ci_token_status: panelRepo.ci_token_status,

      notes: panelRepo.notes,

    });

    setPanelBranches(panelRepo.tracked_branches ?? []);

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
      } else {
        next[item.full_name] = item;
        setBranchPreferences((current) => {
          if (current[item.full_name]) return current;
          const defaultBranch = item.default_branch || "main";
          return {
            ...current,
            [item.full_name]: [defaultBranch],
          };
        });
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

  const toggleBranchPreference = (repoName: string, branch: string) => {
    setBranchPreferences((prev) => {
      const current = prev[repoName] || [];
      const exists = current.includes(branch);
      const updated = exists
        ? current.filter((item) => item !== branch)
        : [...current, branch];
      return {
        ...prev,
        [repoName]: updated.length ? updated : current,
      };
    });
  };

  const handleAddRepos = async () => {
    if (!selectedList.length) return;
    setAddingRepos(true);
    setFeedback(null);
    try {
      for (const repo of selectedList) {
        const created = await reposApi.import({
          full_name: repo.full_name,
          provider: "github",
          installation_id: repo.installation_id,
        });
        const branches = branchPreferences[repo.full_name]?.length
          ? branchPreferences[repo.full_name]
          : created.default_branch
            ? [created.default_branch]
            : [];
        if (branches.length) {
          await reposApi.update(created.id, {
            tracked_branches: branches,
          });
        }
      }
      await loadRepositories();
      setModalOpen(false);
      setFeedback(
        "Repositories queued for sync. Webhooks will activate after installation."
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
    setPanelTab("settings");
    try {
      const detail = await reposApi.get(repoId);
      setPanelRepo(detail);
      await loadJobs(repoId);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load repository details.");
    } finally {
      setPanelLoading(false);
    }
  };

  const closePanel = () => {
    setPanelRepo(null);
    setJobs([]);
  };

  const loadJobs = async (repoId: string) => {
    setJobsLoading(true);
    try {
      const data = await reposApi.listJobs(repoId);
      setJobs(data);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to load sync history for repository.");
    } finally {
      setJobsLoading(false);
    }
  };

  const handlePanelSave = async () => {
    if (!panelRepo) return;
    setPanelSaving(true);
    try {
      const payload: RepoUpdatePayload = {
        ...panelForm,
        tracked_branches: panelBranches,
        notes: panelNotes || undefined,
      };
      const updated = await reposApi.update(panelRepo.id, payload);
      setPanelRepo(updated);
      await loadRepositories();
      setFeedback("Repository settings updated.");
    } catch (err) {
      console.error(err);
      setFeedback("Unable to save repository settings.");
    } finally {
      setPanelSaving(false);
    }
  };

  const handleSyncNow = async (repo: RepositoryRecord) => {
    setTableActionId(repo.id);
    try {
      await reposApi.scan(repo.id);
      setFeedback(`Queued sync for ${repo.full_name}.`);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to queue sync job.");
    } finally {
      setTableActionId(null);
    }
  };

  const handleDisableMonitoring = async (repo: RepositoryRecord) => {
    try {
      setTableActionId(repo.id);
      await reposApi.update(repo.id, {
        monitoring_enabled: false,
        sync_status: "disabled",
      });
      await loadRepositories();
      setFeedback(`${repo.full_name} monitoring disabled.`);
    } catch (err) {
      console.error(err);
      setFeedback("Unable to update monitoring flag.");
    } finally {
      setTableActionId(null);
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
            <CardTitle>Repository & Data Sync Management</CardTitle>
            <CardDescription>
              Connect GitHub repositories, monitor sync state, and inspect
              ingestion jobs.
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
                    CI provider
                  </th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-500">
                    Sync status
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
                      onClick={() => openPanel(repo.id)}
                    >
                      <td className="px-6 py-4 font-medium text-foreground">
                        {repo.full_name}
                      </td>
                      <td className="px-6 py-4 text-muted-foreground capitalize">
                        {repo.ci_provider.replace("_", " ")}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_COLORS[repo.sync_status]
                            }`}
                        >
                          {repo.sync_status === "healthy"
                            ? "Healthy"
                            : repo.sync_status === "error"
                              ? "Error"
                              : "Disabled"}
                        </span>
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
                            variant="secondary"
                            className="gap-1"
                            disabled={tableActionId === repo.id}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleSyncNow(repo);
                            }}
                          >
                            {tableActionId === repo.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <RefreshCw className="h-4 w-4" />
                            )}
                            Sync now
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(event) => {
                              event.stopPropagation();
                              openPanel(repo.id);
                            }}
                          >
                            Configure
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-600 hover:text-red-700"
                            disabled={tableActionId === repo.id}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleDisableMonitoring(repo);
                            }}
                          >
                            Disable
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
      </Card>

      {modalOpen ? (
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
                        <p className="text-sm text-muted-foreground">
                          You must install the GitHub App to import repositories.
                        </p>
                      </div>
                      <Button
                        variant="default"
                        onClick={() =>
                          window.open(
                            "https://github.com/apps/builddefection",
                            "_blank"
                          )
                        }
                      >
                        Install GitHub App
                      </Button>
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
                              {repo.installed ? (
                                <span className="ml-2 rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                  Connected
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
                  Configure monitoring scope for each repository. BuildGuard
                  currently supports GitHub Actions collectors.
                </p>
                {selectedList.map((repo) => {
                  const branchOptions = Array.from(
                    new Set(
                      [repo.default_branch, "main", "master"].filter(
                        Boolean
                      ) as string[]
                    )
                  );
                  const selectedBranches =
                    branchPreferences[repo.full_name] ||
                    (repo.default_branch ? [repo.default_branch] : ["main"]);
                  return (
                    <div key={repo.full_name} className="rounded-xl border p-4">
                      <p className="font-semibold">{repo.full_name}</p>
                      <p className="text-xs text-muted-foreground">
                        Default branch: {repo.default_branch || "main"}
                      </p>
                      <div className="mt-3 space-y-2">
                        {branchOptions.map((branch) => (
                          <label
                            key={`${repo.full_name}-${branch}`}
                            className="flex items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              checked={selectedBranches.includes(branch)}
                              onChange={() =>
                                toggleBranchPreference(repo.full_name, branch)
                              }
                            />
                            Monitor {branch}
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
                <p className="text-xs text-muted-foreground">
                  Need additional branches? You can configure them after the
                  repository is connected.
                </p>
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
      ) : null}

      {panelRepo ? (
        <div className="fixed inset-0 z-30 flex justify-end bg-black/40">
          <div className="h-full w-full max-w-xl bg-white shadow-2xl dark:bg-slate-950">
            <div className="flex items-center justify-between border-b px-6 py-4">
              <div>
                <p className="text-lg font-semibold">{panelRepo.full_name}</p>
                <p className="text-xs text-muted-foreground">
                  Monitoring {panelRepo.tracked_branches.join(", ") || "main"}
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
                <div className="flex gap-4 border-b px-6 py-3 text-sm">
                  <button
                    type="button"
                    className={`pb-2 font-medium ${panelTab === "settings"
                      ? "text-blue-600"
                      : "text-muted-foreground"
                      }`}
                    onClick={() => setPanelTab("settings")}
                  >
                    Sync Settings
                  </button>
                  <button
                    type="button"
                    className={`pb-2 font-medium ${panelTab === "history"
                      ? "text-blue-600"
                      : "text-muted-foreground"
                      }`}
                    onClick={() => {
                      setPanelTab("history");
                      void loadJobs(panelRepo.id);
                    }}
                  >
                    Sync Job History
                  </button>
                </div>

                {panelTab === "settings" ? (
                  <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
                    <div className="rounded-xl border p-4">
                      <p className="text-sm font-semibold">Connection health</p>
                      <div className="mt-3 grid gap-3 text-sm">
                        <StatusItem
                          label="CI API token"
                          value={
                            panelRepo.ci_token_status === "valid"
                              ? "Valid"
                              : "Missing"
                          }
                          healthy={panelRepo.ci_token_status === "valid"}
                        />
                        <StatusItem
                          label="Webhook"
                          value={
                            panelRepo.webhook_status === "active"
                              ? "Active"
                              : "Inactive"
                          }
                          healthy={panelRepo.webhook_status === "active"}
                        />
                        <div className="flex items-center justify-between rounded-lg border px-3 py-2">
                          <div>
                            <p className="text-sm font-semibold">Monitoring</p>
                            <p className="text-xs text-muted-foreground">
                              {panelForm.monitoring_enabled
                                ? "Enabled"
                                : "Disabled"}
                            </p>
                          </div>
                          <label className="flex items-center gap-2 text-xs font-medium">
                            <input
                              type="checkbox"
                              checked={panelForm.monitoring_enabled ?? true}
                              onChange={(event) =>
                                setPanelForm((prev) => ({
                                  ...prev,
                                  monitoring_enabled: event.target.checked,
                                  sync_status: event.target.checked
                                    ? "healthy"
                                    : "disabled",
                                }))
                              }
                            />
                            Enable
                          </label>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border p-4">
                      <p className="text-sm font-semibold">Branches</p>
                      <div className="mt-3 space-y-2 text-sm">
                        {panelBranches.map((branch) => (
                          <div
                            key={branch}
                            className="flex items-center justify-between rounded-lg border px-3 py-2"
                          >
                            <span>{branch}</span>
                            <button
                              type="button"
                              className="text-xs text-red-500"
                              onClick={() =>
                                setPanelBranches((prev) =>
                                  prev.filter((item) => item !== branch)
                                )
                              }
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                        <form
                          className="flex gap-2"
                          onSubmit={(event) => {
                            event.preventDefault();
                            const formData = new FormData(event.currentTarget);
                            const branch = (
                              formData.get("branch") as string
                            )?.trim();
                            if (!branch) return;
                            setPanelBranches((prev) =>
                              prev.includes(branch) ? prev : [...prev, branch]
                            );
                            event.currentTarget.reset();
                          }}
                        >
                          <input
                            name="branch"
                            placeholder="Add branch"
                            className="flex-1 rounded-lg border px-3 py-2 text-sm"
                          />
                          <Button type="submit" variant="secondary">
                            Add
                          </Button>
                        </form>
                      </div>
                    </div>

                    <div className="rounded-xl border p-4">
                      <label className="text-sm font-semibold" htmlFor="notes">
                        Notes
                      </label>
                      <textarea
                        id="notes"
                        className="mt-2 w-full rounded-lg border px-3 py-2 text-sm"
                        rows={4}
                        value={panelNotes}
                        onChange={(event) => setPanelNotes(event.target.value)}
                        placeholder="Optional notes for your team"
                      />
                    </div>

                    <Button onClick={handlePanelSave} disabled={panelSaving}>
                      {panelSaving ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        "Save changes"
                      )}
                    </Button>
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto px-6 py-4">
                    {jobsLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Loading job history...
                      </div>
                    ) : jobs.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No sync jobs recorded for this repository yet.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {jobs.map((job) => (
                          <div
                            key={job.id}
                            className="rounded-xl border p-4 text-sm"
                          >
                            <div className="flex items-center justify-between">
                              <p className="font-semibold">
                                {job.status.toUpperCase()} •{" "}
                                {formatTimestamp(job.created_at)}
                              </p>
                              <a
                                href={`/admin?job=${job.id}`}
                                className="text-xs text-blue-600 hover:underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                View logs
                              </a>
                            </div>
                            <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                              <p>Builds fetched: {job.builds_imported}</p>
                              <p>Commits: {job.commits_analyzed}</p>
                              <p>
                                Errors:{" "}
                                {job.last_error ? job.last_error : "None"}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StatusItem({
  label,
  value,
  healthy,
}: {
  label: string;
  value: string;
  healthy: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2">
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted-foreground">{value}</p>
      </div>
      {healthy ? (
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      ) : (
        <AlertCircle className="h-4 w-4 text-amber-500" />
      )}
    </div>
  );
}
