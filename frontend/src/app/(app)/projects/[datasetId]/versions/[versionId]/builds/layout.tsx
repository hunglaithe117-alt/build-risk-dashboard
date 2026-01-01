"use client";

import { usePathname, useParams } from "next/navigation";
import Link from "next/link";
import { ReactNode, useState, useEffect, useCallback } from "react";
import { Lock, Loader2 } from "lucide-react";
import { datasetVersionApi } from "@/lib/api";
import { cn } from "@/lib/utils";

// Statuses that allow viewing processing/scans tabs
const PROCESSING_STATUSES = ["processing", "processed", "failed"];

export default function BuildsLayout({ children }: { children: ReactNode }) {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const pathname = usePathname();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    const [versionStatus, setVersionStatus] = useState<string>("queued");
    const [loading, setLoading] = useState(true);

    // Fetch version status
    useEffect(() => {
        async function fetchVersion() {
            try {
                const response = await datasetVersionApi.getVersionData(
                    datasetId,
                    versionId,
                    1,
                    1,
                    false
                );
                setVersionStatus(response.version.status);
            } catch (err) {
                console.error("Failed to fetch version:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchVersion();
    }, [datasetId, versionId]);

    // Determine active sub-tab
    const getActiveTab = () => {
        if (pathname.endsWith("/processing")) return "processing";
        if (pathname.endsWith("/scans")) return "scans";
        return "ingestion";
    };
    const activeTab = getActiveTab();

    const canViewProcessing = PROCESSING_STATUSES.includes(versionStatus.toLowerCase());
    const canViewScans = PROCESSING_STATUSES.includes(versionStatus.toLowerCase());

    const basePath = `/projects/${datasetId}/versions/${versionId}/builds`;

    const TabButton = ({ tab, label, disabled, href }: { tab: string; label: string; disabled?: boolean; href: string }) => {
        const isActive = activeTab === tab;
        return (
            <Link
                href={disabled ? "#" : href}
                onClick={(e) => disabled && e.preventDefault()}
                className={cn(
                    "px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1",
                    isActive && !disabled
                        ? "bg-background text-foreground shadow-sm"
                        : disabled
                            ? "text-muted-foreground/50 cursor-not-allowed"
                            : "text-muted-foreground hover:text-foreground"
                )}
            >
                {disabled && <Lock className="h-3 w-3" />}
                {label}
            </Link>
        );
    };

    if (loading) {
        return (
            <div className="flex min-h-[200px] items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Sub-tabs Navigation */}
            <div className="flex items-center justify-between">
                <div className="flex gap-1 rounded-lg bg-muted p-1">
                    <TabButton tab="ingestion" label="Data Collection" href={`${basePath}/ingestion`} />
                    <TabButton
                        tab="processing"
                        label="Feature Extraction"
                        disabled={!canViewProcessing}
                        href={`${basePath}/processing`}
                    />
                    <TabButton
                        tab="scans"
                        label="Integration Scans"
                        disabled={!canViewScans}
                        href={`${basePath}/scans`}
                    />
                </div>
            </div>

            {/* Page Content */}
            {children}
        </div>
    );
}
