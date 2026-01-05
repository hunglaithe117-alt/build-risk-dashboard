"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, XCircle, Clock, AlertTriangle, Loader2, ExternalLink, GitCommit } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api/client";

interface CommitScanDetail {
    commit_sha: string;
    trivy: ScanData | null;
    sonarqube: ScanData | null;
    builds: BuildData[];
    builds_count: number;
}

interface ScanData {
    id: string;
    status: string;
    error_message: string | null;
    started_at: string | null;
    completed_at: string | null;
    metrics: Record<string, unknown>;
    scan_duration_ms?: number;
    component_key?: string;
}

interface BuildData {
    id: string;
    ci_run_id: string;
    branch: string;
    conclusion: string;
    web_url: string | null;
    repo_full_name: string;
}

const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
        case "completed":
            return <CheckCircle2 className="h-4 w-4 text-green-500" />;
        case "failed":
            return <XCircle className="h-4 w-4 text-red-500" />;
        case "pending":
            return <Clock className="h-4 w-4 text-yellow-500" />;
        case "in_progress":
            return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
        default:
            return <AlertTriangle className="h-4 w-4 text-muted-foreground" />;
    }
};

const getConclusionBadge = (conclusion: string) => {
    switch (conclusion?.toLowerCase()) {
        case "success":
            return <Badge variant="outline" className="text-green-600 border-green-600">Success</Badge>;
        case "failure":
            return <Badge variant="outline" className="text-red-600 border-red-600">Failure</Badge>;
        case "cancelled":
            return <Badge variant="outline" className="text-yellow-600 border-yellow-600">Cancelled</Badge>;
        default:
            return <Badge variant="outline">{conclusion || "Unknown"}</Badge>;
    }
};

export default function CommitScanDetailPage() {
    const params = useParams();
    const router = useRouter();
    const datasetId = params.datasetId as string;
    const versionId = params.versionId as string;
    const commitSha = params.commitSha as string;

    const [data, setData] = useState<CommitScanDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const response = await api.get<CommitScanDetail>(
                    `/datasets/${datasetId}/versions/${versionId}/commit-scans/${commitSha}`
                );
                setData(response.data);
            } catch (err) {
                setError("Failed to load commit scan details");
                console.error(err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [datasetId, versionId, commitSha]);

    const handleBack = () => {
        router.push(`/projects/${datasetId}/versions/${versionId}/builds/scans`);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !data) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
                <AlertTriangle className="h-12 w-12 text-destructive" />
                <p className="text-muted-foreground">{error || "No data found"}</p>
                <Button variant="outline" onClick={handleBack}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to Scans
                </Button>
            </div>
        );
    }

    const renderMetrics = (metrics: Record<string, unknown>, title: string) => {
        const entries = Object.entries(metrics);
        if (entries.length === 0) {
            return <p className="text-sm text-muted-foreground">No metrics available</p>;
        }

        return (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {entries.map(([key, value]) => (
                    <div key={key} className="p-3 rounded-lg bg-muted/50 border">
                        <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, " ")}</p>
                        <p className="text-lg font-semibold">{String(value)}</p>
                    </div>
                ))}
            </div>
        );
    };

    const renderScanCard = (scan: ScanData | null, title: string, icon: string) => {
        if (!scan) {
            return (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            {icon === "trivy" ? "🛡️" : "📊"} {title}
                        </CardTitle>
                        <CardDescription>No scan data available for this commit</CardDescription>
                    </CardHeader>
                </Card>
            );
        }

        return (
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="text-base flex items-center gap-2">
                                {icon === "trivy" ? "🛡️" : "📊"} {title}
                            </CardTitle>
                            {scan.component_key && (
                                <CardDescription className="font-mono text-xs mt-1">
                                    {scan.component_key}
                                </CardDescription>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            {getStatusIcon(scan.status)}
                            <span className="text-sm capitalize">{scan.status}</span>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    {scan.error_message && (
                        <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                            {scan.error_message}
                        </div>
                    )}
                    <div className="space-y-2">
                        <h4 className="text-sm font-medium">Metrics</h4>
                        {renderMetrics(scan.metrics, title)}
                    </div>
                    {scan.scan_duration_ms && (
                        <p className="text-xs text-muted-foreground">
                            Scan duration: {(scan.scan_duration_ms / 1000).toFixed(2)}s
                        </p>
                    )}
                </CardContent>
            </Card>
        );
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Button variant="ghost" size="icon" onClick={handleBack}>
                    <ArrowLeft className="h-4 w-4" />
                </Button>
                <div>
                    <h1 className="text-xl font-semibold flex items-center gap-2">
                        <GitCommit className="h-5 w-5" />
                        Commit Scan Details
                    </h1>
                    <p className="text-sm text-muted-foreground font-mono">
                        {data.commit_sha}
                    </p>
                </div>
            </div>

            {/* Scan Cards */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {renderScanCard(data.trivy, "Trivy Security Scan", "trivy")}
                {renderScanCard(data.sonarqube, "SonarQube Analysis", "sonar")}
            </div>

            {/* Related Builds */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Related Builds</CardTitle>
                    <CardDescription>
                        {data.builds_count} build{data.builds_count !== 1 ? "s" : ""} using this commit
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {data.builds.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No builds found for this commit</p>
                    ) : (
                        <div className="rounded-md border overflow-hidden">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Build ID</TableHead>
                                        <TableHead>Repository</TableHead>
                                        <TableHead>Branch</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead className="w-16"></TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {data.builds.map((build) => (
                                        <TableRow key={build.id}>
                                            <TableCell className="font-mono text-sm">
                                                {build.ci_run_id}
                                            </TableCell>
                                            <TableCell className="truncate max-w-[200px]">
                                                {build.repo_full_name}
                                            </TableCell>
                                            <TableCell className="text-sm">
                                                {build.branch}
                                            </TableCell>
                                            <TableCell>
                                                {getConclusionBadge(build.conclusion)}
                                            </TableCell>
                                            <TableCell>
                                                {build.web_url && (
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => window.open(build.web_url!, "_blank")}
                                                    >
                                                        <ExternalLink className="h-4 w-4" />
                                                    </Button>
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
