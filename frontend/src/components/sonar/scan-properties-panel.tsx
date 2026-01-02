"use client";

import { Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { RepoScanOverrideSection } from "./RepoScanOverrideSection";
import type { ScanConfig, EnabledTools } from "./scan-config-panel";

interface RepoInfo {
    id: string;
    full_name: string;
}

interface ScanPropertiesPanelProps {
    scanConfig: ScanConfig;
    onScanConfigChange: (config: ScanConfig) => void;
    enabledTools: EnabledTools;
    disabled?: boolean;
    repos?: RepoInfo[];
}

export function ScanPropertiesPanel({
    scanConfig,
    onScanConfigChange,
    enabledTools,
    disabled = false,
    repos = [],
}: ScanPropertiesPanelProps) {
    // Check if any repo config is set
    const hasConfig = Boolean(
        Object.keys(scanConfig.sonarqube.repos).length > 0 ||
        Object.keys(scanConfig.trivy.repos).length > 0
    );

    // Show panel only if tools are enabled and repos are available
    const shouldShow = (enabledTools.sonarqube || enabledTools.trivy) && repos.length > 0;

    if (!shouldShow) return null;

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div className="space-y-1">
                    <div className="flex items-center gap-2">
                        <Wrench className="h-4 w-4 text-muted-foreground" />
                        <h3 className="text-lg font-medium">Per-Repository Scan Configuration</h3>
                    </div>
                    <p className="text-sm text-muted-foreground">
                        Configure scanner properties for specific repositories
                    </p>
                </div>
                {hasConfig && (
                    <Badge variant="secondary" className="text-xs">
                        configured
                    </Badge>
                )}
            </div>

            <RepoScanOverrideSection
                repos={repos}
                scanConfig={scanConfig}
                onScanConfigChange={onScanConfigChange}
                disabled={disabled}
            />
        </div>
    );
}
