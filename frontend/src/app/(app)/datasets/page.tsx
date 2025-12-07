"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Map,
  RefreshCw,
  Sparkles,
  Upload,
  Wand2,
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
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { datasetsApi, featuresApi } from "@/lib/api";
import type {
  DatasetRecord,
  DatasetTemplateRecord,
  DatasetUpdatePayload,
  FeatureDefinitionSummary,
} from "@/types";

type MappingKey = "build_id" | "commit_sha" | "repo_name" | "timestamp";

type TemplateCard = Pick<
  DatasetTemplateRecord,
  "id" | "name" | "description" | "tags" | "selected_features"
> & { source: "api" | "fallback" };

const TEMPLATE_FALLBACKS: TemplateCard[] = [
  {
    id: "reliability",
    name: "Build reliability",
    description: "Focus on flakiness, duration, and pass rate insights.",
    tags: ["stability", "tests"],
    selected_features: [
      "build_duration_minutes",
      "failed_test_count",
      "test_flakiness_index",
      "change_failure_rate",
    ],
    source: "fallback",
  },
  {
    id: "delivery",
    name: "Delivery risk",
    description: "Surface lead time, deploy frequency, and change risk.",
    tags: ["velocity", "risk"],
    selected_features: [
      "lead_time",
      "deployment_frequency",
      "commit_churn",
      "change_failure_rate",
    ],
    source: "fallback",
  },
  {
    id: "custom",
    name: "Custom enrichment",
    description: "Pick any feature mix and run ad-hoc experiments.",
    tags: ["custom"],
    selected_features: [],
    source: "fallback",
  },
];

const DATASETS_SEED: DatasetRecord[] = [
  {
    id: "mobile-ci",
    name: "Mobile CI builds Q1",
    description: "CSV export from GitHub Actions pipelines for the mobile app.",
    file_name: "mobile_ci_builds_q1.csv",
    source: "User upload",
    rows: 12844,
    size_mb: 42.1,
    columns: [
      "build_id",
      "repo",
      "commit",
      "branch",
      "status",
      "duration_minutes",
      "started_at",
      "author",
      "tests_failed",
      "tests_total",
      "runner_os",
    ],
    mapped_fields: {
      build_id: "build_id",
      commit_sha: "commit",
      repo_name: "repo",
      timestamp: "started_at",
    },
    stats: {
      coverage: 0.93,
      missing_rate: 0.02,
      duplicate_rate: 0.01,
      build_coverage: 0.88,
    },
    tags: ["CSV", "GitHub Actions", "Mobile"],
    selected_template: "reliability",
    selected_features: [
      "build_duration_minutes",
      "failed_test_count",
      "test_flakiness_index",
      "gh_repo_age",
    ],
    preview: [
      {
        build_id: "GA_235111",
        repo: "app/mobile",
        commit: "3bafc9d",
        status: "success",
        duration_minutes: 12.4,
        started_at: "2024-06-01T07:34:00Z",
      },
      {
        build_id: "GA_235112",
        repo: "app/mobile",
        commit: "1c0d92a",
        status: "failed",
        duration_minutes: 18.2,
        started_at: "2024-06-01T08:12:00Z",
      },
      {
        build_id: "GA_235113",
        repo: "app/mobile",
        commit: "b17f223",
        status: "success",
        duration_minutes: 10.9,
        started_at: "2024-06-01T09:05:00Z",
      },
    ],
  },
  {
    id: "platform-delivery",
    name: "Platform delivery risk",
    description: "Build and commit level signals for the platform services.",
    file_name: "platform_delivery_risk.csv",
    source: "User upload",
    rows: 8341,
    size_mb: 27.3,
    columns: [
      "build_id",
      "repository",
      "commit_sha",
      "status",
      "duration",
      "queued_at",
      "started_at",
      "finished_at",
      "tests_count",
      "tests_failed",
      "trigger",
      "actor",
    ],
    mapped_fields: {
      build_id: "build_id",
      commit_sha: "commit_sha",
      repo_name: "repository",
      timestamp: "started_at",
    },
    stats: {
      coverage: 0.9,
      missing_rate: 0.04,
      duplicate_rate: 0.02,
      build_coverage: 0.82,
    },
    tags: ["Delivery risk", "Backend"],
    selected_template: "delivery",
    selected_features: [
      "lead_time",
      "deployment_frequency",
      "commit_churn",
      "build_duration_minutes",
    ],
    preview: [
      {
        build_id: "CICD_99331",
        repository: "platform/api",
        commit_sha: "8e12b5f",
        status: "success",
        duration: 14.1,
        started_at: "2024-05-12T06:30:00Z",
      },
      {
        build_id: "CICD_99332",
        repository: "platform/api",
        commit_sha: "c7d0f2a",
        status: "failed",
        duration: 22.6,
        started_at: "2024-05-12T08:45:00Z",
      },
      {
        build_id: "CICD_99333",
        repository: "platform/worker",
        commit_sha: "a97d141",
        status: "success",
        duration: 16.3,
        started_at: "2024-05-13T11:10:00Z",
      },
    ],
  },
];

const FALLBACK_FEATURES: FeatureDefinitionSummary[] = [
  {
    id: "build_duration_minutes",
    name: "build_duration_minutes",
    display_name: "Build duration (minutes)",
    description: "Total workflow duration in minutes.",
    category: "build",
    source: "build_log",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "float",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "12.4",
    unit: "minutes",
  },
  {
    id: "failed_test_count",
    name: "failed_test_count",
    display_name: "Failed tests",
    description: "Number of failing tests per build.",
    category: "tests",
    source: "build_log",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "integer",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "3",
    unit: "count",
  },
  {
    id: "test_flakiness_index",
    name: "test_flakiness_index",
    display_name: "Test flakiness index",
    description: "Probability of flaky failures on this dataset.",
    category: "tests",
    source: "aggregates",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "float",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "0.23",
    unit: "ratio",
  },
  {
    id: "gh_repo_age",
    name: "gh_repo_age",
    display_name: "Repo age (days)",
    description: "How long the repository has existed.",
    category: "metadata",
    source: "github",
    extractor_node: "git",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "integer",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "682",
    unit: "days",
  },
  {
    id: "lead_time",
    name: "lead_time",
    display_name: "Lead time",
    description: "Time from commit to deployable build.",
    category: "delivery",
    source: "aggregates",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "float",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "3.2",
    unit: "hours",
  },
  {
    id: "deployment_frequency",
    name: "deployment_frequency",
    display_name: "Deployment frequency",
    description: "How often the service is deployed.",
    category: "delivery",
    source: "aggregates",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "float",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "4.1",
    unit: "per week",
  },
  {
    id: "commit_churn",
    name: "commit_churn",
    display_name: "Commit churn",
    description: "Total lines touched in the change set.",
    category: "git",
    source: "git_diff",
    extractor_node: "git",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "integer",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "221",
    unit: "lines",
  },
  {
    id: "change_failure_rate",
    name: "change_failure_rate",
    display_name: "Change failure rate",
    description: "Build or deploy failures over recent runs.",
    category: "delivery",
    source: "aggregates",
    extractor_node: "build_log",
    depends_on_features: [],
    depends_on_resources: [],
    data_type: "float",
    nullable: false,
    is_active: true,
    is_deprecated: false,
    example_value: "0.18",
    unit: "ratio",
  },
];

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

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetRecord[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [availableFeatures, setAvailableFeatures] = useState<
    FeatureDefinitionSummary[]
  >(FALLBACK_FEATURES);
  const [templates, setTemplates] = useState<TemplateCard[]>(TEMPLATE_FALLBACKS);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [featureLoading, setFeatureLoading] = useState(false);
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [loadingDatasets, setLoadingDatasets] = useState(true);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let active = true;
    const loadDatasets = async () => {
      setLoadingDatasets(true);
      setDatasetError(null);
      try {
        const response = await datasetsApi.list({ limit: 50 });
        const items =
          response.items && response.items.length > 0
            ? response.items
            : DATASETS_SEED;

        if (!active) return;
        if (!response.items || response.items.length === 0) {
          setDatasetError(
            "No datasets returned from the API. Showing sample data."
          );
        }
        setDatasets(items);
        setSelectedDatasetId(items[0]?.id ?? "");
      } catch (err) {
        console.error("Failed to load datasets", err);
        if (active) {
          setDatasetError("Unable to load datasets from API. Using sample data.");
          setDatasets(DATASETS_SEED);
          setSelectedDatasetId(DATASETS_SEED[0]?.id ?? "");
        }
      } finally {
        if (active) {
          setLoadingDatasets(false);
        }
      }
    };

    void loadDatasets();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadFeatures = async () => {
      setFeatureLoading(true);
      setFeatureError(null);
      try {
        const result = await featuresApi.list({ is_active: true });
        if (!active) return;
        if (result.items && result.items.length > 0) {
          setAvailableFeatures(result.items);
        } else {
          setFeatureError("Feature list is empty, using a curated sample.");
          setAvailableFeatures(FALLBACK_FEATURES);
        }
      } catch (err) {
        console.error("Unable to load features from API", err);
        if (active) {
          setFeatureError("Could not reach the feature API, using sample data.");
          setAvailableFeatures(FALLBACK_FEATURES);
        }
      } finally {
        if (active) {
          setFeatureLoading(false);
        }
      }
    };

    void loadFeatures();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadTemplates = async () => {
      setTemplatesLoading(true);
      setTemplateError(null);
      try {
        const result = await datasetsApi.listTemplates();
        if (!active) return;
        if (result.items && result.items.length > 0) {
          setTemplates(
            result.items.map((item) => ({
              id: item.id,
              name: item.name,
              description: item.description,
              tags: item.tags || [],
              selected_features: item.selected_features || [],
              source: "api",
            }))
          );
        } else {
          setTemplateError("No dataset templates returned. Using built-in presets.");
          setTemplates(TEMPLATE_FALLBACKS);
        }
      } catch (err) {
        console.error("Failed to load dataset templates", err);
        if (active) {
          setTemplateError(
            "Unable to load dataset templates from API. Using built-in presets."
          );
          setTemplates(TEMPLATE_FALLBACKS);
        }
      } finally {
        if (active) {
          setTemplatesLoading(false);
        }
      }
    };

    void loadTemplates();
    return () => {
      active = false;
    };
  }, []);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId),
    [datasets, selectedDatasetId]
  );

  const filteredDatasets = useMemo(() => {
    const term = search.toLowerCase().trim();
    if (!term) return datasets;
    return datasets.filter(
      (item) =>
        item.name.toLowerCase().includes(term) ||
        item.file_name.toLowerCase().includes(term) ||
        item.tags.some((tag) => tag.toLowerCase().includes(term))
    );
  }, [datasets, search]);

  const totals = useMemo(() => {
    const count = datasets.length;
    const rows = datasets.reduce((sum, item) => sum + item.rows, 0);
    const coverage =
      count === 0
        ? 0
        : Math.round(
          (datasets.reduce((sum, item) => sum + item.stats.coverage, 0) /
            count) *
          100
        );
    const selectedFeatures = datasets.reduce(
      (sum, item) => sum + item.selected_features.length,
      0
    );

    return { count, rows, coverage, selectedFeatures };
  }, [datasets]);

  const mappingReady = selectedDataset
    ? (["build_id", "commit_sha", "repo_name"] as MappingKey[]).every(
      (key) => selectedDataset.mapped_fields[key]
    )
    : false;

  const featuresByCategory = useMemo(() => {
    return availableFeatures.reduce<Record<string, FeatureDefinitionSummary[]>>(
      (acc, feature) => {
        const bucket = feature.category || "other";
        acc[bucket] = acc[bucket] ? [...acc[bucket], feature] : [feature];
        return acc;
      },
      {}
    );
  }, [availableFeatures]);

  const persistDatasetUpdate = async (
    datasetId: string,
    payload: DatasetUpdatePayload,
    successMessage?: string
  ) => {
    setSaving(true);
    setStatusMessage(null);
    try {
      const updated = await datasetsApi.update(datasetId, payload);
      setDatasets((current) =>
        current.map((item) => (item.id === datasetId ? updated : item))
      );
      if (successMessage) {
        setStatusMessage(successMessage);
      }
    } catch (err) {
      console.error("Failed to save dataset update", err);
      setDatasetError(
        "Unable to save changes to the dataset. Changes are kept locally."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleMappingChange = (field: MappingKey, column: string) => {
    setDatasets((current) =>
      current.map((dataset) =>
        dataset.id === selectedDataset?.id
          ? {
            ...dataset,
            mapped_fields: {
              ...dataset.mapped_fields,
              [field]: column,
            },
          }
          : dataset
      )
    );

    if (selectedDataset?.id) {
      void persistDatasetUpdate(
        selectedDataset.id,
        { mapped_fields: { [field]: column } },
        "Mapping saved"
      );
    }
  };

  const handleFeatureToggle = (featureId: string) => {
    let nextFeatures: string[] | null = null;
    setDatasets((current) =>
      current.map((dataset) => {
        if (dataset.id !== selectedDataset?.id) return dataset;
        const hasFeature = dataset.selected_features.includes(featureId);
        nextFeatures = hasFeature
          ? dataset.selected_features.filter((id) => id !== featureId)
          : [...dataset.selected_features, featureId];
        return {
          ...dataset,
          selected_features: nextFeatures,
        };
      })
    );

    if (selectedDataset?.id && nextFeatures) {
      void persistDatasetUpdate(
        selectedDataset.id,
        { selected_features: nextFeatures },
        "Feature selection updated"
      );
    }
  };

  const handleApplyTemplate = async (templateId: string) => {
    const template = templates.find((item) => item.id === templateId);
    if (!template || !selectedDataset?.id) return;

    const combined = Array.from(
      new Set([
        ...(selectedDataset.selected_features || []),
        ...(template.selected_features || []),
      ])
    );

    setDatasets((current) =>
      current.map((dataset) =>
        dataset.id === selectedDataset.id
          ? {
            ...dataset,
            selected_template: templateId,
            selected_features: combined,
          }
          : dataset
      )
    );

    setSaving(true);
    setStatusMessage(null);
    setDatasetError(null);

    try {
      if (template.source === "api") {
        const updated = await datasetsApi.applyTemplate(
          selectedDataset.id,
          templateId
        );
        setDatasets((current) =>
          current.map((item) => (item.id === selectedDataset.id ? updated : item))
        );
      } else {
        const updated = await datasetsApi.update(selectedDataset.id, {
          selected_template: templateId,
          selected_features: combined,
        });
        setDatasets((current) =>
          current.map((item) => (item.id === selectedDataset.id ? updated : item))
        );
      }
      setStatusMessage(`Applied template "${template.name}".`);
    } catch (err) {
      console.error("Failed to apply template", err);
      setDatasetError("Unable to apply template. Changes are kept locally.");
    } finally {
      setSaving(false);
    }
  };

  const handleUploadChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setDatasetError(null);
    setStatusMessage(null);
    setUploadMessage(null);

    try {
      const created = await datasetsApi.upload(file);
      setDatasets((current) => [created, ...current]);
      setSelectedDatasetId(created.id);
      const sizeMb = file.size / 1024 / 1024;
      setUploadMessage(
        `Uploaded ${file.name} (${sizeMb.toFixed(1)} MB). Saved to dataset catalog.`
      );
    } catch (err) {
      console.error("Dataset upload failed", err);
      setDatasetError("Failed to upload dataset. Please try again.");
    } finally {
      setUploading(false);
      if (event.target) {
        event.target.value = "";
      }
    }
  };

  if (loadingDatasets) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading datasets...</CardTitle>
            <CardDescription>Connecting to the backend API.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Retrieving dataset catalog</span>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!selectedDataset && datasets.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>No datasets available</CardTitle>
            <CardDescription>
              Upload a CSV or seed data via the API to get started.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="border-none bg-gradient-to-r from-slate-900 via-blue-700 to-blue-500 text-white shadow-xl">
        <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="text-2xl">Projects / Datasets</CardTitle>
            <CardDescription className="text-slate-100">
              Upload CSV datasets, map build_id / commit / repo fields, and plan
              feature enrichment.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleUploadChange}
            />
            <Button
              variant="secondary"
              className="gap-2"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Upload className="h-4 w-4" />
              {uploading ? "Uploading..." : "Upload CSV"}
            </Button>
            <Button
              variant="outline"
              className="gap-2 text-white"
              onClick={() =>
                templates[0] && selectedDatasetId
                  ? void handleApplyTemplate(templates[0].id)
                  : undefined
              }
              disabled={!selectedDatasetId || saving}
            >
              <Sparkles className="h-4 w-4" /> Quick start template
            </Button>
          </div>
        </CardHeader>
      </Card>

      {datasetError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
          {datasetError}
        </div>
      ) : null}

      {statusMessage ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200">
          {statusMessage}
        </div>
      ) : null}

      {uploadMessage ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50/70 px-4 py-3 text-sm text-blue-700 dark:border-blue-900/60 dark:bg-blue-900/20 dark:text-blue-100">
          {uploadMessage}
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total datasets
            </CardTitle>
            <Database className="h-5 w-5 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totals.count}</div>
            <p className="text-xs text-muted-foreground">
              Uploaded and ready for mapping
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Rows under management
            </CardTitle>
            <FileSpreadsheet className="h-5 w-5 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatNumber(totals.rows)}</div>
            <p className="text-xs text-muted-foreground">
              Across all build datasets
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Required field coverage
            </CardTitle>
            <Map className="h-5 w-5 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totals.coverage}%</div>
            <p className="text-xs text-muted-foreground">
              build_id, commit, repo mapping readiness
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Features selected
            </CardTitle>
            <Wand2 className="h-5 w-5 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totals.selectedFeatures}</div>
            <p className="text-xs text-muted-foreground">
              Planned for enrichment
            </p>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.05fr_1.2fr]">
        <Card className="h-full">
          <CardHeader className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>Dataset catalog</CardTitle>
                <CardDescription>
                  Review uploaded datasets and pick one to map.
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                <Upload className="h-4 w-4" /> Add dataset
              </Button>
            </div>
            <Input
              placeholder="Search by name, file, or tag..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10"
            />
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="bg-slate-50 dark:bg-slate-900/40">
                  <tr>
                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                      Dataset
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                      Rows
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                      Coverage
                    </th>
                    <th className="px-6 py-3 text-left font-semibold text-slate-500">
                      Updated
                    </th>
                    <th className="px-6 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {filteredDatasets.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-6 py-6 text-center text-sm text-muted-foreground"
                      >
                        No datasets found.
                      </td>
                    </tr>
                  ) : (
                    filteredDatasets.map((dataset) => {
                      const isActive = dataset.id === selectedDataset?.id;
                      return (
                        <tr
                          key={dataset.id}
                          className={`cursor-pointer transition ${isActive
                              ? "bg-blue-50/70 dark:bg-blue-900/20"
                              : "hover:bg-slate-50 dark:hover:bg-slate-900/40"
                            }`}
                          onClick={() => setSelectedDatasetId(dataset.id)}
                        >
                          <td className="px-6 py-4">
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-foreground">
                                  {dataset.name}
                                </span>
                                <Badge variant="secondary">
                                  {dataset.source}
                                </Badge>
                              </div>
                              <p className="text-xs text-muted-foreground">
                                {dataset.file_name}
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {dataset.tags.map((tag) => (
                                  <Badge
                                    key={tag}
                                    variant="outline"
                                    className="text-xs"
                                  >
                                    {tag}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-muted-foreground">
                            {formatNumber(dataset.rows)}
                          </td>
                          <td className="px-6 py-4 text-muted-foreground">
                            {(dataset.stats.coverage * 100).toFixed(0)}%
                          </td>
                          <td className="px-6 py-4 text-muted-foreground">
                            {formatDate(dataset.updated_at || dataset.created_at)}
                          </td>
                          <td className="px-6 py-4">
                            <Button
                              size="sm"
                              variant={isActive ? "default" : "outline"}
                              className="w-full md:w-auto"
                            >
                              {isActive ? "Selected" : "View"}
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {selectedDataset ? (
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="space-y-1">
                  <CardTitle>{selectedDataset.name}</CardTitle>
                  <CardDescription>{selectedDataset.description}</CardDescription>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{selectedDataset.file_name}</Badge>
                    <Badge variant="secondary">
                      {formatNumber(selectedDataset.rows)} rows
                    </Badge>
                    <Badge variant="outline">{selectedDataset.size_mb} MB</Badge>
                  </div>
                </div>
                <div className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs text-muted-foreground">
                  <RefreshCw className="h-4 w-4" />
                  <span>Updated {formatDate(selectedDataset.updated_at)}</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold">Required mapping</p>
                      {mappingReady ? (
                        <div className="flex items-center gap-1 text-xs text-emerald-600">
                          <CheckCircle2 className="h-4 w-4" />
                          <span>Ready</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-xs text-amber-600">
                          <AlertCircle className="h-4 w-4" />
                          <span>Missing</span>
                        </div>
                      )}
                    </div>

                    <div className="space-y-2">
                      {(["build_id", "commit_sha", "repo_name", "timestamp"] as MappingKey[]).map(
                        (field) => (
                          <div key={field} className="space-y-1">
                            <p className="text-xs font-semibold uppercase text-muted-foreground">
                              {field.replace("_", " ")}
                            </p>
                            <Select
                              value={selectedDataset.mapped_fields[field] ?? ""}
                              onValueChange={(value) =>
                                handleMappingChange(field, value)
                              }
                            >
                              <SelectTrigger className="h-9">
                                <SelectValue placeholder="Select column" />
                              </SelectTrigger>
                              <SelectContent>
                                {selectedDataset.columns.map((column) => (
                                  <SelectItem key={column} value={column}>
                                    {column}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )
                      )}
                    </div>
                  </div>

                  <div className="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                    <p className="text-sm font-semibold">Data quality</p>
                    <div className="space-y-2">
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Coverage</span>
                          <span>
                            {(selectedDataset.stats.coverage * 100).toFixed(0)}%
                          </span>
                        </div>
                        <Progress value={selectedDataset.stats.coverage * 100} />
                      </div>
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Missing</span>
                          <span>
                            {(selectedDataset.stats.missing_rate * 100).toFixed(1)}%
                          </span>
                        </div>
                        <Progress
                          value={selectedDataset.stats.missing_rate * 100}
                          className="bg-red-50"
                        />
                      </div>
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Duplicates</span>
                          <span>
                            {(selectedDataset.stats.duplicate_rate * 100).toFixed(1)}%
                          </span>
                        </div>
                        <Progress
                          value={selectedDataset.stats.duplicate_rate * 100}
                          className="bg-amber-50"
                        />
                      </div>
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Build coverage</span>
                          <span>
                            {(selectedDataset.stats.build_coverage * 100).toFixed(0)}%
                          </span>
                        </div>
                        <Progress
                          value={selectedDataset.stats.build_coverage * 100}
                          className="bg-emerald-50"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold">Preview</p>
                    <Badge variant="secondary">
                      {selectedDataset.columns.length} columns
                    </Badge>
                  </div>
                  <div className="mt-3 overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead className="bg-slate-50 text-left text-[11px] uppercase text-muted-foreground dark:bg-slate-900/40">
                        <tr>
                          {Object.keys(selectedDataset.preview[0] ?? {}).map((column) => (
                            <th key={column} className="px-3 py-2">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 text-[13px] dark:divide-slate-800">
                        {selectedDataset.preview.map((row, idx) => (
                          <tr
                            key={idx}
                            className="hover:bg-slate-50 dark:hover:bg-slate-900/40"
                          >
                            {Object.values(row).map((value, cellIdx) => (
                              <td key={cellIdx} className="px-3 py-2 text-muted-foreground">
                                {String(value)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>No dataset selected</CardTitle>
              <CardDescription>Pick a dataset from the list to map fields.</CardDescription>
            </CardHeader>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Feature templates and selection</CardTitle>
            <CardDescription>
              Choose a template or pick individual features to enrich the dataset.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Sparkles className="h-4 w-4" />
            <span>
              Selected: {selectedDataset?.selected_features.length ?? 0} features
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            {templates.map((template) => {
              const active = selectedDataset?.selected_template === template.id;
              return (
                <div
                  key={template.id}
                  className={`rounded-lg border p-3 transition ${active
                      ? "border-blue-500 shadow-sm"
                      : "border-slate-200 dark:border-slate-800"
                    }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-semibold">{template.name}</p>
                      <p className="text-xs text-muted-foreground">{template.description}</p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(template.tags || []).map((tag) => (
                          <Badge key={tag} variant="outline" className="text-[11px]">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    {active ? <CheckCircle2 className="h-5 w-5 text-blue-500" /> : null}
                  </div>
                  <Button
                    size="sm"
                    className="mt-3 w-full"
                    variant={active ? "default" : "outline"}
                    onClick={() => void handleApplyTemplate(template.id)}
                    disabled={!selectedDataset || saving}
                  >
                    {active ? "Template active" : "Apply template"}
                  </Button>
                </div>
              );
            })}
          </div>

          {templateError ? (
            <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
              <AlertCircle className="h-4 w-4" />
              <span>{templateError}</span>
            </div>
          ) : null}
          {templatesLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Loading dataset templates...</span>
            </div>
          ) : null}

          {featureError ? (
            <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
              <AlertCircle className="h-4 w-4" />
              <span>{featureError}</span>
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            {Object.entries(featuresByCategory).map(([category, features]) => (
              <div
                key={category}
                className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-semibold capitalize">{category}</p>
                  <Badge variant="secondary">{features.length} features</Badge>
                </div>
                <div className="space-y-2">
                  {features.map((feature) => {
                    const checked =
                      selectedDataset?.selected_features.includes(feature.id) ?? false;
                    return (
                      <label
                        key={feature.id}
                        className="flex cursor-pointer items-start gap-3 rounded-md border border-transparent px-2 py-2 hover:border-slate-200 dark:hover:border-slate-700"
                      >
                        <Checkbox
                          checked={checked}
                          onChange={() => handleFeatureToggle(feature.id)}
                          disabled={!selectedDataset || saving}
                        />
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold">{feature.display_name}</p>
                            <Badge variant="outline" className="text-[11px]">
                              {feature.data_type}
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {feature.description}
                          </p>
                          <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                            <span>Source: {feature.source}</span>
                            <span>Node: {feature.extractor_node}</span>
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {featureLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Loading feature catalog...</span>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
