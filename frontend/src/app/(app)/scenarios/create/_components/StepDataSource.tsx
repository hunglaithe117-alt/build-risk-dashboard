"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Calendar,
    Check,
    FileCode,
    Filter,
    Loader2,
    Search,
    Upload,
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
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { trainingScenariosApi } from "@/lib/api";
import type { PreviewBuild } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
    useWizard,
    CI_PROVIDERS,
    BUILD_CONCLUSIONS,
    SUPPORTED_LANGUAGES,
    type CIProviderKey,
} from "./WizardContext";

function formatNumber(value: number) {
    return value.toLocaleString("en-US");
}

function getConclusionBadge(conclusion: string) {
    const isSuccess = conclusion === "success";
    return (
        <Badge
            variant="outline"
            className={
                isSuccess
                    ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                    : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
            }
        >
            {conclusion}
        </Badge>
    );
}

export function StepDataSource() {
    const { state, updateDataSource, setPreviewStats, setPreviewRepos, setIsPreviewLoading, setStep } = useWizard();
    const { dataSource, previewStats, isPreviewLoading } = state;

    const [previewBuilds, setPreviewBuilds] = useState<PreviewBuild[]>([]);
    const [page, setPage] = useState(1);
    const [hasApplied, setHasApplied] = useState(false);

    const PAGE_SIZE = 20;

    const applyFilters = useCallback(async (pageNum = 1) => {
        setIsPreviewLoading(true);
        try {
            const params: Record<string, string | boolean | number> = {
                skip: (pageNum - 1) * PAGE_SIZE,
                limit: PAGE_SIZE,
                exclude_bots: true, // Always exclude bots
            };

            if (dataSource.date_start) {
                params.date_start = dataSource.date_start;
            }
            if (dataSource.date_end) {
                params.date_end = dataSource.date_end;
            }
            if (dataSource.languages.length > 0) {
                params.languages = dataSource.languages.join(",");
            }
            if (dataSource.conclusions.length > 0) {
                params.conclusions = dataSource.conclusions.join(",");
            }
            if (dataSource.ci_provider !== "all") {
                params.ci_provider = dataSource.ci_provider;
            }

            const response = await trainingScenariosApi.previewBuilds(params);
            setPreviewBuilds(response.builds);
            setPreviewStats(response.stats);
            // Save repos from preview for per-repo configuration in Step 2
            if (response.stats.repos) {
                setPreviewRepos(response.stats.repos);
            }
            setPage(pageNum);
            setHasApplied(true);
        } catch (error) {
            console.error("Failed to preview builds:", error);
        } finally {
            setIsPreviewLoading(false);
        }
    }, [dataSource, setIsPreviewLoading, setPreviewStats, setPreviewRepos]);

    // Auto-load on mount only if not applied yet
    useEffect(() => {
        if (!hasApplied) {
            applyFilters(1);
        }
    }, [hasApplied, applyFilters]);

    const handleLanguageToggle = (lang: string) => {
        const current = dataSource.languages;
        if (current.includes(lang)) {
            updateDataSource({ languages: current.filter((l) => l !== lang) });
        } else {
            updateDataSource({ languages: [...current, lang] });
        }
    };

    const handleConclusionToggle = (conclusion: string) => {
        const current = dataSource.conclusions;
        if (current.includes(conclusion)) {
            updateDataSource({ conclusions: current.filter((c) => c !== conclusion) });
        } else {
            updateDataSource({ conclusions: [...current, conclusion] });
        }
    };

    const totalBuilds = previewStats?.total_builds ?? 0;
    const totalPages = Math.max(1, Math.ceil(totalBuilds / PAGE_SIZE));

    // YAML Import state
    const [yamlFile, setYamlFile] = useState<File | null>(null);
    const [yamlError, setYamlError] = useState<string | null>(null);
    const [yamlLoaded, setYamlLoaded] = useState(false);

    // Get loadFromYaml from context
    const { loadFromYaml } = useWizard();

    const handleYamlUploadReal = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setYamlFile(file);
        setYamlError(null);
        setYamlLoaded(false);

        try {
            const yaml = await import("js-yaml");
            const text = await file.text();
            const parsed = yaml.load(text) as any;

            // Validate required fields
            if (!parsed.scenario?.name) {
                setYamlError("Missing required field: scenario.name");
                return;
            }

            // Load into wizard state
            loadFromYaml(parsed);
            setYamlLoaded(true);

            // Trigger preview with loaded filters
            setTimeout(() => applyFilters(1), 100);
        } catch (err) {
            setYamlError(`YAML parse error: ${(err as Error).message}`);
        }
    };

    const handleSkipToReview = () => {
        setStep(5);
    };

    return (
        <div className="space-y-6">
            {/* YAML Import Card */}
            <Card className="border-dashed border-purple-500/50">
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <FileCode className="h-5 w-5 text-purple-500" />
                        Import from YAML
                    </CardTitle>
                    <CardDescription>
                        Upload a YAML config file to auto-fill all settings
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4">
                        <label className="flex-1">
                            <input
                                type="file"
                                accept=".yaml,.yml"
                                onChange={handleYamlUploadReal}
                                className="hidden"
                            />
                            <div className="flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed rounded-lg cursor-pointer hover:border-purple-500 hover:bg-purple-500/5 transition-colors">
                                <Upload className="h-4 w-4 text-muted-foreground" />
                                <span className="text-sm text-muted-foreground">
                                    {yamlFile ? yamlFile.name : "Choose YAML file..."}
                                </span>
                            </div>
                        </label>
                        {yamlLoaded && (
                            <Button
                                onClick={handleSkipToReview}
                                className="bg-purple-600 hover:bg-purple-700"
                            >
                                Skip to Review
                            </Button>
                        )}
                    </div>
                    {yamlError && (
                        <p className="mt-2 text-sm text-red-500">{yamlError}</p>
                    )}
                    {yamlLoaded && (
                        <p className="mt-2 text-sm text-green-500">
                            ✓ YAML loaded successfully! Review preview below or skip to review.
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Filters Panel */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Filter className="h-5 w-5" />
                        Data Source Filters
                    </CardTitle>
                    <CardDescription>
                        Configure filters to select builds from the database for your scenario
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Date Range */}
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label className="flex items-center gap-2">
                                <Calendar className="h-4 w-4" />
                                Start Date
                            </Label>
                            <Input
                                type="date"
                                value={dataSource.date_start}
                                onChange={(e) => updateDataSource({ date_start: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="flex items-center gap-2">
                                <Calendar className="h-4 w-4" />
                                End Date
                            </Label>
                            <Input
                                type="date"
                                value={dataSource.date_end}
                                onChange={(e) => updateDataSource({ date_end: e.target.value })}
                            />
                        </div>
                    </div>

                    {/* Languages */}
                    <div className="space-y-2">
                        <Label>Languages</Label>
                        <div className="flex flex-wrap gap-3">
                            {SUPPORTED_LANGUAGES.map((lang) => (
                                <div key={lang.value} className="flex items-center space-x-2">
                                    <Checkbox
                                        id={`lang-${lang.value}`}
                                        checked={dataSource.languages.includes(lang.value)}
                                        onCheckedChange={() => handleLanguageToggle(lang.value)}
                                    />
                                    <label
                                        htmlFor={`lang-${lang.value}`}
                                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                    >
                                        {lang.label}
                                    </label>
                                </div>
                            ))}
                        </div>
                        {dataSource.languages.length === 0 && (
                            <p className="text-xs text-muted-foreground">All languages selected</p>
                        )}
                    </div>

                    {/* Conclusions */}
                    <div className="space-y-2">
                        <Label>Build Conclusions</Label>
                        <div className="flex flex-wrap gap-4">
                            {BUILD_CONCLUSIONS.map((c) => (
                                <div key={c.value} className="flex items-center space-x-2">
                                    <Checkbox
                                        id={`conclusion-${c.value}`}
                                        checked={dataSource.conclusions.includes(c.value)}
                                        onCheckedChange={() => handleConclusionToggle(c.value)}
                                    />
                                    <label
                                        htmlFor={`conclusion-${c.value}`}
                                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                    >
                                        {c.label}
                                    </label>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* CI Provider */}
                    <div className="space-y-2">
                        <Label>CI Provider</Label>
                        <Select
                            value={dataSource.ci_provider}
                            onValueChange={(value) => updateDataSource({ ci_provider: value as CIProviderKey | "all" })}
                        >
                            <SelectTrigger className="w-[250px]">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All Providers</SelectItem>
                                {CI_PROVIDERS.map((provider) => (
                                    <SelectItem key={provider.value} value={provider.value}>
                                        {provider.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Apply Button */}
                    <div className="flex justify-end">
                        <Button
                            onClick={() => applyFilters(1)}
                            disabled={isPreviewLoading}
                            className="gap-2"
                        >
                            {isPreviewLoading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Search className="h-4 w-4" />
                            )}
                            Apply Filters
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Preview Table for DB */}
            {previewStats && (
                <>
                    <div className="grid gap-4 md:grid-cols-4">
                        <Card>
                            <CardContent className="pt-6">
                                <div className="text-2xl font-bold">{formatNumber(previewStats.total_builds)}</div>
                                <p className="text-xs text-muted-foreground">Total Builds</p>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <div className="text-2xl font-bold">{formatNumber(previewStats.total_repos)}</div>
                                <p className="text-xs text-muted-foreground">Repositories</p>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <div className="text-2xl font-bold text-green-600">
                                    {formatNumber(previewStats.outcome_distribution.success)}
                                </div>
                                <p className="text-xs text-muted-foreground">Success</p>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <div className="text-2xl font-bold text-red-600">
                                    {formatNumber(previewStats.outcome_distribution.failure)}
                                </div>
                                <p className="text-xs text-muted-foreground">Failure</p>
                            </CardContent>
                        </Card>
                    </div>

                    <Card>
                        <CardHeader>
                            <CardTitle>Build Preview</CardTitle>
                            <CardDescription>
                                Sample of builds matching your filters
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                                    <thead className="bg-slate-50 dark:bg-slate-900/40">
                                        <tr>
                                            <th className="px-4 py-3 text-left font-semibold text-slate-500">Repository</th>
                                            <th className="px-4 py-3 text-left font-semibold text-slate-500">Branch</th>
                                            <th className="px-4 py-3 text-left font-semibold text-slate-500">Commit</th>
                                            <th className="px-4 py-3 text-left font-semibold text-slate-500">Conclusion</th>
                                            <th className="px-4 py-3 text-left font-semibold text-slate-500">Date</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                        {isPreviewLoading ? (
                                            <tr>
                                                <td colSpan={5} className="px-4 py-8 text-center">
                                                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                                                </td>
                                            </tr>
                                        ) : previewBuilds.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                                                    No builds match your filters
                                                </td>
                                            </tr>
                                        ) : (
                                            previewBuilds.map((build) => (
                                                <tr key={build.id}>
                                                    <td className="px-4 py-3 font-medium">{build.repo_name}</td>
                                                    <td className="px-4 py-3 text-muted-foreground">{build.branch}</td>
                                                    <td className="px-4 py-3 font-mono text-xs">{build.commit_sha}</td>
                                                    <td className="px-4 py-3">{getConclusionBadge(build.conclusion)}</td>
                                                    <td className="px-4 py-3 text-muted-foreground">
                                                        {formatDateTime(build.run_started_at)}
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                            {totalBuilds > PAGE_SIZE && (
                                <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-800">
                                    <span className="text-sm text-muted-foreground">
                                        Page {page} of {totalPages}
                                    </span>
                                    <div className="flex gap-2">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => applyFilters(page - 1)}
                                            disabled={page === 1 || isPreviewLoading}
                                        >
                                            Previous
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => applyFilters(page + 1)}
                                            disabled={page >= totalPages || isPreviewLoading}
                                        >
                                            Next
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </>
            )}

            {/* Navigation */}
            <div className="flex justify-end">
                <Button
                    onClick={() => setStep(2)}
                    disabled={
                        !previewStats || previewStats.total_builds === 0 || isPreviewLoading
                    }
                    className="gap-2"
                >
                    Next: Feature Config
                    <Check className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
}
