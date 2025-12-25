"use client";

import { useState } from "react";
import { Settings, ChevronDown, ChevronUp, BarChart3, Shield, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScanMetricsSelector } from "./scan-metrics-selector";
import { RepoScanOverrideSection } from "./RepoScanOverrideSection";

// =============================================================================
// Types
// =============================================================================

export interface SonarConfig {
    projectKey?: string;
    extraProperties?: string;
    token?: string;
}

export interface TrivyConfig {
    trivyYaml?: string;
}

export interface ScanConfig {
    sonarqube: SonarConfig & { repos?: Record<string, SonarConfig> };
    trivy: TrivyConfig & { repos?: Record<string, TrivyConfig> };
}

export interface EnabledTools {
    sonarqube: boolean;
    trivy: boolean;
}

interface RepoInfo {
    id: string;
    full_name: string;
}

interface ScanConfigPanelProps {
    selectedSonarMetrics: string[];
    selectedTrivyMetrics: string[];
    onSonarMetricsChange: (metrics: string[]) => void;
    onTrivyMetricsChange: (metrics: string[]) => void;
    scanConfig: ScanConfig;
    onScanConfigChange: (config: ScanConfig) => void;
    enabledTools?: EnabledTools;
    onEnabledToolsChange?: (tools: EnabledTools) => void;
    disabled?: boolean;
    repos?: RepoInfo[];  // Optional repos for per-repo config
}


const DEFAULT_SCAN_CONFIG: ScanConfig = {
    sonarqube: {
        projectKey: "",
        extraProperties: "",
        token: "",
    },
    trivy: {
        trivyYaml: "",
    },
};

const DEFAULT_ENABLED_TOOLS: EnabledTools = {
    sonarqube: false,
    trivy: false,
};


export function ScanConfigPanel({
    selectedSonarMetrics,
    selectedTrivyMetrics,
    onSonarMetricsChange,
    onTrivyMetricsChange,
    scanConfig,
    onScanConfigChange,
    enabledTools = DEFAULT_ENABLED_TOOLS,
    onEnabledToolsChange,
    disabled = false,
    repos = [],
}: ScanConfigPanelProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [isConfigOpen, setIsConfigOpen] = useState(false);
    const [internalEnabledTools, setInternalEnabledTools] = useState<EnabledTools>(enabledTools);

    // Use external or internal state
    const tools = onEnabledToolsChange ? enabledTools : internalEnabledTools;
    const setTools = onEnabledToolsChange || setInternalEnabledTools;

    const totalMetrics = selectedSonarMetrics.length + selectedTrivyMetrics.length;
    const enabledCount = (tools.sonarqube ? 1 : 0) + (tools.trivy ? 1 : 0);

    // Toggle tool
    const toggleTool = (tool: keyof EnabledTools) => {
        const newTools = { ...tools, [tool]: !tools[tool] };
        setTools(newTools);

        // Clear metrics when disabling tool
        if (tools[tool]) {
            if (tool === "sonarqube") onSonarMetricsChange([]);
            if (tool === "trivy") onTrivyMetricsChange([]);
        }
    };

    // Update SonarQube config
    const updateSonarConfig = (key: keyof SonarConfig, value: string | boolean) => {
        onScanConfigChange({
            ...scanConfig,
            sonarqube: {
                ...scanConfig.sonarqube,
                [key]: value,
            },
        });
    };

    // Update Trivy config
    const updateTrivyConfig = (key: keyof TrivyConfig, value: string) => {
        onScanConfigChange({
            ...scanConfig,
            trivy: {
                ...scanConfig.trivy,
                [key]: value,
            },
        });
    };

    // Check if any config is set
    const hasConfig = Boolean(
        scanConfig.sonarqube.projectKey ||
        scanConfig.sonarqube.extraProperties ||
        scanConfig.trivy.trivyYaml
    );

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <CollapsibleTrigger asChild>
                <Button
                    variant="outline"
                    className="w-full justify-between"
                    disabled={disabled}
                >
                    <span className="flex items-center gap-2">
                        <Settings className="h-4 w-4" />
                        Scan Configuration
                        {enabledCount > 0 && (
                            <span className="bg-primary/10 text-primary text-xs px-2 py-0.5 rounded-full">
                                {enabledCount} tool{enabledCount > 1 ? "s" : ""}
                                {totalMetrics > 0 && ` • ${totalMetrics} metrics`}
                            </span>
                        )}
                    </span>
                    {isOpen ? (
                        <ChevronUp className="h-4 w-4" />
                    ) : (
                        <ChevronDown className="h-4 w-4" />
                    )}
                </Button>
            </CollapsibleTrigger>

            <CollapsibleContent className="pt-4 space-y-4">
                {/* Tool Selection & Metrics */}
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base">Select Scan Tools & Metrics</CardTitle>
                        <CardDescription>
                            Enable tools and choose which metrics to include
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {/* Tool Selection */}
                        <div className="flex flex-wrap gap-4">
                            <label
                                className={`flex items-center gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-all ${tools.sonarqube
                                    ? "bg-blue-50 border-blue-300 dark:bg-blue-900/20"
                                    : "hover:bg-muted/50"
                                    }`}
                            >
                                <Checkbox
                                    checked={tools.sonarqube}
                                    onCheckedChange={() => toggleTool("sonarqube")}
                                />
                                <div className="flex items-center gap-2">
                                    <BarChart3 className="h-4 w-4 text-blue-600" />
                                    <span className="font-medium">SonarQube</span>
                                </div>
                                {selectedSonarMetrics.length > 0 && (
                                    <Badge variant="secondary" className="ml-2">
                                        {selectedSonarMetrics.length} metrics
                                    </Badge>
                                )}
                            </label>

                            <label
                                className={`flex items-center gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-all ${tools.trivy
                                    ? "bg-green-50 border-green-300 dark:bg-green-900/20"
                                    : "hover:bg-muted/50"
                                    }`}
                            >
                                <Checkbox
                                    checked={tools.trivy}
                                    onCheckedChange={() => toggleTool("trivy")}
                                />
                                <div className="flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-green-600" />
                                    <span className="font-medium">Trivy</span>
                                </div>
                                {selectedTrivyMetrics.length > 0 && (
                                    <Badge variant="secondary" className="ml-2">
                                        {selectedTrivyMetrics.length} metrics
                                    </Badge>
                                )}
                            </label>
                        </div>

                        {/* Metrics Selection - show when a tool is enabled */}
                        {tools.sonarqube && (
                            <div className="space-y-3 border-t pt-4">
                                <div className="flex items-center gap-2">
                                    <BarChart3 className="h-4 w-4 text-blue-600" />
                                    <h5 className="text-sm font-medium">SonarQube Metrics</h5>
                                </div>
                                <ScanMetricsSelector
                                    selectedSonarMetrics={selectedSonarMetrics}
                                    selectedTrivyMetrics={[]}
                                    onSonarChange={onSonarMetricsChange}
                                    onTrivyChange={() => { }}
                                    showOnlyTool="sonarqube"
                                />
                            </div>
                        )}

                        {tools.trivy && (
                            <div className="space-y-3 border-t pt-4">
                                <div className="flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-green-600" />
                                    <h5 className="text-sm font-medium">Trivy Metrics</h5>
                                </div>
                                <ScanMetricsSelector
                                    selectedSonarMetrics={[]}
                                    selectedTrivyMetrics={selectedTrivyMetrics}
                                    onSonarChange={() => { }}
                                    onTrivyChange={onTrivyMetricsChange}
                                    showOnlyTool="trivy"
                                />
                            </div>
                        )}

                        {/* Empty State */}
                        {!tools.sonarqube && !tools.trivy && (
                            <div className="text-center py-6 text-muted-foreground">
                                Select a tool above to choose metrics
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Tool Configuration - Separate Collapsible (like FeatureConfigForm) */}
                {(tools.sonarqube || tools.trivy) && (
                    <Collapsible open={isConfigOpen} onOpenChange={setIsConfigOpen}>
                        <Card className="border-dashed">
                            <CollapsibleTrigger asChild>
                                <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors py-3">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <Wrench className="h-4 w-4 text-muted-foreground" />
                                            <CardTitle className="text-sm font-medium">
                                                Scanner Configuration
                                            </CardTitle>
                                            {hasConfig && (
                                                <Badge variant="secondary" className="text-xs">
                                                    configured
                                                </Badge>
                                            )}
                                        </div>
                                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                                            {isConfigOpen ? (
                                                <ChevronUp className="h-4 w-4" />
                                            ) : (
                                                <ChevronDown className="h-4 w-4" />
                                            )}
                                        </Button>
                                    </div>
                                    <CardDescription className="text-xs">
                                        Configure scanner properties (optional)
                                    </CardDescription>
                                </CardHeader>
                            </CollapsibleTrigger>

                            <CollapsibleContent>
                                <CardContent className="pt-0 space-y-6">
                                    <Accordion type="multiple">
                                        {/* SonarQube Config */}
                                        {tools.sonarqube && (
                                            <AccordionItem value="sonarqube">
                                                <AccordionTrigger className="hover:no-underline py-2">
                                                    <div className="flex items-center gap-2">
                                                        <BarChart3 className="h-4 w-4 text-blue-600" />
                                                        <span className="text-sm">SonarQube Properties</span>
                                                    </div>
                                                </AccordionTrigger>
                                                <AccordionContent className="pt-2 space-y-4">
                                                    <div className="grid gap-3 pl-4">
                                                        <div className="grid gap-2">
                                                            <Label htmlFor="sonar-project-key" className="text-xs">
                                                                Project Key (Optional)
                                                            </Label>
                                                            <Input
                                                                id="sonar-project-key"
                                                                placeholder="my-project-key"
                                                                value={scanConfig.sonarqube.projectKey || ""}
                                                                onChange={(e) =>
                                                                    updateSonarConfig("projectKey", e.target.value)
                                                                }
                                                                className="h-8 text-sm"
                                                            />
                                                            <p className="text-xs text-muted-foreground">
                                                                Override auto-generated project key
                                                            </p>
                                                        </div>
                                                        <div className="grid gap-2">
                                                            <Label htmlFor="sonar-extra" className="text-xs">
                                                                Extra Scanner Properties
                                                            </Label>
                                                            <Textarea
                                                                id="sonar-extra"
                                                                placeholder={`sonar.sources=.\nsonar.sourceEncoding=UTF-8`}
                                                                value={scanConfig.sonarqube.extraProperties || ""}
                                                                onChange={(e) =>
                                                                    updateSonarConfig("extraProperties", e.target.value)
                                                                }
                                                                rows={4}
                                                                className="font-mono text-xs"
                                                            />
                                                        </div>
                                                    </div>
                                                </AccordionContent>
                                            </AccordionItem>
                                        )}

                                        {/* Trivy Config */}
                                        {tools.trivy && (
                                            <AccordionItem value="trivy">
                                                <AccordionTrigger className="hover:no-underline py-2">
                                                    <div className="flex items-center gap-2">
                                                        <Shield className="h-4 w-4 text-green-600" />
                                                        <span className="text-sm">Trivy Configuration</span>
                                                    </div>
                                                </AccordionTrigger>
                                                <AccordionContent className="pt-2 space-y-4">
                                                    <div className="grid gap-3 pl-4">
                                                        <div className="grid gap-2">
                                                            <Label htmlFor="trivy-yaml" className="text-xs">
                                                                Config File (trivy.yaml)
                                                            </Label>
                                                            <Textarea
                                                                id="trivy-yaml"
                                                                placeholder={`timeout: 10m\nformat: json\nseverity:\n  - CRITICAL\n  - HIGH`}
                                                                value={scanConfig.trivy.trivyYaml || ""}
                                                                onChange={(e) =>
                                                                    updateTrivyConfig("trivyYaml", e.target.value)
                                                                }
                                                                rows={8}
                                                                className="font-mono text-xs"
                                                            />
                                                            <p className="text-xs text-muted-foreground">
                                                                Paste trivy.yaml content here
                                                            </p>
                                                        </div>
                                                    </div>
                                                </AccordionContent>
                                            </AccordionItem>
                                        )}
                                    </Accordion>

                                    {/* Per-Repo Overrides */}
                                    {repos.length > 0 && (
                                        <RepoScanOverrideSection
                                            repos={repos}
                                            scanConfig={scanConfig}
                                            onScanConfigChange={onScanConfigChange}
                                            disabled={disabled}
                                        />
                                    )}
                                </CardContent>
                            </CollapsibleContent>
                        </Card>
                    </Collapsible>
                )}
            </CollapsibleContent>
        </Collapsible>
    );
}

export { DEFAULT_SCAN_CONFIG, DEFAULT_ENABLED_TOOLS };
