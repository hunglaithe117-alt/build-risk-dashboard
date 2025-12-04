"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  GitBranch,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Database,
  Info,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { FeatureSelector } from "./feature-selector";
import { JobList } from "./job-list";
import { datasetApi } from "@/lib/api";
import type {
  AvailableFeaturesResponse,
  DatasetJob,
  DatasetJobListResponse,
  ResolvedDependenciesResponse,
} from "@/types/dataset";
import { SourceLanguage } from "@/types";

type Step = "config" | "features" | "review";

export function DatasetBuilder() {
  // State for wizard steps
  const [currentStep, setCurrentStep] = useState<Step>("config");

  // State for configuration
  const [repoUrl, setRepoUrl] = useState("");
  const [maxBuilds, setMaxBuilds] = useState<number | "">("");
  const [includeMetadata, setIncludeMetadata] = useState(true);
  const [mlOnly, setMlOnly] = useState(false);

  // State for features
  const [featuresData, setFeaturesData] =
    useState<AvailableFeaturesResponse | null>(null);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);
  const [resolvedData, setResolvedData] =
    useState<ResolvedDependenciesResponse | null>(null);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);

  // State for jobs
  const [jobs, setJobs] = useState<DatasetJob[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);

  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load available features
  useEffect(() => {
    const loadFeatures = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await datasetApi.getFeatures(mlOnly);
        setFeaturesData(data);
      } catch (err: any) {
        setError(err.response?.data?.detail || "Failed to load features");
      } finally {
        setIsLoading(false);
      }
    };
    loadFeatures();
  }, [mlOnly]);

  // Ref to track if polling should continue
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Load jobs
  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    try {
      const data = await datasetApi.listJobs(1, 50);
      setJobs(data.items);

      // Check if we need to continue polling
      const hasActiveJobs = data.items.some((j: DatasetJob) =>
        ["pending", "fetching_runs", "processing", "exporting"].includes(
          j.status
        )
      );

      // Set up next poll if there are active jobs
      if (hasActiveJobs && !pollingRef.current) {
        pollingRef.current = setInterval(() => {
          loadJobs();
        }, 10000);
      } else if (!hasActiveJobs && pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    } catch (err) {
      console.error("Failed to load jobs:", err);
    } finally {
      setJobsLoading(false);
    }
  }, []);

  // Initial load and cleanup
  useEffect(() => {
    loadJobs();
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [loadJobs]);

  // Resolve dependencies when features change
  useEffect(() => {
    if (selectedFeatures.length === 0) {
      setResolvedData(null);
      return;
    }

    const resolve = async () => {
      try {
        const data = await datasetApi.resolveFeatures(selectedFeatures);
        setResolvedData(data);
      } catch (err) {
        console.error("Failed to resolve features:", err);
      }
    };

    const timeout = setTimeout(resolve, 300); // Debounce
    return () => clearTimeout(timeout);
  }, [selectedFeatures]);

  // Validate GitHub URL
  const isValidGithubUrl = (url: string) => {
    const patterns = [
      /^https?:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/,
      /^[\w.-]+\/[\w.-]+$/,
    ];
    return patterns.some((p) => p.test(url.trim()));
  };

  // Create job
  const handleCreateJob = async () => {
    if (!isValidGithubUrl(repoUrl)) {
      setError("Please enter a valid GitHub repository URL");
      return;
    }

    if (selectedFeatures.length === 0) {
      setError("Please select at least one feature");
      return;
    }

    // Validate source_languages if required
    if (resolvedData?.requires_source_languages && selectedLanguages.length === 0) {
      setError("Please select at least one source language for the selected features");
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      await datasetApi.createJob({
        repo_url: repoUrl.trim(),
        max_builds: maxBuilds || null,
        feature_ids: selectedFeatures,
        include_metadata: includeMetadata,
        source_languages: selectedLanguages.length > 0 ? selectedLanguages : null,
      });

      // Reset form
      setRepoUrl("");
      setMaxBuilds("");
      setSelectedFeatures([]);
      setSelectedLanguages([]);
      setCurrentStep("config");

      // Refresh jobs list
      loadJobs();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create dataset job");
    } finally {
      setIsCreating(false);
    }
  };

  // Step navigation
  const canProceed = {
    config: isValidGithubUrl(repoUrl),
    features: selectedFeatures.length > 0 && 
      (!resolvedData?.requires_source_languages || selectedLanguages.length > 0),
    review: true,
  };

  const goToStep = (step: Step) => {
    setError(null);
    setCurrentStep(step);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Custom Dataset Builder</h1>
        <p className="text-muted-foreground mt-1">
          Build custom ML datasets from GitHub repositories
        </p>
      </div>

      {/* Wizard */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            {/* Step indicators */}
            {(["config", "features", "review"] as Step[]).map((step, index) => {
              const isActive = currentStep === step;
              const isPast =
                (step === "config" && currentStep !== "config") ||
                (step === "features" && currentStep === "review");

              return (
                <button
                  key={step}
                  onClick={() => isPast && goToStep(step)}
                  disabled={!isPast}
                  className={cn(
                    "flex items-center gap-2 transition-colors",
                    isPast && "cursor-pointer hover:text-foreground",
                    !isPast && !isActive && "cursor-not-allowed"
                  )}
                >
                  <div
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium",
                      isActive
                        ? "bg-blue-600 text-white"
                        : isPast
                        ? "bg-green-600 text-white"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {isPast ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
                  </div>
                  <span
                    className={cn(
                      "text-sm font-medium",
                      isActive
                        ? "text-foreground"
                        : isPast
                        ? "text-muted-foreground"
                        : "text-muted-foreground/50"
                    )}
                  >
                    {step === "config" && "Repository"}
                    {step === "features" && "Features"}
                    {step === "review" && "Review"}
                  </span>
                </button>
              );
            })}
          </div>
        </CardHeader>

        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Step 1: Repository Configuration */}
          {currentStep === "config" && (
            <div className="space-y-6">
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">
                    GitHub Repository URL
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        placeholder="https://github.com/owner/repo or owner/repo"
                        className="pl-10"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Enter a public GitHub repository URL
                  </p>
                </div>

                <div>
                  <label className="text-sm font-medium mb-2 block">
                    Maximum Builds (optional)
                  </label>
                  <Input
                    type="number"
                    value={maxBuilds}
                    onChange={(e) =>
                      setMaxBuilds(
                        e.target.value ? parseInt(e.target.value) : ""
                      )
                    }
                    placeholder="Leave empty for all builds"
                    min={1}
                    max={10000}
                    className="w-48"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Limit the number of builds to process (newest first)
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id="include-metadata"
                    checked={includeMetadata}
                    onCheckedChange={(checked) =>
                      setIncludeMetadata(checked as boolean)
                    }
                  />
                  <label htmlFor="include-metadata" className="text-sm">
                    Include build metadata (commit_sha, build_number,
                    build_status, created_at)
                  </label>
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  onClick={() => goToStep("features")}
                  disabled={!canProceed.config}
                >
                  Continue to Features
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Feature Selection */}
          {currentStep === "features" && (
            <div className="space-y-6">
              {/* Default features notice */}
              {featuresData && featuresData.default_features.length > 0 && (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    <span className="font-medium">Default features:</span>{" "}
                    {featuresData.default_features.join(", ")} are automatically included in every dataset.
                  </AlertDescription>
                </Alert>
              )}

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="ml-only"
                    checked={mlOnly}
                    onCheckedChange={(checked) => setMlOnly(checked as boolean)}
                  />
                  <label htmlFor="ml-only" className="text-sm">
                    Show ML features only
                  </label>
                </div>
                {featuresData && (
                  <div className="text-sm text-muted-foreground">
                    {featuresData.total_features} features available (
                    {featuresData.ml_features_count} ML)
                  </div>
                )}
              </div>

              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : featuresData ? (
                <FeatureSelector
                  categories={featuresData.categories}
                  selectedFeatures={selectedFeatures}
                  onSelectionChange={setSelectedFeatures}
                  mlOnly={mlOnly}
                />
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  Failed to load features
                </div>
              )}

              {/* Resolution preview */}
              {resolvedData && (
                <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
                  <h4 className="font-medium flex items-center gap-2">
                    <Settings2 className="h-4 w-4" />
                    Dependency Resolution
                  </h4>
                  <div className="text-sm text-muted-foreground space-y-1">
                    <p>
                      Selected: {resolvedData.selected_feature_ids.length} →
                      Resolved: {resolvedData.resolved_feature_names.length} features
                    </p>
                    <p>
                      Required extractors:{" "}
                      {resolvedData.required_nodes.join(", ")}
                    </p>
                    <div className="flex gap-2 flex-wrap mt-2">
                      {resolvedData.requires_clone && (
                        <Badge variant="outline" className="text-orange-600">
                          Requires Git Clone
                        </Badge>
                      )}
                      {resolvedData.requires_log_collection && (
                        <Badge variant="outline" className="text-purple-600">
                          Requires Log Collection
                        </Badge>
                      )}
                      {resolvedData.requires_source_languages && (
                        <Badge variant="outline" className="text-amber-600">
                          Requires Source Languages
                        </Badge>
                      )}
                    </div>
                  </div>
                  
                  {/* Language selector for source_languages requirement */}
                  {resolvedData.requires_source_languages && (
                    <div className="mt-4 p-4 rounded-lg border border-amber-500 bg-amber-50 dark:bg-amber-950/30">
                      <div className="flex items-start gap-2 mb-3">
                        <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5" />
                        <div>
                          <p className="font-medium text-amber-800 dark:text-amber-200">
                            Source Languages Required
                          </p>
                          <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                            The following features need language info:{" "}
                            {resolvedData.features_needing_source_languages.join(", ")}
                          </p>
                        </div>
                      </div>
                      
                      <div>
                        <label className="text-xs font-semibold text-amber-800 dark:text-amber-200 uppercase mb-2 block">
                          Select Source Languages
                        </label>
                        <div className="grid grid-cols-3 gap-2">
                          {[SourceLanguage.PYTHON, SourceLanguage.RUBY, SourceLanguage.JAVA].map((lang) => {
                            const isSelected = selectedLanguages.includes(lang);
                            return (
                              <label 
                                key={lang} 
                                className={cn(
                                  "flex items-center gap-2 text-sm cursor-pointer p-2 rounded-md border transition-colors",
                                  isSelected 
                                    ? "bg-amber-100 dark:bg-amber-900 border-amber-500" 
                                    : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-amber-400"
                                )}
                              >
                                <input
                                  type="checkbox"
                                  className="rounded border-gray-300"
                                  checked={isSelected}
                                  onChange={() => {
                                    if (isSelected) {
                                      setSelectedLanguages(prev => prev.filter(l => l !== lang));
                                    } else {
                                      setSelectedLanguages(prev => [...prev, lang]);
                                    }
                                  }}
                                />
                                <span className="capitalize">{lang}</span>
                              </label>
                            );
                          })}
                        </div>
                        {selectedLanguages.length === 0 && (
                          <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                            Please select at least one language to continue
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-between">
                <Button variant="outline" onClick={() => goToStep("config")}>
                  Back
                </Button>
                <Button
                  onClick={() => goToStep("review")}
                  disabled={!canProceed.features}
                >
                  Review & Create
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Review & Create */}
          {currentStep === "review" && (
            <div className="space-y-6">
              <div className="rounded-lg border p-4 space-y-4">
                <h4 className="font-medium">Job Summary</h4>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Repository:</span>
                    <p className="font-mono">{repoUrl}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Max builds:</span>
                    <p>{maxBuilds || "All available"}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">
                      Selected features:
                    </span>
                    <p>{selectedFeatures.length}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">
                      With dependencies:
                    </span>
                    <p>{resolvedData?.resolved_feature_names.length || "-"}</p>
                  </div>
                  {selectedLanguages.length > 0 && (
                    <div className="col-span-2">
                      <span className="text-muted-foreground">
                        Source languages:
                      </span>
                      <div className="flex gap-1 mt-1">
                        {selectedLanguages.map((lang) => (
                          <Badge key={lang} variant="outline" className="capitalize">
                            {lang}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {resolvedData && (
                  <div>
                    <span className="text-sm text-muted-foreground">
                      Features to extract:
                    </span>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {resolvedData.resolved_feature_names.slice(0, 20).map((f) => (
                        <Badge key={f} variant="secondary" className="text-xs">
                          {f}
                        </Badge>
                      ))}
                      {resolvedData.resolved_feature_names.length > 20 && (
                        <Badge variant="secondary" className="text-xs">
                          +{resolvedData.resolved_feature_names.length - 20} more
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-between">
                <Button variant="outline" onClick={() => goToStep("features")}>
                  Back
                </Button>
                <Button
                  onClick={handleCreateJob}
                  disabled={isCreating}
                  className="bg-green-600 hover:bg-green-700"
                >
                  {isCreating ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Database className="h-4 w-4 mr-2" />
                      Create Dataset Job
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Jobs List */}
      <Card>
        <CardContent className="pt-6">
          <JobList jobs={jobs} onRefresh={loadJobs} isLoading={jobsLoading} />
        </CardContent>
      </Card>
    </div>
  );
}
