"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Loader2,
    XCircle,
    AlertTriangle,
    Clock,
    RefreshCw,
    RotateCcw,
    Shield,
    BarChart3,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const ITEMS_PER_PAGE = 10;

interface CommitScan {
    id: string;
    commit_sha: string;
    repo_full_name: string;
    status: string;
    error_message: string | null;
    builds_affected: number;
    retry_count: number;
    started_at: string | null;
    completed_at: string | null;
}

interface ScanListResponse {
    items: CommitScan[];
    total: number;
    skip: number;
    limit: number;
}

interface CommitScansResponse {
    trivy?: ScanListResponse;
    sonarqube?: ScanListResponse;
}

function formatDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt || !completedAt) return "-";
    const diff = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (diff < 1000) return `${diff}ms`;
    return `${(diff / 1000).toFixed(1)}s`;
}

export default function ScansPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    const [trivyData, setTrivyData] = useState<ScanListResponse | null>(null);
    const [sonarData, setSonarData] = useState<ScanListResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [retrying, setRetrying] = useState<string | null>(null);
    const [retryAllLoading, setRetryAllLoading] = useState(false);
    const [sonarPage, setSonarPage] = useState(1);
    const [trivyPage, setTrivyPage] = useState(1);
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

    const fetchScans = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            // Fetch trivy scans
            const trivySkip = (trivyPage - 1) * ITEMS_PER_PAGE;
            const trivyRes = await fetch(
                `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans?tool_type=trivy&skip=${trivySkip}&limit=${ITEMS_PER_PAGE}`,
                { credentials: "include" }
            );
            let newTrivyData: ScanListResponse | null = null;
            if (trivyRes.ok) {
                const data = await trivyRes.json();
                newTrivyData = data.trivy || null;
                setTrivyData(newTrivyData);
            }

            // Fetch sonarqube scans
            const sonarSkip = (sonarPage - 1) * ITEMS_PER_PAGE;
            const sonarRes = await fetch(
                `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans?tool_type=sonarqube&skip=${sonarSkip}&limit=${ITEMS_PER_PAGE}`,
                { credentials: "include" }
            );
            let newSonarData: ScanListResponse | null = null;
            if (sonarRes.ok) {
                const data = await sonarRes.json();
                newSonarData = data.sonarqube || null;
                setSonarData(newSonarData);
            }

            // Check for running scans for polling using fresh data
            const allItems = [
                ...(newTrivyData?.items || []),
                ...(newSonarData?.items || []),
            ];
            const hasRunning = allItems.some(
                (s) => s.status === "scanning" || s.status === "pending"
            );
            if (hasRunning && !pollingRef.current) {
                pollingRef.current = setInterval(() => fetchScans(true), 5000);
            } else if (!hasRunning && pollingRef.current) {
                clearInterval(pollingRef.current);
                pollingRef.current = null;
            }
        } catch (err) {
            console.error("Failed to fetch scans:", err);
        } finally {
            if (!silent) setLoading(false);
        }
    }, [datasetId, versionId, trivyPage, sonarPage]);

    useEffect(() => {
        if (versionId) fetchScans();
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [versionId, trivyPage, sonarPage]);

    // Listen for real-time SCAN_UPDATE events
    useEffect(() => {
        const handleScanUpdate = (event: CustomEvent<{
            version_id: string;
            scan_id: string;
            commit_sha: string;
            tool_type: string;
            status: string;
        }>) => {
            if (event.detail.version_id === versionId) {
                // Refresh scans when we receive an update for this version
                fetchScans(true);
            }
        };

        window.addEventListener("SCAN_UPDATE", handleScanUpdate as EventListener);
        return () => {
            window.removeEventListener("SCAN_UPDATE", handleScanUpdate as EventListener);
        };
    }, [versionId, fetchScans]);

    // Listen for SCAN_ERROR events (max retries exhausted)
    useEffect(() => {
        const handleScanError = (event: CustomEvent<{
            version_id: string;
            scan_id: string;
            commit_sha: string;
            tool_type: string;
            error: string;
            retry_count: number;
        }>) => {
            if (event.detail.version_id === versionId) {
                // Refresh when scan permanently fails
                fetchScans(true);
            }
        };

        window.addEventListener("SCAN_ERROR", handleScanError as EventListener);
        return () => {
            window.removeEventListener("SCAN_ERROR", handleScanError as EventListener);
        };
    }, [versionId, fetchScans]);

    const handleRetry = async (commitSha: string, toolType: string) => {
        setRetrying(`${toolType}-${commitSha}`);
        try {
            await fetch(
                `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans/${commitSha}/retry?tool_type=${toolType}`,
                { method: "POST", credentials: "include" }
            );
            await fetchScans();
        } catch (err) {
            console.error("Retry failed:", err);
        } finally {
            setRetrying(null);
        }
    };

    // Calculate failed counts
    const trivyFailedCount = trivyData?.items?.filter(s => s.status === "failed").length || 0;
    const sonarFailedCount = sonarData?.items?.filter(s => s.status === "failed").length || 0;
    const totalFailedCount = trivyFailedCount + sonarFailedCount;

    // Retry all failed scans
    const handleRetryAllFailed = async () => {
        setRetryAllLoading(true);
        try {
            const allFailed: { sha: string; tool: string }[] = [];
            trivyData?.items?.forEach(s => s.status === "failed" && allFailed.push({ sha: s.commit_sha, tool: "trivy" }));
            sonarData?.items?.forEach(s => s.status === "failed" && allFailed.push({ sha: s.commit_sha, tool: "sonarqube" }));

            // Retry in parallel batches
            await Promise.allSettled(
                allFailed.map(({ sha, tool }) =>
                    fetch(
                        `${API_BASE}/datasets/${datasetId}/versions/${versionId}/commit-scans/${sha}/retry?tool_type=${tool}`,
                        { method: "POST", credentials: "include" }
                    )
                )
            );
            await fetchScans();
        } catch (err) {
            console.error("Retry all failed:", err);
        } finally {
            setRetryAllLoading(false);
        }
    };

    const renderStatus = (status: string) => {
        const config: Record<string, { icon: React.ReactNode; variant: "default" | "destructive" | "secondary" | "outline" }> = {
            completed: { icon: <CheckCircle2 className="h-3 w-3" />, variant: "default" },
            failed: { icon: <XCircle className="h-3 w-3" />, variant: "destructive" },
            scanning: { icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "secondary" },
            pending: { icon: <Clock className="h-3 w-3" />, variant: "outline" },
        };
        const c = config[status] || config.pending;
        return (
            <Badge variant={c.variant}>
                <span className="flex items-center gap-1">{c.icon} {status}</span>
            </Badge>
        );
    };

    const renderScanTable = (
        scanData: ScanListResponse | null,
        toolType: string,
        currentPage: number,
        setPage: (page: number) => void
    ) => {
        if (!scanData || scanData.items.length === 0) {
            return <p className="text-sm text-muted-foreground py-4">No scans</p>;
        }

        const { items, total } = scanData;
        const totalPages = Math.ceil(total / ITEMS_PER_PAGE);

        const stats = {
            total: total,
            completed: items.filter(s => s.status === "completed").length,
            failed: items.filter(s => s.status === "failed").length,
            pending: items.filter(s => s.status === "pending" || s.status === "scanning").length,
        };

        return (
            <div className="space-y-2">
                <div className="flex gap-2 text-xs text-muted-foreground mb-2">
                    <span>{stats.total} total</span>
                    <span>•</span>
                    <span className="text-green-600">{stats.completed} completed (page)</span>
                    {stats.failed > 0 && <><span>•</span><span className="text-red-600">{stats.failed} failed (page)</span></>}
                    {stats.pending > 0 && <><span>•</span><span>{stats.pending} pending (page)</span></>}
                </div>
                <div className="border rounded-lg overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Commit</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Builds</TableHead>
                                <TableHead>Duration</TableHead>
                                <TableHead className="w-16"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {items.map((scan) => (
                                <TableRow key={scan.id}>
                                    <TableCell className="font-mono text-xs">
                                        {scan.commit_sha.substring(0, 7)}
                                    </TableCell>
                                    <TableCell>{renderStatus(scan.status)}</TableCell>
                                    <TableCell>{scan.builds_affected}</TableCell>
                                    <TableCell className="text-xs">
                                        {formatDuration(scan.started_at, scan.completed_at)}
                                    </TableCell>
                                    <TableCell>
                                        {scan.status === "failed" && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                disabled={retrying === `${toolType}-${scan.commit_sha}`}
                                                onClick={() => handleRetry(scan.commit_sha, toolType)}
                                            >
                                                {retrying === `${toolType}-${scan.commit_sha}` ? (
                                                    <Loader2 className="h-3 w-3 animate-spin" />
                                                ) : (
                                                    <RotateCcw className="h-3 w-3" />
                                                )}
                                            </Button>
                                        )}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
                {/* Pagination */}
                <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-muted-foreground">
                        Showing {items.length} of {total} scans
                    </p>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage(Math.max(1, currentPage - 1))}
                            disabled={currentPage === 1}
                        >
                            <ChevronLeft className="h-3 w-3" />
                        </Button>
                        <span className="text-xs text-muted-foreground">
                            Page {currentPage} of {Math.max(1, totalPages)}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage(Math.min(totalPages, currentPage + 1))}
                            disabled={currentPage >= totalPages || totalPages <= 1}
                        >
                            <ChevronRight className="h-3 w-3" />
                        </Button>
                    </div>
                </div>
            </div>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin mr-2" />
                <span className="text-muted-foreground">Loading scans...</span>
            </div>
        );
    }

    const hasTrivyScans = trivyData && trivyData.total > 0;
    const hasSonarScans = sonarData && sonarData.total > 0;

    if (!hasTrivyScans && !hasSonarScans) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    No integration scans for this version
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Integration Scans</CardTitle>
                        <CardDescription>
                            SonarQube and Trivy security scans
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRetryAllFailed}
                            disabled={retryAllLoading || totalFailedCount === 0}
                            className={totalFailedCount === 0 ? "opacity-50" : ""}
                        >
                            {retryAllLoading ? (
                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                            ) : (
                                <RotateCcw className="h-4 w-4 mr-1" />
                            )}
                            Retry Failed ({totalFailedCount})
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => fetchScans()}>
                            <RefreshCw className="h-4 w-4 mr-1" />
                            Refresh
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <Tabs defaultValue={hasSonarScans ? "sonarqube" : "trivy"} className="w-full">
                    <TabsList className="mb-4">
                        {hasSonarScans && (
                            <TabsTrigger value="sonarqube" className="flex items-center gap-2">
                                <BarChart3 className="h-4 w-4 text-blue-600" />
                                SonarQube ({sonarData?.total || 0})
                            </TabsTrigger>
                        )}
                        {hasTrivyScans && (
                            <TabsTrigger value="trivy" className="flex items-center gap-2">
                                <Shield className="h-4 w-4 text-green-600" />
                                Trivy ({trivyData?.total || 0})
                            </TabsTrigger>
                        )}
                    </TabsList>

                    {hasSonarScans && (
                        <TabsContent value="sonarqube">
                            {renderScanTable(sonarData, "sonarqube", sonarPage, setSonarPage)}
                        </TabsContent>
                    )}
                    {hasTrivyScans && (
                        <TabsContent value="trivy">
                            {renderScanTable(trivyData, "trivy", trivyPage, setTrivyPage)}
                        </TabsContent>
                    )}
                </Tabs>
            </CardContent>
        </Card>
    );
}
