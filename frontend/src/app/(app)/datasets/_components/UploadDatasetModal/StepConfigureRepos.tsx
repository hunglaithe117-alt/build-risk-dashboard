"use client";

import { AlertCircle, CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { CIProvider, CIProviderLabels } from "@/types";
import { cn } from "@/lib/utils";
import type { StepConfigureReposProps } from "./types";

export function StepConfigureRepos({
    uniqueRepos,
    invalidFormatRepos,
    repoConfigs,
    activeRepo,
    availableLanguages,
    languageLoading,
    transitionLoading,
    validReposCount,
    invalidReposCount,
    onActiveRepoChange,
    onToggleLanguage,
    onToggleFramework,
    onSetCiProvider,
    getSuggestedFrameworks,
}: StepConfigureReposProps) {
    if (transitionLoading) {
        return (
            <div className="flex flex-col items-center justify-center gap-6 py-20">
                <Loader2 className="h-16 w-16 animate-spin text-blue-500" />
                <div className="text-center">
                    <p className="text-lg font-semibold">Validating repositories on GitHub...</p>
                    <p className="text-muted-foreground">This may take a few seconds</p>
                </div>
            </div>
        );
    }

    // Get validation icon for a repo
    const getValidationIcon = (repo: string) => {
        const config = repoConfigs[repo];
        if (!config) return null;

        switch (config.validation_status) {
            case "validating":
                return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
            case "valid":
                return <CheckCircle2 className="h-4 w-4 text-green-500" />;
            case "not_found":
            case "error":
                return <XCircle className="h-4 w-4 text-red-500" />;
            default:
                return null;
        }
    };

    return (
        <div className="space-y-4">
            {/* Validation Summary */}
            <div className="flex items-center gap-4 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
                <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    <span className="font-medium">{validReposCount} valid</span>
                </div>
                {invalidReposCount > 0 && (
                    <div className="flex items-center gap-2">
                        <XCircle className="h-5 w-5 text-red-500" />
                        <span className="font-medium text-red-600">{invalidReposCount} not found</span>
                    </div>
                )}
                <span className="text-sm text-muted-foreground ml-auto">
                    {invalidReposCount > 0
                        ? "Invalid repos will be skipped during validation"
                        : "All repositories found on GitHub"}
                </span>
            </div>

            {/* Warning for invalid format repos */}
            {invalidFormatRepos.length > 0 && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Invalid Repository Format</AlertTitle>
                    <AlertDescription>
                        <p className="mb-2">
                            {invalidFormatRepos.length} repo(s) have invalid format. Expected: <code>owner/repo</code>
                        </p>
                        <div className="flex flex-wrap gap-1">
                            {invalidFormatRepos.slice(0, 5).map((r: string) => (
                                <Badge key={r} variant="outline" className="text-xs">{r}</Badge>
                            ))}
                            {invalidFormatRepos.length > 5 && (
                                <Badge variant="outline" className="text-xs">+{invalidFormatRepos.length - 5} more</Badge>
                            )}
                        </div>
                        <p className="mt-2 text-xs">These rows will be skipped during enrichment.</p>
                    </AlertDescription>
                </Alert>
            )}

            <div className="flex gap-6 h-full">
                {/* Repo List */}
                <div className="w-72 flex-shrink-0 border-r pr-4">
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase mb-3">
                        Repositories ({uniqueRepos.length})
                    </h3>
                    <div className="space-y-1 max-h-[300px] overflow-y-auto">
                        {uniqueRepos.map((repo: string) => (
                            <button
                                key={repo}
                                onClick={() => onActiveRepoChange(repo)}
                                className={cn(
                                    "w-full text-left px-3 py-2 rounded-lg text-sm transition flex items-center gap-2",
                                    activeRepo === repo
                                        ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                                        : "hover:bg-slate-100 dark:hover:bg-slate-800",
                                    repoConfigs[repo]?.validation_status === "not_found" || repoConfigs[repo]?.validation_status === "error"
                                        ? "opacity-60"
                                        : ""
                                )}
                            >
                                {getValidationIcon(repo)}
                                <div className="flex-1 min-w-0">
                                    <p className="font-medium truncate">{repo}</p>
                                    {repoConfigs[repo]?.validation_status === "valid" && (
                                        <p className="text-xs text-muted-foreground">
                                            {repoConfigs[repo]?.source_languages?.length || 0} langs, {repoConfigs[repo]?.test_frameworks?.length || 0} frameworks
                                        </p>
                                    )}
                                    {repoConfigs[repo]?.validation_error && (
                                        <p className="text-xs text-red-500 truncate">
                                            {repoConfigs[repo].validation_error}
                                        </p>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Config Panel */}
                <div className="flex-1 space-y-6">
                    {activeRepo && repoConfigs[activeRepo] && (
                        <>
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <h3 className="text-lg font-semibold">{activeRepo}</h3>
                                    {getValidationIcon(activeRepo)}
                                </div>
                                {repoConfigs[activeRepo].validation_status === "valid" ? (
                                    <p className="text-sm text-green-600">✓ Repository exists on GitHub</p>
                                ) : repoConfigs[activeRepo].validation_status === "not_found" ? (
                                    <p className="text-sm text-red-600">✗ Repository not found on GitHub - will be skipped</p>
                                ) : repoConfigs[activeRepo].validation_status === "error" ? (
                                    <p className="text-sm text-red-600">✗ Error validating repo: {repoConfigs[activeRepo].validation_error}</p>
                                ) : (
                                    <p className="text-sm text-muted-foreground">Validating...</p>
                                )}
                            </div>

                            {/* Only show config if repo is valid */}
                            {repoConfigs[activeRepo].validation_status === "valid" && (
                                <>
                                    {/* CI Provider */}
                                    <div className="space-y-2">
                                        <Label>CI Provider</Label>
                                        <Select
                                            value={repoConfigs[activeRepo].ci_provider}
                                            onValueChange={(v) => onSetCiProvider(activeRepo, v as CIProvider)}
                                        >
                                            <SelectTrigger className="w-64">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {Object.values(CIProvider).map((p) => (
                                                    <SelectItem key={p} value={p}>{CIProviderLabels[p]}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Languages */}
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <Label>Source Languages</Label>
                                            {languageLoading[activeRepo] && (
                                                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                                    <Loader2 className="h-3 w-3 animate-spin" /> Detecting...
                                                </span>
                                            )}
                                        </div>
                                        {(availableLanguages[activeRepo]?.length || 0) > 0 ? (
                                            <div className="flex flex-wrap gap-2">
                                                {availableLanguages[activeRepo]?.map((lang: string) => (
                                                    <label
                                                        key={lang}
                                                        className={cn(
                                                            "flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition text-sm",
                                                            repoConfigs[activeRepo].source_languages.includes(lang)
                                                                ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/20"
                                                                : "hover:bg-slate-50 dark:hover:bg-slate-800"
                                                        )}
                                                    >
                                                        <Checkbox
                                                            checked={repoConfigs[activeRepo].source_languages.includes(lang)}
                                                            onCheckedChange={() => onToggleLanguage(activeRepo, lang)}
                                                        />
                                                        {lang}
                                                    </label>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="text-sm text-muted-foreground italic">
                                                No supported languages detected for this repository.
                                            </p>
                                        )}
                                    </div>

                                    {/* Frameworks */}
                                    <div className="space-y-2">
                                        <div className="flex items-center gap-2">
                                            <Label>Test Frameworks</Label>
                                            <Badge variant="outline" className="text-xs">Optional</Badge>
                                        </div>
                                        {repoConfigs[activeRepo].source_languages.length === 0 ? (
                                            <p className="text-sm text-muted-foreground italic">
                                                Select a source language first to see available test frameworks.
                                            </p>
                                        ) : getSuggestedFrameworks(repoConfigs[activeRepo]).length > 0 ? (
                                            <div className="flex flex-wrap gap-2">
                                                {getSuggestedFrameworks(repoConfigs[activeRepo]).map((fw: string) => (
                                                    <label
                                                        key={fw}
                                                        className={cn(
                                                            "flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition text-sm",
                                                            repoConfigs[activeRepo].test_frameworks.includes(fw)
                                                                ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20"
                                                                : "hover:bg-slate-50 dark:hover:bg-slate-800"
                                                        )}
                                                    >
                                                        <Checkbox
                                                            checked={repoConfigs[activeRepo].test_frameworks.includes(fw)}
                                                            onCheckedChange={() => onToggleFramework(activeRepo, fw)}
                                                        />
                                                        {fw}
                                                    </label>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="text-sm text-muted-foreground italic">
                                                No test frameworks available for the selected languages.
                                            </p>
                                        )}
                                    </div>
                                </>
                            )}
                        </>
                    )}

                    {!activeRepo && (
                        <div className="flex items-center justify-center h-full text-muted-foreground">
                            Select a repository to configure
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
