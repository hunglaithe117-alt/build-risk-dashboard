"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
    ArrowLeft,
    ExternalLink,
    Globe,
    Loader2,
    Lock,
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useWebSocket } from "@/contexts/websocket-context";
import { useToast } from "@/components/ui/use-toast";
import { buildApi, reposApi } from "@/lib/api";
import type { Build, RepoDetail } from "@/types";
import { RepoContext, type ImportProgress, type RepoContextType } from "./repo-context";

export default function RepoLayout({ children }: { children: React.ReactNode }) {
    const params = useParams();
    const router = useRouter();
    const pathname = usePathname();
    const repoId = params.repoId as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [progress, setProgress] = useState<ImportProgress | null>(null);
    const [builds, setBuilds] = useState<Build[]>([]);
    const [loading, setLoading] = useState(true);

    // Action loading states
    const [startProcessingLoading, setStartProcessingLoading] = useState(false);
    const [syncLoading, setSyncLoading] = useState(false);
    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);

    const { subscribe } = useWebSocket();
    const { toast } = useToast();

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

    // WebSocket subscription for REPO_UPDATE
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

    // Listen for INGESTION_ERROR events
    useEffect(() => {
        const handleIngestionError = (event: CustomEvent<{
            repo_id: string;
            resource: string;
            chunk_index: number;
            error: string;
        }>) => {
            // Check if error is for this repo (by id)
            if (repo?.id === event.detail.repo_id) {
                toast({
                    variant: "destructive",
                    title: `Ingestion Error (${event.detail.resource})`,
                    description: event.detail.error.slice(0, 150),
                });
                loadProgress();
            }
        };

        window.addEventListener("INGESTION_ERROR", handleIngestionError as EventListener);
        return () => {
            window.removeEventListener("INGESTION_ERROR", handleIngestionError as EventListener);
        };
    }, [repo?.id, loadProgress, toast]);


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

    // Determine active tab from pathname
    const isOverviewActive = pathname === `/repositories/${repoId}` || pathname.endsWith("/overview");
    const isBuildsActive = pathname.includes("/builds");
    // Check if we're on a build detail page (hide tabs for cleaner UI)
    const isBuildDetailPage = pathname.includes("/build/") && pathname.split("/").length > 4;

    const contextValue: RepoContextType = {
        repo,
        progress,
        builds,
        loading,
        repoId,
        loadRepo,
        loadProgress,
        loadBuilds,
        handleStartProcessing,
        handleSync,
        handleRetryIngestion,
        handleRetryProcessing,
        startProcessingLoading,
        syncLoading,
        retryIngestionLoading,
        retryProcessingLoading,
    };

    return (
        <RepoContext.Provider value={contextValue}>
            <div className="space-y-6">
                {/* Header - simplified on build detail page */}
                {!isBuildDetailPage && (
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
                )}

                {/* Tab Navigation - hide on build detail page */}
                {!isBuildDetailPage && (
                    <div className="border-b">
                        <nav className="flex gap-4">
                            <Link
                                href={`/repositories/${repoId}/overview`}
                                className={cn(
                                    "pb-3 text-sm font-medium transition-colors border-b-2",
                                    isOverviewActive
                                        ? "border-primary text-primary"
                                        : "border-transparent text-muted-foreground hover:text-foreground"
                                )}
                            >
                                Overview
                            </Link>
                            <Link
                                href={`/repositories/${repoId}/builds`}
                                className={cn(
                                    "pb-3 text-sm font-medium transition-colors border-b-2",
                                    isBuildsActive
                                        ? "border-primary text-primary"
                                        : "border-transparent text-muted-foreground hover:text-foreground"
                                )}
                            >
                                Builds
                            </Link>
                        </nav>
                    </div>
                )}

                {/* Page Content */}
                {children}
            </div>
        </RepoContext.Provider>
    );
}
