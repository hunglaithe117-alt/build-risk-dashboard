"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { reposApi } from "@/lib/api";
import { RepoDetail } from "@/types";
import { SonarConfigEditor } from "@/components/sonar/sonar-config-editor";
import { FailedScansTable } from "@/components/sonar/failed-scans-table";
import { ScanMetricsTable } from "@/components/sonar/scan-metrics-table";

export default function RepoDetailPage() {
    const params = useParams();
    const router = useRouter();
    const repoId = params.repoId as string;

    const [repo, setRepo] = useState<RepoDetail | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadRepo = async () => {
            try {
                const data = await reposApi.get(repoId);
                setRepo(data);
            } catch (error) {
                console.error(error);
            } finally {
                setLoading(false);
            }
        };
        loadRepo();
    }, [repoId]);

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
                <Card className="w-full max-w-md border-red-200">
                    <CardHeader>
                        <CardTitle>Repository not found</CardTitle>
                    </CardHeader>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push("/admin/repos")}
                        className="gap-2"
                    >
                        <ArrowLeft className="h-4 w-4" />
                        Back to Repos
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">
                            {repo.full_name}
                        </h1>
                        <p className="text-muted-foreground">
                            {repo.description || "No description"}
                        </p>
                    </div>
                </div>
            </div>

            <Tabs defaultValue="builds" className="w-full">
                <TabsList>
                    <TabsTrigger value="builds" onClick={() => router.push(`/admin/repos/${repoId}/builds`)}>
                        Builds
                    </TabsTrigger>
                    <TabsTrigger value="sonar">SonarQube</TabsTrigger>
                    <TabsTrigger value="settings">Settings</TabsTrigger>
                </TabsList>

                <TabsContent value="builds" className="mt-6">
                    {/* This will be rendered via the builds page */}
                </TabsContent>

                <TabsContent value="sonar" className="mt-6 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Configuration</CardTitle>
                            <CardDescription>
                                Manage SonarQube scanning configuration for this repository.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <SonarConfigEditor repoId={repoId} />
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Failed Scans</CardTitle>
                            <CardDescription>
                                Manage failed scans that need configuration fixes.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <FailedScansTable repoId={repoId} />
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Metrics & Results</CardTitle>
                            <CardDescription>
                                View historical scan metrics and code quality data.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <ScanMetricsTable repoId={repoId} />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="settings" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Repository Settings</CardTitle>
                            <CardDescription>
                                Configure repository-specific settings.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <p className="text-muted-foreground">
                                Settings panel can be added here.
                            </p>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
