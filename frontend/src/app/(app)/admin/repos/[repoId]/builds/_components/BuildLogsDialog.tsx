"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api } from "@/lib/api";
import type { Build } from "@/types";
import {
    AlertCircle,
    AlertTriangle,
    FileText,
    Loader2,
} from "lucide-react";

interface LogFile {
    job_name: string;
    filename: string;
    content?: string;
    size_bytes?: number;
    error?: string;
}

interface LogsResponse {
    logs: LogFile[];
    logs_available: boolean;
    logs_expired: boolean;
    build_number?: number;
    error?: string;
}

interface BuildLogsDialogProps {
    repoId: string;
    build: Build | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function BuildLogsDialog({ repoId, build, open, onOpenChange }: BuildLogsDialogProps) {
    const [logs, setLogs] = useState<LogsResponse | null>(null);
    const [loading, setLoading] = useState(false);

    const loadLogs = async (buildId: string) => {
        setLoading(true);
        setLogs(null);
        try {
            const res = await api.get<LogsResponse>(`/repos/${repoId}/builds/${buildId}/logs`);
            setLogs(res.data);
        } catch (err) {
            console.error("Failed to load logs:", err);
            setLogs({ logs: [], logs_available: false, logs_expired: true, error: "Failed to load logs" });
        } finally {
            setLoading(false);
        }
    };

    // Load logs when dialog opens
    if (open && build && !logs && !loading) {
        loadLogs(build.id);
    }

    // Reset when dialog closes
    const handleOpenChange = (newOpen: boolean) => {
        if (!newOpen) {
            setLogs(null);
        }
        onOpenChange(newOpen);
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-4xl max-h-[85vh]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5" />
                        Build Logs - #{build?.build_number}
                    </DialogTitle>
                    <DialogDescription>
                        Workflow Run #{build?.workflow_run_id}
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : logs?.logs_expired ? (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>
                            Build logs have expired and are no longer available from GitHub.
                        </AlertDescription>
                    </Alert>
                ) : !logs?.logs_available ? (
                    <Alert>
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                            No logs available for this build.
                        </AlertDescription>
                    </Alert>
                ) : logs?.logs && logs.logs.length > 0 ? (
                    <Tabs defaultValue={logs.logs[0].job_name} className="flex-1">
                        <TabsList className="flex flex-wrap h-auto gap-1">
                            {logs.logs.map((log) => (
                                <TabsTrigger key={log.job_name} value={log.job_name} className="text-xs">
                                    {log.job_name}
                                    {log.size_bytes && (
                                        <span className="ml-1 text-muted-foreground">({formatBytes(log.size_bytes)})</span>
                                    )}
                                </TabsTrigger>
                            ))}
                        </TabsList>
                        {logs.logs.map((log) => (
                            <TabsContent key={log.job_name} value={log.job_name} className="mt-4">
                                <ScrollArea className="h-[50vh] rounded border bg-slate-950 p-4">
                                    <pre className="text-xs text-slate-100 font-mono whitespace-pre-wrap">
                                        {log.content || log.error || "No content"}
                                    </pre>
                                </ScrollArea>
                            </TabsContent>
                        ))}
                    </Tabs>
                ) : (
                    <p className="text-muted-foreground text-center py-8">No log files found.</p>
                )}
            </DialogContent>
        </Dialog>
    );
}

interface LogsCellProps {
    build: Build;
    onViewLogs: (build: Build) => void;
}

export function LogsCell({ build, onViewLogs }: LogsCellProps) {
    if (build.logs_available) {
        return (
            <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onViewLogs(build); }} className="h-7 px-2">
                <FileText className="h-3 w-3 mr-1 text-green-600" />
                View
            </Button>
        );
    }

    if (build.logs_expired) {
        return (
            <Badge variant="secondary" className="bg-amber-100 text-amber-700">
                <AlertTriangle className="h-3 w-3 mr-1" />
                Expired
            </Badge>
        );
    }

    return <Badge variant="secondary">N/A</Badge>;
}
