"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ValidationStats, RepoValidationResultNew } from "@/types";
import {
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Loader2,
    Play,
    GitBranch
} from "lucide-react";

interface StepValidateProps {
    datasetId: string | null;
    validationStatus: "pending" | "validating" | "completed" | "failed" | "cancelled";
    validationProgress: number;
    validationStats: ValidationStats | null;
    validationError: string | null;
    validatedRepos: RepoValidationResultNew[];
    onStartValidation: () => void;
    onCancelValidation: () => void;
}

export function StepValidate({
    datasetId,
    validationStatus,
    validationProgress,
    validationStats,
    validationError,
    validatedRepos,
    onStartValidation,
    onCancelValidation,
}: StepValidateProps) {
    const isValidating = validationStatus === "validating";
    const isCompleted = validationStatus === "completed";
    const isFailed = validationStatus === "failed";

    return (
        <div className="space-y-6">
            {/* Validation Progress */}
            {validationStatus === "pending" && (
                <div className="text-center py-8">
                    <div className="mx-auto w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mb-4">
                        <Play className="h-8 w-8 text-blue-500" />
                    </div>
                    <h3 className="text-lg font-semibold mb-2">Ready to Validate Builds</h3>
                    <p className="text-sm text-muted-foreground mb-6">
                        Click the button below to validate all build IDs in your dataset
                    </p>
                    <Button onClick={onStartValidation} size="lg" className="gap-2">
                        <Play className="h-4 w-4" /> Start Validation
                    </Button>
                </div>
            )}

            {isValidating && (
                <div className="text-center py-8">
                    <Loader2 className="h-16 w-16 animate-spin text-blue-500 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold mb-2">Validating Builds...</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                        Checking if build IDs exist in CI provider
                    </p>
                    <div className="w-full max-w-md mx-auto">
                        <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-blue-500 transition-all duration-300"
                                style={{ width: `${validationProgress}%` }}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">{validationProgress}% complete</p>
                    </div>
                    <Button variant="outline" onClick={onCancelValidation} className="mt-4">
                        Cancel
                    </Button>
                </div>
            )}

            {isFailed && (
                <div className="text-center py-8">
                    <div className="mx-auto w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mb-4">
                        <XCircle className="h-8 w-8 text-red-500" />
                    </div>
                    <h3 className="text-lg font-semibold mb-2 text-red-600">Validation Failed</h3>
                    <p className="text-sm text-muted-foreground mb-4">{validationError}</p>
                    <Button onClick={onStartValidation} className="gap-2">
                        <Play className="h-4 w-4" /> Retry Validation
                    </Button>
                </div>
            )}

            {validationStatus === "cancelled" && (
                <div className="text-center py-8">
                    <div className="mx-auto w-16 h-16 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mb-4">
                        <AlertTriangle className="h-8 w-8 text-amber-500" />
                    </div>
                    <h3 className="text-lg font-semibold mb-2 text-amber-600">Validation Cancelled</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                        Validation was cancelled. {validationProgress > 0 && `${validationProgress}% was completed.`}
                    </p>
                    <p className="text-xs text-muted-foreground mb-4">
                        Resuming will continue from where it left off.
                    </p>
                    <Button onClick={onStartValidation} className="gap-2">
                        <Play className="h-4 w-4" /> Resume Validation
                    </Button>
                </div>
            )}

            {isCompleted && validationStats && (
                <>
                    {/* Summary Stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <Card className="border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/20">
                            <CardContent className="p-4 text-center">
                                <p className="text-2xl font-bold text-blue-700 dark:text-blue-400">
                                    {validationStats.repos_total}
                                </p>
                                <p className="text-xs text-blue-600">Total Repos</p>
                            </CardContent>
                        </Card>
                        <Card className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20">
                            <CardContent className="p-4 text-center">
                                <CheckCircle2 className="h-5 w-5 text-green-600 mx-auto mb-1" />
                                <p className="text-2xl font-bold text-green-700 dark:text-green-400">
                                    {validationStats.builds_found}
                                </p>
                                <p className="text-xs text-green-600">Valid Builds</p>
                            </CardContent>
                        </Card>
                        <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20">
                            <CardContent className="p-4 text-center">
                                <AlertTriangle className="h-5 w-5 text-amber-600 mx-auto mb-1" />
                                <p className="text-2xl font-bold text-amber-700 dark:text-amber-400">
                                    {validationStats.builds_not_found}
                                </p>
                                <p className="text-xs text-amber-600">Not Found</p>
                            </CardContent>
                        </Card>
                        <Card className="border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
                            <CardContent className="p-4 text-center">
                                <p className="text-2xl font-bold text-slate-700 dark:text-slate-300">
                                    {validationStats.builds_total}
                                </p>
                                <p className="text-xs text-slate-600">Total Builds</p>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Repo Breakdown */}
                    {validatedRepos.length > 0 && (
                        <Card>
                            <CardContent className="p-4">
                                <h3 className="font-medium mb-3">Validation Results by Repository</h3>
                                <div className="max-h-[200px] overflow-y-auto space-y-2">
                                    {validatedRepos.map((repo) => (
                                        <div key={repo.id} className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                                            <div className="flex items-center gap-2">
                                                {repo.validation_status === "valid" ? (
                                                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                                                ) : (
                                                    <XCircle className="h-4 w-4 text-red-500" />
                                                )}
                                                <GitBranch className="h-4 w-4 text-slate-400" />
                                                <span className="text-sm">{repo.full_name}</span>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Badge variant={repo.validation_status === "valid" ? "default" : "destructive"}>
                                                    {repo.builds_found ?? 0}/{(repo.builds_found ?? 0) + (repo.builds_not_found ?? 0)} builds
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Success Message */}
                    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                        <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-600" />
                            <p className="text-sm text-green-700 dark:text-green-300 font-medium">
                                Validation complete! Click "Import Dataset" to proceed.
                            </p>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
