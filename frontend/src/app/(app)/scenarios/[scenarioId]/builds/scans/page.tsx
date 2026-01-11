"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useSearchParams, useRouter, usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDateTime } from "@/lib/utils";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSSE } from "@/contexts/sse-context";
import {
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Loader2,
    XCircle,
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

function formatDuration(startedAt: string | null, completedAt: string | null): string {
    if (!startedAt || !completedAt) return "-";
    const diff = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (diff < 1000) return `${diff}ms`;
    return `${(diff / 1000).toFixed(1)}s`;
}

export default function ScansPage() {
    const params = useParams<{ scenarioId: string }>();
    const scenarioId = params.scenarioId;
    const searchParams = useSearchParams();
    const router = useRouter();
    const pathname = usePathname();
    const { subscribe } = useSSE();

    const activeTab = searchParams.get("tab") || "sonarqube";

    const [trivyData, setTrivyData] = useState<ScanListResponse | null>(null);
    const [sonarData, setSonarData] = useState<ScanListResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [retrying, setRetrying] = useState<string | null>(null);
    const [retryAllLoading, setRetryAllLoading] = useState(false);
    const [sonarPage, setSonarPage] = useState(1);
    const [trivyPage, setTrivyPage] = useState(1);
    // Scan progress tracking
    const [scanProgress, setScanProgress] = useState<{
        scans_total: number;
        scans_completed: number;
        scans_failed: number;
        scan_extraction_completed: boolean;
    } | null>(null);
    const pollingRef = useRef<NodeJS.Timeout | null>(null);

    const handleTabChange = (value: string) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("tab", value);
        router.push(`${pathname}?${params.toString()}`);
    };

    const fetchScans = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);

        try {
            let currentData: ScanListResponse | null = null;

            if (activeTab === "trivy") {
                // Fetch trivy scans
                const trivySkip = (trivyPage - 1) * ITEMS_PER_PAGE;
                const url = `${API_BASE}/training-scenarios/${scenarioId}/commit-scans?tool_type=trivy&skip=${trivySkip}&limit=${ITEMS_PER_PAGE}`;
                const trivyRes = await fetch(url, { credentials: "include" });

                if (trivyRes.ok) {
                    const data = await trivyRes.json();
                    setTrivyData(data.trivy || null);
                    currentData = data.trivy;
                } else {
                    console.error("Trivy fetch failed:", trivyRes.status, trivyRes.statusText);
                }
            } else {
                // Fetch sonarqube scans
                const sonarSkip = (sonarPage - 1) * ITEMS_PER_PAGE;
                const url = `${API_BASE}/training-scenarios/${scenarioId}/commit-scans?tool_type=sonarqube&skip=${sonarSkip}&limit=${ITEMS_PER_PAGE}`;
                const sonarRes = await fetch(url, { credentials: "include" });

                if (sonarRes.ok) {
                    const data = await sonarRes.json();
                    setSonarData(data.sonarqube || null);
                    currentData = data.sonarqube;
                } else {
                    console.error("SonarQube fetch failed:", sonarRes.status, sonarRes.statusText);
                }
            }

            // Check for running scans for polling using fresh data
            const hasRunning = currentData?.items.some(
                (s: any) => s.status === "scanning" || s.status === "pending"
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
    }, [scenarioId, trivyPage, sonarPage, activeTab]);

    useEffect(() => {
        if (scenarioId) fetchScans();
        return () => {
            if (pollingRef.current) clearInterval(pollingRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scenarioId, trivyPage, sonarPage, activeTab]);

    // Listen for real-time SCAN_UPDATE events
    useEffect(() => {
        const handleScanUpdate = (event: CustomEvent<{
            scenario_id?: string;
            version_id?: string;
            scan_id: string;
            commit_sha: string;
            tool_type: string;
            status: string;
        }>) => {
            if (event.detail.scenario_id === scenarioId || event.detail.version_id === scenarioId) {
                fetchScans(true);
            }
        };

        window.addEventListener("SCAN_UPDATE", handleScanUpdate as EventListener);
        return () => {
            window.removeEventListener("SCAN_UPDATE", handleScanUpdate as EventListener);
        };
    }, [scenarioId, fetchScans]);

    // Subscribe to SSE for scenario scan progress updates
    useEffect(() => {
        const unsubscribe = subscribe("SCENARIO_UPDATE", (data: any) => {
            if (data.scenario_id === scenarioId) {
                setScanProgress({
                    scans_total: data.scans_total ?? 0,
                    scans_completed: data.scans_completed ?? 0,
                    scans_failed: data.scans_failed ?? 0,
                    scan_extraction_completed: data.scan_extraction_completed ?? false,
                });
            }
        });
        return () => unsubscribe();
    }, [subscribe, scenarioId]);

    // Listen for SCAN_ERROR events
    useEffect(() => {
        const handleScanError = (event: CustomEvent<{
            scenario_id?: string;
            version_id?: string;
            scan_id: string;
            commit_sha: string;
            tool_type: string;
            error: string;
            retry_count: number;
        }>) => {
            if (event.detail.scenario_id === scenarioId || event.detail.version_id === scenarioId) {
                fetchScans(true);
            }
        };

        window.addEventListener("SCAN_ERROR", handleScanError as EventListener);
        return () => {
            window.removeEventListener("SCAN_ERROR", handleScanError as EventListener);
        };
    }, [scenarioId, fetchScans]);

    const handleRetry = async (commitSha: string, toolType: string) => {
        setRetrying(`${toolType}-${commitSha}`);
        try {
            await fetch(
                `${API_BASE}/training-scenarios/${scenarioId}/commit-scans/${commitSha}/retry?tool_type=${toolType}`,
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

            await Promise.allSettled(
                allFailed.map(({ sha, tool }) =>
                    fetch(
                        `${API_BASE}/training-scenarios/${scenarioId}/commit-scans/${sha}/retry?tool_type=${tool}`,
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
        const config: Record<string, { icon: React.ReactNode; color: string }> = {
            completed: { icon: <CheckCircle2 className="h-3 w-3" />, color: "text-green-600 border-green-600/20 bg-green-50" },
            failed: { icon: <XCircle className="h-3 w-3" />, color: "text-destructive border-destructive/20 bg-destructive/10" },
            scanning: { icon: <Loader2 className="h-3 w-3 animate-spin" />, color: "text-secondary-foreground" },
            pending: { icon: <Clock className="h-3 w-3" />, color: "text-muted-foreground" },
        };
        const c = config[status] || config.pending;
        return (
            <Badge variant="outline" className={cn("font-medium", c.color)}>
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
        if (loading) {
            return (
                <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    <span className="text-sm text-muted-foreground">Loading scans...</span>
                </div>
            );
        }

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
                                <TableHead className="w-[100px]">Commit</TableHead>
                                <TableHead className="w-[140px]">Status</TableHead>
                                <TableHead className="w-[80px]">Builds</TableHead>
                                <TableHead className="w-[100px]">Duration</TableHead>
                                <TableHead className="w-[140px] text-right">Completed At</TableHead>
                                <TableHead className="w-16"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {items.map((scan) => (
                                <TableRow key={scan.id}>
                                    <TableCell className="font-mono text-xs py-2">
                                        {scan.commit_sha.substring(0, 7)}
                                    </TableCell>
                                    <TableCell className="py-2">{renderStatus(scan.status)}</TableCell>
                                    <TableCell className="py-2">{scan.builds_affected}</TableCell>
                                    <TableCell className="text-xs py-2">
                                        {formatDuration(scan.started_at, scan.completed_at)}
                                    </TableCell>
                                    <TableCell className="text-xs py-2 text-right text-muted-foreground">
                                        {formatDateTime(scan.completed_at)}
                                    </TableCell>
                                    <TableCell className="py-2">
                                        {scan.status === "failed" && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                disabled={retrying === `${toolType}-${scan.commit_sha}`}
                                                onClick={() => handleRetry(scan.commit_sha, toolType)}
                                                className="h-8 w-8 p-0"
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

    const hasTrivyScans = trivyData && trivyData.total > 0;
    const hasSonarScans = sonarData && sonarData.total > 0;

    return (
        <div className="space-y-4">
            {/* Scan Progress Banner */}
            {scanProgress && scanProgress.scans_total > 0 && (
                <Card>
                    <CardContent className="py-4">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Scan Progress</span>
                            <span className="text-sm text-muted-foreground">
                                {scanProgress.scans_completed}/{scanProgress.scans_total}
                                {scanProgress.scans_failed > 0 && (
                                    <span className="text-red-500 ml-1">({scanProgress.scans_failed} failed)</span>
                                )}
                            </span>
                        </div>
                        <Progress
                            value={
                                scanProgress.scans_total > 0
                                    ? ((scanProgress.scans_completed + scanProgress.scans_failed) / scanProgress.scans_total) * 100
                                    : 0
                            }
                            className="h-2"
                        />
                        {scanProgress.scan_extraction_completed && (
                            <p className="text-xs text-green-600 mt-1">✓ All scans complete</p>
                        )}
                    </CardContent>
                </Card>
            )}

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
                    <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
                        <TabsList className="mb-4">
                            <TabsTrigger value="sonarqube" className="flex items-center gap-2">
                                <BarChart3 className="h-4 w-4 text-blue-600" />
                                SonarQube
                            </TabsTrigger>
                            <TabsTrigger value="trivy" className="flex items-center gap-2">
                                <Shield className="h-4 w-4 text-green-600" />
                                Trivy
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="sonarqube">
                            {renderScanTable(sonarData, "sonarqube", sonarPage, setSonarPage)}
                        </TabsContent>
                        <TabsContent value="trivy">
                            {renderScanTable(trivyData, "trivy", trivyPage, setTrivyPage)}
                        </TabsContent>
                    </Tabs>
                </CardContent>
            </Card>
        </div>
    );
}
