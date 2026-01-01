"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { ReactNode, useState, useEffect, useCallback } from "react";
import { ArrowLeft, Download, Loader2, CheckCircle2, AlertCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Database, BarChart3, Home, Lock } from "lucide-react";
import { datasetVersionApi } from "@/lib/api";
import { ExportVersionModal } from "@/components/datasets/ExportVersionModal";
import { useToast } from "@/components/ui/use-toast";

interface VersionData {
    id: string;
    name: string;
    version_number: number;
    status: string;
    builds_total: number;
    builds_ingested: number;
    builds_missing_resource: number;
    builds_ingestion_failed: number;
    builds_processed: number;
    builds_processing_failed: number;
    selected_features: string[];
    created_at: string | null;
    completed_at: string | null;
}

// Status config
const getVersionStatusConfig = (status: string) => {
    const key = status.toLowerCase();
    const config: Record<string, { icon: typeof CheckCircle2; color: string; bgColor: string }> = {
        queued: { icon: Loader2, color: "text-slate-600", bgColor: "bg-slate-100" },
        ingesting: { icon: Loader2, color: "text-blue-600", bgColor: "bg-blue-100" },
        ingested: { icon: CheckCircle2, color: "text-emerald-600", bgColor: "bg-emerald-100" },
        processing: { icon: Loader2, color: "text-purple-600", bgColor: "bg-purple-100" },
        processed: { icon: CheckCircle2, color: "text-green-600", bgColor: "bg-green-100" },
        failed: { icon: XCircle, color: "text-red-600", bgColor: "bg-red-100" },
        cancelled: { icon: AlertCircle, color: "text-slate-600", bgColor: "bg-slate-100" },
    };
    return config[key] || config.failed;
};

export default function VersionLayout({ children }: { children: ReactNode }) {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const pathname = usePathname();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    const [version, setVersion] = useState<VersionData | null>(null);
    const [loading, setLoading] = useState(true);
    const [isExportModalOpen, setIsExportModalOpen] = useState(false);
    const { toast } = useToast();

    // Determine active tab from pathname
    const getActiveTab = () => {
        if (pathname.includes("/builds")) return "builds";
        if (pathname.includes("/analysis")) return "analysis";
        if (pathname.includes("/export")) return "export";
        return "overview";
    };
    const activeTab = getActiveTab();

    // Fetch version data
    useEffect(() => {
        async function fetchVersion() {
            setLoading(true);
            try {
                const response = await datasetVersionApi.getVersionData(
                    datasetId,
                    versionId,
                    1,
                    1,
                    false
                );
                setVersion(response.version);
            } catch (err) {
                console.error("Failed to fetch version:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchVersion();
    }, [datasetId, versionId]);

    // Listen for INGESTION_ERROR events
    useEffect(() => {
        const handleIngestionError = (event: CustomEvent<{
            repo_id: string;
            resource: string;
            error: string;
        }>) => {
            toast({
                variant: "destructive",
                title: `Ingestion Error (${event.detail.resource})`,
                description: event.detail.error.slice(0, 150),
            });
        };

        window.addEventListener("INGESTION_ERROR", handleIngestionError as EventListener);
        return () => {
            window.removeEventListener("INGESTION_ERROR", handleIngestionError as EventListener);
        };
    }, [toast]);

    // Listen for SCAN_ERROR events
    useEffect(() => {
        const handleScanError = (event: CustomEvent<{
            version_id: string;
            commit_sha: string;
            tool_type: string;
            error: string;
        }>) => {
            if (event.detail.version_id === versionId) {
                toast({
                    variant: "destructive",
                    title: `${event.detail.tool_type} Scan Failed`,
                    description: `Commit ${event.detail.commit_sha.slice(0, 7)}: ${event.detail.error.slice(0, 100)}`,
                });
            }
        };

        window.addEventListener("SCAN_ERROR", handleScanError as EventListener);
        return () => {
            window.removeEventListener("SCAN_ERROR", handleScanError as EventListener);
        };
    }, [versionId, toast]);

    if (loading || !version) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    const statusConfig = getVersionStatusConfig(version.status);
    const StatusIcon = statusConfig.icon;
    const isProcessed = version.status === "processed";
    const canViewAnalysis = isProcessed;
    const canViewExport = isProcessed;

    const basePath = `/projects/${datasetId}/versions/${versionId}`;

    return (
        <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link href={`/projects/${datasetId}`}>
                        <Button variant="ghost" size="sm">
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                    </Link>
                    <div>
                        <h1 className="text-2xl font-bold">{version.name}</h1>
                        <p className="text-sm text-muted-foreground">
                            Version {version.version_number}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <Badge className={`${statusConfig.bgColor} ${statusConfig.color}`}>
                        <StatusIcon className={`mr-1 h-3 w-3 ${["queued", "ingesting", "processing"].includes(version.status) ? "animate-spin" : ""}`} />
                        {version.status.charAt(0).toUpperCase() + version.status.slice(1)}
                    </Badge>
                    {version.status === "processed" && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setIsExportModalOpen(true)}
                        >
                            <Download className="mr-2 h-4 w-4" />
                            Export
                        </Button>
                    )}
                </div>
            </div>

            {/* Tab Navigation */}
            <Tabs value={activeTab}>
                <TabsList className="grid w-full grid-cols-4 mb-4">
                    <TabsTrigger value="overview" asChild>
                        <Link href={basePath} className="gap-2">
                            <Home className="h-4 w-4" />
                            Overview
                        </Link>
                    </TabsTrigger>
                    <TabsTrigger value="builds" asChild>
                        <Link href={`${basePath}/builds`} className="gap-2">
                            <Database className="h-4 w-4" />
                            Builds
                        </Link>
                    </TabsTrigger>
                    <TabsTrigger value="analysis" asChild disabled={!canViewAnalysis}>
                        <Link
                            href={canViewAnalysis ? `${basePath}/analysis` : "#"}
                            className="gap-2"
                            onClick={(e) => !canViewAnalysis && e.preventDefault()}
                        >
                            {!canViewAnalysis && <Lock className="h-3 w-3" />}
                            <BarChart3 className="h-4 w-4" />
                            Analysis
                        </Link>
                    </TabsTrigger>
                    <TabsTrigger value="export" asChild disabled={!canViewExport}>
                        <Link
                            href={canViewExport ? `${basePath}/export` : "#"}
                            className="gap-2"
                            onClick={(e) => !canViewExport && e.preventDefault()}
                        >
                            {!canViewExport && <Lock className="h-3 w-3" />}
                            <Download className="h-4 w-4" />
                            Export
                        </Link>
                    </TabsTrigger>
                </TabsList>
            </Tabs>

            {/* Page Content */}
            {children}

            {/* Export Modal */}
            <ExportVersionModal
                isOpen={isExportModalOpen}
                onClose={() => setIsExportModalOpen(false)}
                datasetId={datasetId}
                versionId={versionId}
                versionName={version.name}
                totalRows={version.builds_total}
            />
        </div>
    );
}
