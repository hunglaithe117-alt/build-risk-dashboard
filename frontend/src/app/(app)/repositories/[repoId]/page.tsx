"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
    ArrowLeft,
    ExternalLink,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWebSocket } from "@/contexts/websocket-context";
import { buildApi, reposApi } from "@/lib/api";
import type { Build, RepoDetail } from "@/types";

import { OverviewTab } from "./_tabs/OverviewTab";
import { BuildsTab } from "./_tabs/BuildsTab";
import { IssuesTab } from "./_tabs/IssuesTab";


interface ImportProgress {
    // Checkpoint info (if processing was started)
    checkpoint: {
        has_checkpoint: boolean;
        last_checkpoint_at: string | null;
        accepted_failed: number;
        stats: Record<string, number>;
    };
    // Total import builds (all batches)
    import_builds: {
        pending: number;
        fetched: number;
        ingesting: number;
        ingested: number;
        missing_resource: number;
        total: number;
    };
    resource_status?: Record<string, Record<string, number>>;
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
    const searchParams = useSearchParams();
    const repoId = params.repoId as string;

    // Read tab from URL or default to "overview"
    const tabFromUrl = searchParams.get("tab") || "overview";
    const validTabs = ["overview", "builds", "issues"];
    const currentTab = validTabs.includes(tabFromUrl) ? tabFromUrl : "overview";

    const handleTabChange = (value: string) => {
        router.push(`/repositories/${repoId}?tab=${value}`, { scroll: false });
    };

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [progress, setProgress] = useState<ImportProgress | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loading, setLoading] = useState(true);
    const [progressLoading, setProgressLoading] = useState(true);

    // Action loading states
    const [startProcessingLoading, setStartProcessingLoading] = useState(false);
    const [syncLoading, setSyncLoading] = useState(false);
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);

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
                checkpoint: data.checkpoint,
                import_builds: data.import_builds,
                resource_status: data.resource_status,
                training_builds: data.training_builds,
            });
        } catch (err) {
            console.error(err);
        } finally {
            setProgressLoading(false);
        }
    }, [repoId]);

    const loadBuilds = useCallback(async () => {
        try {
            const data = await buildApi.getByRepo(repoId, { skip: 0, limit: 5 });
            setBuilds(data.items);
        } catch (err) {
            console.error(err);
        }
    }, [repoId]);

    useEffect(() => {
        loadRepo();
        loadProgress();
        loadBuilds();
    }, [loadRepo, loadProgress, loadBuilds]);

    // WebSocket subscription
    useEffect(() => {
        const unsubscribe = subscribe("REPO_UPDATE", (data: any) => {
            if (data.repo_id === repoId) {
                loadRepo();
                loadProgress();
                loadBuilds();
            }
        });
        return () => unsubscribe();
    }, [subscribe, loadRepo, loadProgress, loadBuilds, repoId]);

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

            {/* Tabs */}
            <Tabs value={currentTab} onValueChange={handleTabChange} className="space-y-6">
                <TabsList className="w-full grid grid-cols-3">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="builds">Builds</TabsTrigger>
                    <TabsTrigger value="issues" className="gap-1">
                        Issues
                        {((progress?.import_builds.missing_resource || 0) + (progress?.training_builds.failed || 0) + (progress?.training_builds.prediction_failed || 0)) > 0 && (
                            <Badge variant="destructive" className="ml-1 h-5 px-1.5 text-xs">
                                {(progress?.import_builds.missing_resource || 0) + (progress?.training_builds.failed || 0) + (progress?.training_builds.prediction_failed || 0)}
                            </Badge>
                        )}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-6">
                    <OverviewTab
                        repo={repo}
                        progress={progress}
                        builds={builds}
                        onSync={handleSync}
                        onRetryIngestion={handleRetryIngestion}
                        onStartProcessing={handleStartProcessing}
                        onRetryFailed={handleRetryProcessing}
                        syncLoading={syncLoading}
                        retryIngestionLoading={retryIngestionLoading}
                        startProcessingLoading={startProcessingLoading}
                        retryFailedLoading={retryProcessingLoading}
                    />
                </TabsContent>

                <TabsContent value="builds">
                    <BuildsTab repoId={repoId} repoName={repo.full_name} />
                </TabsContent>

                <TabsContent value="issues">
                    <IssuesTab
                        repoId={repoId}
                        failedIngestionCount={progress?.import_builds.missing_resource || 0}
                        failedExtractionCount={progress?.training_builds.failed || 0}
                        failedPredictionCount={progress?.training_builds.prediction_failed || 0}
                        onRetryIngestion={handleRetryIngestion}
                        onRetryFailed={handleRetryProcessing}
                        retryIngestionLoading={retryIngestionLoading}
                        retryFailedLoading={retryProcessingLoading}
                    />
                </TabsContent>
            </Tabs>
        </div>
    );
}
