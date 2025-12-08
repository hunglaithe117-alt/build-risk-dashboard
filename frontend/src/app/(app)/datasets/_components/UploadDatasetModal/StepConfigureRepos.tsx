"use client";

import { Loader2 } from "lucide-react";

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
    repoConfigs,
    activeRepo,
    availableLanguages,
    languageLoading,
    transitionLoading,
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
                    <p className="text-lg font-semibold">Detecting repository languages...</p>
                    <p className="text-muted-foreground">This may take a few seconds</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex gap-6 h-full">
            {/* Repo List */}
            <div className="w-64 flex-shrink-0 border-r pr-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase mb-3">
                    Repositories ({uniqueRepos.length})
                </h3>
                <div className="space-y-1">
                    {uniqueRepos.map((repo) => (
                        <button
                            key={repo}
                            onClick={() => onActiveRepoChange(repo)}
                            className={cn(
                                "w-full text-left px-3 py-2 rounded-lg text-sm transition",
                                activeRepo === repo
                                    ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                                    : "hover:bg-slate-100 dark:hover:bg-slate-800"
                            )}
                        >
                            <p className="font-medium truncate">{repo}</p>
                            <p className="text-xs text-muted-foreground">
                                {repoConfigs[repo]?.source_languages?.length || 0} langs, {repoConfigs[repo]?.test_frameworks?.length || 0} frameworks
                            </p>
                        </button>
                    ))}
                </div>
            </div>

            {/* Config Panel */}
            <div className="flex-1 space-y-6">
                {activeRepo && repoConfigs[activeRepo] && (
                    <>
                        <div>
                            <h3 className="text-lg font-semibold mb-1">{activeRepo}</h3>
                            <p className="text-sm text-muted-foreground">Configure languages, frameworks, and CI provider</p>
                        </div>

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
                                    {availableLanguages[activeRepo]?.map((lang) => (
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
                                    {getSuggestedFrameworks(repoConfigs[activeRepo]).map((fw) => (
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
            </div>
        </div>
    );
}
