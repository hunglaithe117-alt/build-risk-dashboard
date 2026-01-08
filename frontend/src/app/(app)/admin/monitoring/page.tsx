"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useWebSocket } from "@/contexts/websocket-context";
import {
    SystemStatsCard,
    LogsViewer,
    GrafanaLinksCard,
} from "@/components/monitoring";
import { Button } from "@/components/ui/button";
import { RefreshCw, Activity } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface SystemStats {
    celery: {
        workers: any[];
        worker_count: number;
        queues: Record<string, number>;
        status: string;
    };
    redis: {
        connected: boolean;
        version?: string;
        memory_used?: string;
        connected_clients?: number;
        error?: string;
    };
    mongodb: {
        connected: boolean;
        version?: string;
        connections?: { current: number; available: number };
        collections?: number;
        error?: string;
    };
    trivy?: {
        connected: boolean;
        server_mode?: boolean;
        server_url?: string;
        docker_available?: boolean;
        status?: string;
        error?: string;
    };
    sonarqube?: {
        connected: boolean;
        configured?: boolean;
        host_url?: string;
        status?: string;
        version?: string;
        error?: string;
    };
    timestamp: string;
}

interface LogEntry {
    timestamp: string;
    level: string;
    message: string;
    container?: string;
}

export default function MonitoringPage() {
    // System stats
    const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
    const [isLoadingStats, setIsLoadingStats] = useState(true);

    // System logs
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [isLoadingLogs, setIsLoadingLogs] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [containerFilter, setContainerFilter] = useState("all");
    const [levelFilter, setLevelFilter] = useState("all");
    const [searchQuery, setSearchQuery] = useState("");

    // WebSocket
    const { isConnected } = useWebSocket();

    // Fetch system stats
    const fetchSystemStats = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/monitoring/system`, {
                credentials: "include",
            });
            if (res.ok) {
                const data = await res.json();
                setSystemStats(data);
            }
        } catch (error) {
            console.error("Failed to fetch system stats:", error);
        } finally {
            setIsLoadingStats(false);
        }
    }, []);

    // Fetch system logs
    const fetchLogs = useCallback(async () => {
        setIsLoadingLogs(true);
        try {
            const params = new URLSearchParams();
            if (levelFilter !== "all") params.set("level", levelFilter.toUpperCase());
            if (containerFilter !== "all") params.set("source", containerFilter);
            params.set("limit", "100");

            const res = await fetch(`${API_BASE}/monitoring/logs?${params.toString()}`, {
                credentials: "include",
            });

            if (res.ok) {
                const data = await res.json();
                if (data.logs && Array.isArray(data.logs)) {
                    const parsedLogs: LogEntry[] = data.logs.map((log: any) => ({
                        timestamp: log.timestamp || new Date().toISOString(),
                        level: log.level || "INFO",
                        message: log.message || "",
                        container: log.source || "unknown",
                    }));
                    setLogs(parsedLogs);
                }
            }
        } catch (error) {
            console.error("Failed to fetch logs:", error);
            setLogs([
                {
                    timestamp: new Date().toISOString().replace("T", " ").split(".")[0],
                    level: "INFO",
                    message: "System logs will appear here when activity is logged.",
                    container: "system",
                },
            ]);
        } finally {
            setIsLoadingLogs(false);
        }
    }, [containerFilter, levelFilter]);

    // Initial fetch
    useEffect(() => {
        fetchSystemStats();
        fetchLogs();
    }, [fetchSystemStats, fetchLogs]);

    // Real-time logs via WebSocket
    useEffect(() => {
        if (isPaused) return;

        const wsUrl = (API_BASE.replace("http", "ws").replace("/api", "") + "/api/ws/logs");
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("Connected to logs WebSocket");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "connected") return;

                const newLog: LogEntry = {
                    timestamp: data.timestamp || new Date().toISOString(),
                    level: data.level || "INFO",
                    message: data.message || "",
                    container: data.source || "unknown",
                };

                setLogs((prev) => [newLog, ...prev].slice(0, 200));
            } catch (error) {
                console.error("Failed to parse WebSocket message:", error);
            }
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
        };

        ws.onclose = () => {
            console.log("Logs WebSocket disconnected");
        };

        return () => {
            ws.close();
        };
    }, [isPaused]);

    // Auto-refresh system stats every 10 seconds
    useEffect(() => {
        if (isPaused) return;

        const interval = setInterval(() => {
            fetchSystemStats();
        }, 10000);

        return () => clearInterval(interval);
    }, [isPaused, fetchSystemStats]);

    const handleRefreshAll = () => {
        setIsLoadingStats(true);
        fetchSystemStats();
        fetchLogs();
    };

    return (
        <div className="container mx-auto py-4 md:py-6 flex flex-col gap-4 md:gap-6 h-full min-h-0">
            {/* Header */}
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                    <Activity className="h-6 w-6 md:h-8 md:w-8" />
                    <div>
                        <h1 className="text-xl md:text-2xl font-bold">System Monitoring</h1>
                        <p className="text-muted-foreground text-xs md:text-sm">
                            Real-time system stats and logs
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <span
                        className={`h-2 w-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}
                        title={isConnected ? "WebSocket connected" : "WebSocket disconnected"}
                    />
                    <Button variant="outline" size="sm" onClick={handleRefreshAll}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        <span className="hidden md:inline">Refresh All</span>
                        <span className="md:hidden">Refresh</span>
                    </Button>
                </div>
            </div>

            {/* System Stats */}
            <SystemStatsCard stats={systemStats} isLoading={isLoadingStats} />

            {/* Grafana Integration */}
            <GrafanaLinksCard />

            {/* Application Logs - fills remaining space */}
            <div className="flex-1 min-h-0 flex flex-col">
                <LogsViewer
                    logs={logs.filter(log => ["ERROR", "WARN", "WARNING"].includes(log.level.toUpperCase()))}
                    isLoading={isLoadingLogs}
                    onRefresh={fetchLogs}
                    isPaused={isPaused}
                    onTogglePause={() => setIsPaused(!isPaused)}
                    containerFilter={containerFilter}
                    onContainerFilterChange={setContainerFilter}
                    levelFilter="error"
                    onLevelFilterChange={setLevelFilter}
                    searchQuery={searchQuery}
                    onSearchChange={setSearchQuery}
                />
            </div>
        </div>
    );
}
