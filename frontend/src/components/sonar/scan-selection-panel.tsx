"use client";

import { BarChart3, Shield, Info } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScanMetricsSelector } from "./scan-metrics-selector";
import { cn } from "@/lib/utils";

export interface EnabledTools {
    sonarqube: boolean;
    trivy: boolean;
}

interface ScanSelectionPanelProps {
    selectedSonarMetrics: string[];
    selectedTrivyMetrics: string[];
    onSonarMetricsChange: (metrics: string[]) => void;
    onTrivyMetricsChange: (metrics: string[]) => void;
    enabledTools: EnabledTools;
    onEnabledToolsChange: (tools: EnabledTools) => void;
    disabled?: boolean;
}

export function ScanSelectionPanel({
    selectedSonarMetrics,
    selectedTrivyMetrics,
    onSonarMetricsChange,
    onTrivyMetricsChange,
    enabledTools,
    onEnabledToolsChange,
    disabled = false,
}: ScanSelectionPanelProps) {

    // Toggle tool
    const toggleTool = (tool: keyof EnabledTools) => {
        const newTools = { ...enabledTools, [tool]: !enabledTools[tool] };
        onEnabledToolsChange(newTools);

        // Clear metrics when disabling tool
        if (enabledTools[tool]) {
            if (tool === "sonarqube") onSonarMetricsChange([]);
            if (tool === "trivy") onTrivyMetricsChange([]);
        }
    };

    return (
        <Card className="h-full border-none shadow-none bg-transparent">
            <CardContent className="p-0 h-full flex flex-col">
                <Tabs defaultValue="sonarqube" className="flex-1 flex flex-col min-h-0">
                    <TabsList className="grid w-full grid-cols-2 mb-4 bg-muted/50">
                        <TabsTrigger value="sonarqube" className="flex items-center gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
                            <BarChart3 className="h-4 w-4" />
                            SonarQube
                            {enabledTools.sonarqube && (
                                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 pointer-events-none">
                                    ON
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="trivy" className="flex items-center gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
                            <Shield className="h-4 w-4" />
                            Trivy
                            {enabledTools.trivy && (
                                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px] bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300 pointer-events-none">
                                    ON
                                </Badge>
                            )}
                        </TabsTrigger>
                    </TabsList>

                    {/* SonarQube Content */}
                    <TabsContent value="sonarqube" className="mt-0 flex-1 overflow-y-auto min-h-0 space-y-4 pr-1">
                        <div className="flex items-center gap-2 px-1 mb-4">
                            <Checkbox
                                id="enable-sonar"
                                checked={enabledTools.sonarqube}
                                onCheckedChange={() => !disabled && toggleTool("sonarqube")}
                                disabled={disabled}
                                className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                            />
                            <label
                                htmlFor="enable-sonar"
                                className={cn(
                                    "font-medium cursor-pointer select-none flex items-center gap-2",
                                    disabled && "opacity-50 cursor-not-allowed"
                                )}
                            >
                                Enable SonarQube Scan
                                <span className="text-sm font-normal text-muted-foreground hidden sm:inline-block">
                                    - Analyzes code quality, bugs, and security vulnerabilities
                                </span>
                            </label>
                        </div>

                        {enabledTools.sonarqube ? (
                            <div className="space-y-3">
                                <div className="flex items-center gap-2 text-sm font-medium text-blue-600 dark:text-blue-400 px-1">
                                    <BarChart3 className="h-4 w-4" />
                                    Select Metrics
                                </div>
                                <ScanMetricsSelector
                                    selectedSonarMetrics={selectedSonarMetrics}
                                    selectedTrivyMetrics={[]}
                                    onSonarChange={onSonarMetricsChange}
                                    onTrivyChange={() => { }}
                                    showOnlyTool="sonarqube"
                                />
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-10 text-center text-muted-foreground bg-slate-50/50 dark:bg-slate-900/20 rounded-lg dashed border-2 border-dashed">
                                <BarChart3 className="h-10 w-10 opacity-20 mb-3" />
                                <p>SonarQube scanning is disabled.</p>
                                <p className="text-sm opacity-60">Enable it to select metrics.</p>
                            </div>
                        )}
                    </TabsContent>

                    {/* Trivy Content */}
                    <TabsContent value="trivy" className="mt-0 flex-1 overflow-y-auto min-h-0 space-y-4 pr-1">
                        <div className="flex items-center gap-2 px-1 mb-4">
                            <Checkbox
                                id="enable-trivy"
                                checked={enabledTools.trivy}
                                onCheckedChange={() => !disabled && toggleTool("trivy")}
                                disabled={disabled}
                                className="data-[state=checked]:bg-green-600 data-[state=checked]:border-green-600"
                            />
                            <label
                                htmlFor="enable-trivy"
                                className={cn(
                                    "font-medium cursor-pointer select-none flex items-center gap-2",
                                    disabled && "opacity-50 cursor-not-allowed"
                                )}
                            >
                                Enable Trivy Scan
                                <span className="text-sm font-normal text-muted-foreground hidden sm:inline-block">
                                    - Scans for container image vulnerabilities (CVEs) and filesystem issues
                                </span>
                            </label>
                        </div>

                        {enabledTools.trivy ? (
                            <div className="space-y-3">
                                <div className="flex items-center gap-2 text-sm font-medium text-green-600 dark:text-green-400 px-1">
                                    <Shield className="h-4 w-4" />
                                    Select Metrics
                                </div>
                                <ScanMetricsSelector
                                    selectedSonarMetrics={[]}
                                    selectedTrivyMetrics={selectedTrivyMetrics}
                                    onSonarChange={() => { }}
                                    onTrivyChange={onTrivyMetricsChange}
                                    showOnlyTool="trivy"
                                />
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-10 text-center text-muted-foreground bg-slate-50/50 dark:bg-slate-900/20 rounded-lg dashed border-2 border-dashed">
                                <Shield className="h-10 w-10 opacity-20 mb-3" />
                                <p>Trivy scanning is disabled.</p>
                                <p className="text-sm opacity-60">Enable it to select metrics.</p>
                            </div>
                        )}
                    </TabsContent>
                </Tabs>
            </CardContent>
        </Card>
    );
}
