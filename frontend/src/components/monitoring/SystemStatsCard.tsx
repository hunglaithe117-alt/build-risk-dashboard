"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    Activity,
    Database,
    Server,
    Cpu,
    HardDrive,
    Users,
    Zap,
    Shield,
    Bug,
} from "lucide-react";

interface WorkerInfo {
    name: string;
    status: string;
    active_tasks: number;
    reserved_tasks: number;
    pool: number;
}

interface SystemStatsProps {
    celery: {
        workers: WorkerInfo[];
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
        docker_version?: string;
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

interface SystemStatsCardProps {
    stats: SystemStatsProps | null;
    isLoading: boolean;
}

export function SystemStatsCard({ stats, isLoading }: SystemStatsCardProps) {
    if (isLoading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                {[1, 2, 3, 4, 5].map((i) => (
                    <Card key={i} className="animate-pulse">
                        <CardHeader className="pb-2">
                            <div className="h-4 bg-muted rounded w-24" />
                        </CardHeader>
                        <CardContent>
                            <div className="h-8 bg-muted rounded w-16 mb-2" />
                            <div className="h-3 bg-muted rounded w-32" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    if (!stats) {
        return (
            <Card>
                <CardContent className="pt-6">
                    <p className="text-muted-foreground text-center">
                        Failed to load system stats
                    </p>
                </CardContent>
            </Card>
        );
    }

    const totalQueueMessages = Object.values(stats.celery.queues).reduce(
        (a, b) => a + b,
        0
    );

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {/* Celery Card */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Cpu className="h-4 w-4" />
                        Celery Workers
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-bold">
                            {stats.celery.worker_count}
                        </span>
                        <Badge
                            variant={stats.celery.status === "online" ? "default" : "destructive"}
                        >
                            {stats.celery.status}
                        </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                        {totalQueueMessages} messages in queues
                    </p>
                    {stats.celery.workers.length > 0 && (
                        <div className="mt-3 space-y-1">
                            {stats.celery.workers.map((worker) => (
                                <div
                                    key={worker.name}
                                    className="flex items-center justify-between text-xs"
                                >
                                    <span className="truncate max-w-[120px]" title={worker.name}>
                                        {worker.name.split("@")[1] || worker.name}
                                    </span>
                                    <Badge variant="outline" className="text-xs">
                                        {worker.active_tasks} active
                                    </Badge>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Redis Card */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Zap className="h-4 w-4" />
                        Redis
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <Badge
                            variant={stats.redis.connected ? "default" : "destructive"}
                        >
                            {stats.redis.connected ? "Connected" : "Disconnected"}
                        </Badge>
                    </div>
                    {stats.redis.connected ? (
                        <>
                            <p className="text-xs text-muted-foreground mt-2">
                                Memory: {stats.redis.memory_used}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Clients: {stats.redis.connected_clients}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Version: {stats.redis.version}
                            </p>
                        </>
                    ) : (
                        <p className="text-xs text-destructive mt-2">{stats.redis.error}</p>
                    )}
                </CardContent>
            </Card>

            {/* MongoDB Card */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Database className="h-4 w-4" />
                        MongoDB
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <Badge
                            variant={stats.mongodb.connected ? "default" : "destructive"}
                        >
                            {stats.mongodb.connected ? "Connected" : "Disconnected"}
                        </Badge>
                    </div>
                    {stats.mongodb.connected ? (
                        <>
                            <p className="text-xs text-muted-foreground mt-2">
                                Collections: {stats.mongodb.collections}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Connections: {stats.mongodb.connections?.current} /{" "}
                                {stats.mongodb.connections?.available}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Version: {stats.mongodb.version}
                            </p>
                        </>
                    ) : (
                        <p className="text-xs text-destructive mt-2">
                            {stats.mongodb.error}
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Trivy Card */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Shield className="h-4 w-4" />
                        Trivy
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <Badge
                            variant={stats.trivy?.connected ? "default" : "destructive"}
                        >
                            {stats.trivy?.connected ? "Connected" : "Disconnected"}
                        </Badge>
                    </div>
                    {stats.trivy?.connected ? (
                        <>
                            <p className="text-xs text-muted-foreground mt-2">
                                Mode: {stats.trivy.server_mode ? "Server" : "Standalone"}
                            </p>
                            {stats.trivy.server_url && (
                                <p className="text-xs text-muted-foreground truncate" title={stats.trivy.server_url}>
                                    URL: {stats.trivy.server_url}
                                </p>
                            )}
                            {stats.trivy.docker_version && (
                                <p className="text-xs text-muted-foreground truncate">
                                    Docker: ✓
                                </p>
                            )}
                        </>
                    ) : (
                        <p className="text-xs text-destructive mt-2">
                            {stats.trivy?.error || "Not configured"}
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* SonarQube Card */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <Bug className="h-4 w-4" />
                        SonarQube
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <Badge
                            variant={stats.sonarqube?.connected ? "default" : "destructive"}
                        >
                            {stats.sonarqube?.connected ? "Connected" : "Disconnected"}
                        </Badge>
                    </div>
                    {stats.sonarqube?.connected ? (
                        <>
                            <p className="text-xs text-muted-foreground mt-2">
                                Status: {stats.sonarqube.status}
                            </p>
                            {stats.sonarqube.version && (
                                <p className="text-xs text-muted-foreground">
                                    Version: {stats.sonarqube.version}
                                </p>
                            )}
                            {stats.sonarqube.host_url && (
                                <p className="text-xs text-muted-foreground truncate" title={stats.sonarqube.host_url}>
                                    Host: {new URL(stats.sonarqube.host_url).hostname}
                                </p>
                            )}
                        </>
                    ) : (
                        <p className="text-xs text-destructive mt-2">
                            {stats.sonarqube?.error || "Not configured"}
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

