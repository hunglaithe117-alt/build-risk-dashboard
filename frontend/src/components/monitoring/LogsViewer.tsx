"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { RefreshCw, Pause, Play, Search, X } from "lucide-react";

interface LogEntry {
    timestamp: string;
    level: string;
    message: string;
    container?: string;
}

interface LogsViewerProps {
    logs: LogEntry[];
    isLoading: boolean;
    onRefresh: () => void;
    isPaused: boolean;
    onTogglePause: () => void;
    containerFilter: string;
    onContainerFilterChange: (value: string) => void;
    levelFilter: string;
    onLevelFilterChange: (value: string) => void;
    searchQuery: string;
    onSearchChange: (value: string) => void;
}

const levelColors: Record<string, string> = {
    INFO: "text-blue-500",
    WARNING: "text-yellow-500",
    ERROR: "text-red-500",
    DEBUG: "text-gray-500",
};

export function LogsViewer({
    logs,
    isLoading,
    onRefresh,
    isPaused,
    onTogglePause,
    containerFilter,
    onContainerFilterChange,
    levelFilter,
    onLevelFilterChange,
    searchQuery,
    onSearchChange,
}: LogsViewerProps) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [autoScroll, setAutoScroll] = useState(true);

    // Auto-scroll to bottom when new logs arrive
    useEffect(() => {
        if (autoScroll && scrollRef.current && !isPaused) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs, autoScroll, isPaused]);

    const handleScroll = useCallback(() => {
        if (scrollRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
            setAutoScroll(isAtBottom);
        }
    }, []);

    const filteredLogs = logs.filter((log) => {
        if (searchQuery && !log.message.toLowerCase().includes(searchQuery.toLowerCase())) {
            return false;
        }
        return true;
    });

    return (
        <Card className="flex flex-col min-h-[400px] flex-1">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">Application Logs</CardTitle>
                    <div className="flex items-center gap-2">
                        <Badge variant={isPaused ? "secondary" : "default"}>
                            {isPaused ? "Paused" : "Live"}
                        </Badge>
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={onTogglePause}
                            title={isPaused ? "Resume" : "Pause"}
                        >
                            {isPaused ? (
                                <Play className="h-4 w-4" />
                            ) : (
                                <Pause className="h-4 w-4" />
                            )}
                        </Button>
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={onRefresh}
                            disabled={isLoading}
                        >
                            <RefreshCw
                                className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
                            />
                        </Button>
                        <a
                            href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/monitoring/logs/export?format=json`}
                            download
                            className="inline-flex"
                        >
                            <Button variant="outline" size="sm">
                                Export JSON
                            </Button>
                        </a>
                        <a
                            href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/monitoring/logs/export?format=csv`}
                            download
                            className="inline-flex"
                        >
                            <Button variant="outline" size="sm">
                                Export CSV
                            </Button>
                        </a>
                    </div>
                </div>

                {/* Filters */}
                <div className="flex items-center gap-2 mt-2">
                    <Select value={containerFilter} onValueChange={onContainerFilterChange}>
                        <SelectTrigger className="w-[150px]">
                            <SelectValue placeholder="Container" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Containers</SelectItem>
                            <SelectItem value="backend">Backend</SelectItem>
                            <SelectItem value="celery-worker">Celery Worker</SelectItem>
                            <SelectItem value="celery-beat">Celery Beat</SelectItem>
                        </SelectContent>
                    </Select>

                    <Select value={levelFilter} onValueChange={onLevelFilterChange}>
                        <SelectTrigger className="w-[120px]">
                            <SelectValue placeholder="Level" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Levels</SelectItem>
                            <SelectItem value="INFO">INFO</SelectItem>
                            <SelectItem value="WARNING">WARNING</SelectItem>
                            <SelectItem value="ERROR">ERROR</SelectItem>
                            <SelectItem value="DEBUG">DEBUG</SelectItem>
                        </SelectContent>
                    </Select>

                    <div className="relative flex-1">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search logs..."
                            value={searchQuery}
                            onChange={(e) => onSearchChange(e.target.value)}
                            className="pl-8 pr-8"
                        />
                        {searchQuery && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="absolute right-0 top-0 h-full"
                                onClick={() => onSearchChange("")}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                </div>
            </CardHeader>

            <CardContent className="flex-1 overflow-hidden p-0">
                <ScrollArea
                    ref={scrollRef}
                    className="h-full"
                    onScroll={handleScroll}
                >
                    <div className="p-4 font-mono text-xs space-y-1">
                        {filteredLogs.length === 0 ? (
                            <p className="text-muted-foreground text-center py-8">
                                {isLoading ? "Loading logs..." : "No logs found"}
                            </p>
                        ) : (
                            filteredLogs.map((log, index) => (
                                <div
                                    key={index}
                                    className="flex gap-2 hover:bg-muted/50 px-1 rounded"
                                >
                                    <span className="text-muted-foreground whitespace-nowrap">
                                        {log.timestamp}
                                    </span>
                                    <span
                                        className={`font-medium w-16 ${levelColors[log.level] || "text-foreground"
                                            }`}
                                    >
                                        [{log.level}]
                                    </span>
                                    {log.container && (
                                        <span className="text-muted-foreground">
                                            [{log.container}]
                                        </span>
                                    )}
                                    <span className="flex-1 break-all">{log.message}</span>
                                </div>
                            ))
                        )}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}
