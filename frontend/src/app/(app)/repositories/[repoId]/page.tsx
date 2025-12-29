"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
    ArrowLeft,
    ArrowRight,
    ExternalLink,
    GitBranch,
    Globe,
    Loader2,
    Lock,
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
import { useWebSocket } from "@/contexts/websocket-context";
import { reposApi } from "@/lib/api";
import { formatTimestamp } from "@/lib/utils";
import type { RepoDetail } from "@/types";

import { ActionPanel } from "../_components/ActionPanel";
import { CurrentPhaseCard } from "../_components/CurrentPhaseCard";
import { PipelineStepper } from "../_components/PipelineStepper";

interface ImportProgress {
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        failed: number;
        total: number;
    };
    training_builds: {
        pending: number;
        completed: number;
        partial: number;
        failed: number;
        total: number;
        with_prediction?: number;
        pending_prediction?: number;
        prediction_failed?: number;
    };
}

export default function RepoDetailPage() {
    const params = useParams();
    const router = useRouter();
    const repoId = params.repoId as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [progress, setProgress] = useState<ImportProgress | null>(null);
    const [loading, setLoading] = useState(true);
    const [progressLoading, setProgressLoading] = useState(true);

    // Action loading states
    const [startProcessingLoading, setStartProcessingLoading] = useState(false);
    const [syncLoading, setSyncLoading] = useState(false);
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);
    const [retryPredictionLoading, setRetryPredictionLoading] = useState(false);

    const { subscribe } = useWebSocket();

    const loadRepo = useCallback(async () => {
        try {
            const data = await reposApi.get(repoId);
            setRepo(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [repoId]);

    const loadProgress = useCallback(async () => {
        try {
            const data = await reposApi.getImportProgress(repoId);
            setProgress({
                import_builds: data.import_builds,
                training_builds: data.training_builds,
            });
        } catch (err) {
            console.error(err);
        } finally {
            setProgressLoading(false);
        }
    }, [repoId]);

    useEffect(() => {
        loadRepo();
        loadProgress();
    }, [loadRepo, loadProgress]);

    // WebSocket subscription for repo updates
    useEffect(() => {
        const unsubscribe = subscribe("REPO_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                loadRepo();
                loadProgress();
            }
        });

        return () => {
            unsubscribe();
        };
    }, [subscribe, loadRepo, loadProgress, repoId]);

    // Action handlers
    const handleStartProcessing = async () => {
        setStartProcessingLoading(true);
        try {
            await reposApi.startProcessing(repoId);
            loadRepo();
            loadProgress();
        } catch (err) {
            console.error(err);
        } finally {
            setStartProcessingLoading(false);
        }
    };

    const handleSync = async () => {
        setSyncLoading(true);
        try {
            await reposApi.triggerLazySync(repoId);
            loadRepo();
        } catch (err) {
            console.error(err);
        } finally {
            setSyncLoading(false);
        }
    };

    const handleRetryIngestion = async () => {
        setRetryIngestionLoading(true);
        try {
            await reposApi.reingestFailed(repoId);
            loadRepo();
            loadProgress();
        } catch (err) {
            console.error(err);
        } finally {
            setRetryIngestionLoading(false);
        }
    };

    const handleRetryProcessing = async () => {
        setRetryProcessingLoading(true);
        try {
            await reposApi.reprocessFailed(repoId);
            loadRepo();
            loadProgress();
        } catch (err) {
            console.error(err);
        } finally {
            setRetryProcessingLoading(false);
        }
    };

    const handleRetryPrediction = async () => {
        setRetryPredictionLoading(true);
        try {
            await reposApi.retryPredictions(repoId);
            loadRepo();
            loadProgress();
        } catch (err) {
            console.error(err);
        } finally {
            setRetryPredictionLoading(false);
        }
    };

    const handleRetryFailed = () => {
        const status = repo?.status?.toLowerCase() || "";
        if (status === "ingestion_partial") {
            handleRetryIngestion();
        } else if (status === "partial" || status === "failed") {
            handleRetryProcessing();
        }
    };

    if (loading) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!repo) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <CardTitle>Repository not found</CardTitle>
                        <CardDescription>
                            The repository you are looking for does not exist.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button onClick={() => router.push("/repositories")}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back to Repositories
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const hasIngestionFailed = (progress?.import_builds.failed || 0) > 0;
    const hasProcessingFailed = (progress?.training_builds.failed || 0) > 0;
    const hasPredictionFailed = (progress?.training_builds.prediction_failed || 0) > 0;
    const hasFailed = hasIngestionFailed || hasProcessingFailed || hasPredictionFailed;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push("/repositories")}
                        className="gap-2"
                    >
                        <ArrowLeft className="h-4 w-4" />
                        Back
                    </Button>
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-2xl font-bold tracking-tight">
                                {repo.full_name}
                            </h1>
                            <Badge
                                variant={repo.is_private ? "secondary" : "outline"}
                                className="gap-1"
                            >
                                {repo.is_private ? (
                                    <Lock className="h-3 w-3" />
                                ) : (
                                    <Globe className="h-3 w-3" />
                                )}
                                {repo.is_private ? "Private" : "Public"}
                            </Badge>
                        </div>
                        {repo.metadata?.description && (
                            <p className="text-muted-foreground mt-1">
                                {repo.metadata.description}
                            </p>
                        )}
                    </div>
                </div>
                {repo.metadata?.html_url && (
                    <a
                        href={repo.metadata.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <ExternalLink className="h-4 w-4" />
                        View on GitHub
                    </a>
                )}
            </div>

            {/* Pipeline Stepper */}
            <Card>
                <CardHeader className="pb-4">
                    <CardTitle className="text-lg">Pipeline Progress</CardTitle>
                    <CardDescription>
                        Track the import and processing pipeline for this repository
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <PipelineStepper status={repo.status} progress={progress} />
                </CardContent>
            </Card>

            {/* Current Phase + Actions */}
            <div className="grid gap-6 md:grid-cols-3">
                <div className="md:col-span-2">
                    <CurrentPhaseCard
                        status={repo.status}
                        progress={progress}
                        isLoading={progressLoading}
                        onRetryFailed={hasFailed ? handleRetryFailed : undefined}
                    />
                </div>
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-lg">Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                        <ActionPanel
                            status={repo.status}
                            hasFailed={hasFailed}
                            hasIngestionFailed={hasIngestionFailed}
                            hasProcessingFailed={hasProcessingFailed}
                            hasPredictionFailed={hasPredictionFailed}
                            isStartProcessingLoading={startProcessingLoading}
                            isSyncLoading={syncLoading}
                            isRetryIngestionLoading={retryIngestionLoading}
                            isRetryProcessingLoading={retryProcessingLoading}
                            isRetryPredictionLoading={retryPredictionLoading}
                            onStartProcessing={handleStartProcessing}
                            onSync={handleSync}
                            onRetryIngestion={handleRetryIngestion}
                            onRetryProcessing={handleRetryProcessing}
                            onRetryPrediction={handleRetryPrediction}
                        />
                    </CardContent>
                </Card>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Fetched</CardDescription>
                        <CardTitle className="text-2xl">
                            {repo.builds_fetched.toLocaleString()}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Ingested</CardDescription>
                        <CardTitle className="text-2xl">
                            {(progress?.import_builds.ingested || 0).toLocaleString()}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Processed</CardDescription>
                        <CardTitle className="text-2xl">
                            {(repo.builds_processed || 0).toLocaleString()}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Failed</CardDescription>
                        <CardTitle className="text-2xl text-red-600">
                            {(repo.builds_failed || 0).toLocaleString()}
                        </CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Repository Info */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-lg">Repository Info</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-6 text-sm">
                        <div className="flex items-center gap-2">
                            <GitBranch className="h-4 w-4 text-muted-foreground" />
                            <span className="text-muted-foreground">Default branch:</span>
                            <span className="font-medium">{repo.default_branch || "main"}</span>
                        </div>
                        {repo.main_lang && (
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Language:</span>
                                <Badge variant="outline">{repo.main_lang}</Badge>
                            </div>
                        )}
                        <div className="flex items-center gap-2">
                            <span className="text-muted-foreground">CI Provider:</span>
                            <Badge variant="outline">{repo.ci_provider}</Badge>
                        </div>
                        {repo.last_synced_at && (
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">Last synced:</span>
                                <span className="font-medium">
                                    {formatTimestamp(repo.last_synced_at)}
                                </span>
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* View Builds Link */}
            <div className="flex justify-center">
                <Button
                    variant="outline"
                    onClick={() => router.push(`/repositories/${repoId}/builds`)}
                    className="gap-2"
                >
                    View All Builds
                    <ArrowRight className="h-4 w-4" />
                </Button>
            </div>
        </div>
    );
}
