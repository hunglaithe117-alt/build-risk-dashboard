"use client";

import { useState, useEffect, useCallback } from "react";
import { Check, Search, Info, Loader2, BarChart3, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { settingsApi } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// =============================================================================
// Types
// =============================================================================

interface MetricDefinition {
    key: string;
    display_name: string;
    description: string;
    data_type: string;
}

interface ToolMetrics {
    metrics: Record<string, MetricDefinition[]>;
    all_keys: string[];
}

interface AvailableMetrics {
    sonarqube: ToolMetrics;
    trivy: ToolMetrics;
}

interface ScanMetricsSelectorProps {
    selectedSonarMetrics: string[];
    selectedTrivyMetrics: string[];
    onSonarChange: (metrics: string[]) => void;
    onTrivyChange: (metrics: string[]) => void;
    className?: string;
    showOnlyTool?: "sonarqube" | "trivy";
}

// =============================================================================
// Constants
// =============================================================================

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
    reliability: <BarChart3 className="h-4 w-4" />,
    security: <Shield className="h-4 w-4" />,
    maintainability: <BarChart3 className="h-4 w-4" />,
    coverage: <BarChart3 className="h-4 w-4" />,
    duplication: <BarChart3 className="h-4 w-4" />,
    complexity: <BarChart3 className="h-4 w-4" />,
    size: <BarChart3 className="h-4 w-4" />,
    code_quality: <BarChart3 className="h-4 w-4" />,
    metadata: <Info className="h-4 w-4" />,
    vulnerability: <Shield className="h-4 w-4" />,
    license: <Info className="h-4 w-4" />,
    secret: <Shield className="h-4 w-4" />,
};

const CATEGORY_COLORS: Record<string, string> = {
    reliability: "bg-blue-500/10 text-blue-600 border-blue-200",
    security: "bg-red-500/10 text-red-600 border-red-200",
    maintainability: "bg-amber-500/10 text-amber-600 border-amber-200",
    coverage: "bg-green-500/10 text-green-600 border-green-200",
    duplication: "bg-purple-500/10 text-purple-600 border-purple-200",
    complexity: "bg-orange-500/10 text-orange-600 border-orange-200",
    size: "bg-gray-500/10 text-gray-600 border-gray-200",
    code_quality: "bg-cyan-500/10 text-cyan-600 border-cyan-200",
    metadata: "bg-slate-500/10 text-slate-600 border-slate-200",
    vulnerability: "bg-red-500/10 text-red-600 border-red-200",
    license: "bg-yellow-500/10 text-yellow-600 border-yellow-200",
    secret: "bg-pink-500/10 text-pink-600 border-pink-200",
};

// =============================================================================
// Component
// =============================================================================

export function ScanMetricsSelector({
    selectedSonarMetrics,
    selectedTrivyMetrics,
    onSonarChange,
    onTrivyChange,
    className,
    showOnlyTool,
}: ScanMetricsSelectorProps) {
    const [availableMetrics, setAvailableMetrics] = useState<AvailableMetrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [activeTab, setActiveTab] = useState<string>(showOnlyTool || "sonarqube");

    // Fetch available metrics on mount
    useEffect(() => {
        const fetchMetrics = async () => {
            try {
                setLoading(true);
                const data = await settingsApi.getAvailableMetrics();
                setAvailableMetrics(data);
            } catch (err) {
                console.error("Failed to fetch available metrics:", err);
                setError("Failed to load available metrics");
            } finally {
                setLoading(false);
            }
        };
        fetchMetrics();
    }, []);

    // Toggle metric selection
    const handleToggleSonar = useCallback(
        (key: string) => {
            if (selectedSonarMetrics.includes(key)) {
                onSonarChange(selectedSonarMetrics.filter((k) => k !== key));
            } else {
                onSonarChange([...selectedSonarMetrics, key]);
            }
        },
        [selectedSonarMetrics, onSonarChange]
    );

    const handleToggleTrivy = useCallback(
        (key: string) => {
            if (selectedTrivyMetrics.includes(key)) {
                onTrivyChange(selectedTrivyMetrics.filter((k) => k !== key));
            } else {
                onTrivyChange([...selectedTrivyMetrics, key]);
            }
        },
        [selectedTrivyMetrics, onTrivyChange]
    );

    // Select/Deselect all in a category
    const handleSelectAllInCategory = (
        tool: "sonarqube" | "trivy",
        category: string,
        metrics: MetricDefinition[]
    ) => {
        const keys = metrics.map((m) => m.key);

        if (tool === "sonarqube") {
            const allSelected = keys.every((k) => selectedSonarMetrics.includes(k));
            if (allSelected) {
                onSonarChange(selectedSonarMetrics.filter((k) => !keys.includes(k)));
            } else {
                onSonarChange([...new Set([...selectedSonarMetrics, ...keys])]);
            }
        } else {
            const allSelected = keys.every((k) => selectedTrivyMetrics.includes(k));
            if (allSelected) {
                onTrivyChange(selectedTrivyMetrics.filter((k) => !keys.includes(k)));
            } else {
                onTrivyChange([...new Set([...selectedTrivyMetrics, ...keys])]);
            }
        }
    };

    // Filter metrics by search query
    const filterMetrics = (metrics: Record<string, MetricDefinition[]>) => {
        if (!searchQuery) return metrics;

        const filtered: Record<string, MetricDefinition[]> = {};
        for (const [category, items] of Object.entries(metrics)) {
            const matchingItems = items.filter(
                (m) =>
                    m.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    m.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    m.description.toLowerCase().includes(searchQuery.toLowerCase())
            );
            if (matchingItems.length > 0) {
                filtered[category] = matchingItems;
            }
        }
        return filtered;
    };

    // Render metric item
    const renderMetricItem = (
        metric: MetricDefinition,
        isSelected: boolean,
        onToggle: () => void
    ) => (
        <div
            key={metric.key}
            className={cn(
                "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all",
                isSelected
                    ? "bg-primary/5 border-primary/30"
                    : "hover:bg-muted/50 border-transparent"
            )}
            onClick={onToggle}
        >
            <Checkbox checked={isSelected} className="mt-0.5" />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{metric.display_name}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {metric.data_type}
                    </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {metric.description}
                </p>
                <code className="text-[10px] text-muted-foreground/70 font-mono">
                    {metric.key}
                </code>
            </div>
            {isSelected && <Check className="h-4 w-4 text-primary shrink-0" />}
        </div>
    );

    // Render category accordion
    const renderCategory = (
        tool: "sonarqube" | "trivy",
        category: string,
        metrics: MetricDefinition[],
        selectedMetrics: string[],
        onToggle: (key: string) => void
    ) => {
        const selectedCount = metrics.filter((m) => selectedMetrics.includes(m.key)).length;
        const allSelected = selectedCount === metrics.length;

        return (
            <AccordionItem key={category} value={category}>
                <AccordionTrigger className="hover:no-underline px-2">
                    <div className="flex items-center gap-3 flex-1">
                        <span className="font-medium capitalize">
                            {category.replace(/_/g, " ")}
                        </span>
                        <Badge variant="secondary" className="ml-auto mr-2">
                            {selectedCount}/{metrics.length}
                        </Badge>
                    </div>
                </AccordionTrigger>
                <AccordionContent className="px-2">
                    <div className="flex justify-end mb-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={(e) => {
                                e.stopPropagation();
                                handleSelectAllInCategory(tool, category, metrics);
                            }}
                        >
                            {allSelected ? "Deselect All" : "Select All"}
                        </Button>
                    </div>
                    <div className="grid gap-2">
                        {metrics.map((metric) =>
                            renderMetricItem(metric, selectedMetrics.includes(metric.key), () =>
                                onToggle(metric.key)
                            )
                        )}
                    </div>
                </AccordionContent>
            </AccordionItem>
        );
    };

    if (loading) {
        return (
            <div className={cn("flex items-center justify-center p-8", className)}>
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Loading available metrics...</span>
            </div>
        );
    }

    if (error || !availableMetrics) {
        return (
            <div className={cn("text-center p-8 text-destructive", className)}>
                {error || "No metrics available"}
            </div>
        );
    }

    const filteredSonarMetrics = filterMetrics(availableMetrics.sonarqube.metrics);
    const filteredTrivyMetrics = filterMetrics(availableMetrics.trivy.metrics);

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header - only show when displaying both tools */}
            {!showOnlyTool && (
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h3 className="text-lg font-semibold">Select Scan Metrics</h3>
                        <p className="text-sm text-muted-foreground">
                            Choose metrics to include in your dataset features
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 text-sm mr-4">
                            <Badge variant="outline" className="bg-blue-50">
                                <BarChart3 className="h-3 w-3 mr-1" />
                                SonarQube: {selectedSonarMetrics.length}
                            </Badge>
                            <Badge variant="outline" className="bg-green-50">
                                <Shield className="h-3 w-3 mr-1" />
                                Trivy: {selectedTrivyMetrics.length}
                            </Badge>
                        </div>

                        <div className="h-4 w-px bg-border mx-1" />

                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={() => {
                                if (availableMetrics) {
                                    onSonarChange(availableMetrics.sonarqube.all_keys);
                                    onTrivyChange(availableMetrics.trivy.all_keys);
                                }
                            }}
                        >
                            Select All
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={() => {
                                onSonarChange([]);
                                onTrivyChange([]);
                            }}
                        >
                            Clear All
                        </Button>
                    </div>
                </div>
            )}

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search metrics by name or description..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                />
            </div>

            {/* Tabs - only show when displaying both tools */}
            {showOnlyTool ? (
                // Single tool view - no tabs
                <div className="mt-2">
                    <div className="flex justify-end gap-2 mb-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={() => {
                                if (!availableMetrics) return;
                                if (showOnlyTool === "sonarqube") {
                                    onSonarChange(availableMetrics.sonarqube.all_keys);
                                } else {
                                    onTrivyChange(availableMetrics.trivy.all_keys);
                                }
                            }}
                        >
                            Select All
                        </Button>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={() => {
                                if (showOnlyTool === "sonarqube") {
                                    onSonarChange([]);
                                } else {
                                    onTrivyChange([]);
                                }
                            }}
                            disabled={showOnlyTool === "sonarqube" ? selectedSonarMetrics.length === 0 : selectedTrivyMetrics.length === 0}
                        >
                            Clear All
                        </Button>
                    </div>
                    {showOnlyTool === "sonarqube" && (
                        <ScrollArea className="h-[300px] pr-4">
                            <Accordion type="multiple" className="space-y-2">
                                {Object.entries(filteredSonarMetrics).map(([category, metrics]) =>
                                    renderCategory(
                                        "sonarqube",
                                        category,
                                        metrics,
                                        selectedSonarMetrics,
                                        handleToggleSonar
                                    )
                                )}
                            </Accordion>
                            {Object.keys(filteredSonarMetrics).length === 0 && (
                                <div className="text-center py-8 text-muted-foreground">
                                    No metrics match your search
                                </div>
                            )}
                        </ScrollArea>
                    )}
                    {showOnlyTool === "trivy" && (
                        <ScrollArea className="h-[300px] pr-4">
                            <Accordion type="multiple" className="space-y-2">
                                {Object.entries(filteredTrivyMetrics).map(([category, metrics]) =>
                                    renderCategory(
                                        "trivy",
                                        category,
                                        metrics,
                                        selectedTrivyMetrics,
                                        handleToggleTrivy
                                    )
                                )}
                            </Accordion>
                            {Object.keys(filteredTrivyMetrics).length === 0 && (
                                <div className="text-center py-8 text-muted-foreground">
                                    No metrics match your search
                                </div>
                            )}
                        </ScrollArea>
                    )}
                </div>
            ) : (
                // Both tools view - with tabs
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <div className="flex items-center justify-between mb-2">
                        <TabsList className="grid w-[60%] grid-cols-2">
                            <TabsTrigger value="sonarqube" className="gap-2">
                                <BarChart3 className="h-4 w-4" />
                                SonarQube
                                <Badge variant="secondary" className="ml-1">
                                    {selectedSonarMetrics.length}
                                </Badge>
                            </TabsTrigger>
                            <TabsTrigger value="trivy" className="gap-2">
                                <Shield className="h-4 w-4" />
                                Trivy
                                <Badge variant="secondary" className="ml-1">
                                    {selectedTrivyMetrics.length}
                                </Badge>
                            </TabsTrigger>
                        </TabsList>

                        {/* Tab-specific actions (e.g., Clear All for current tab only) could go here if needed */}
                        <div className="flex gap-1 ml-auto">
                            {activeTab === 'sonarqube' ? (
                                <>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs h-7"
                                        onClick={() => availableMetrics && onSonarChange(availableMetrics.sonarqube.all_keys)}
                                    >
                                        Select All
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs h-7"
                                        onClick={() => onSonarChange([])}
                                        disabled={selectedSonarMetrics.length === 0}
                                    >
                                        Clear Sonar
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs h-7"
                                        onClick={() => availableMetrics && onTrivyChange(availableMetrics.trivy.all_keys)}
                                    >
                                        Select All
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-xs h-7"
                                        onClick={() => onTrivyChange([])}
                                        disabled={selectedTrivyMetrics.length === 0}
                                    >
                                        Clear Trivy
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>

                    <TabsContent value="sonarqube" className="mt-4">
                        <ScrollArea className="h-[400px] pr-4">
                            <Accordion type="multiple" className="space-y-2">
                                {Object.entries(filteredSonarMetrics).map(([category, metrics]) =>
                                    renderCategory(
                                        "sonarqube",
                                        category,
                                        metrics,
                                        selectedSonarMetrics,
                                        handleToggleSonar
                                    )
                                )}
                            </Accordion>
                            {Object.keys(filteredSonarMetrics).length === 0 && (
                                <div className="text-center py-8 text-muted-foreground">
                                    No metrics match your search
                                </div>
                            )}
                        </ScrollArea>
                    </TabsContent>

                    <TabsContent value="trivy" className="mt-4">
                        <ScrollArea className="h-[400px] pr-4">
                            <Accordion type="multiple" className="space-y-2">
                                {Object.entries(filteredTrivyMetrics).map(([category, metrics]) =>
                                    renderCategory(
                                        "trivy",
                                        category,
                                        metrics,
                                        selectedTrivyMetrics,
                                        handleToggleTrivy
                                    )
                                )}
                            </Accordion>
                            {Object.keys(filteredTrivyMetrics).length === 0 && (
                                <div className="text-center py-8 text-muted-foreground">
                                    No metrics match your search
                                </div>
                            )}
                        </ScrollArea>
                    </TabsContent>
                </Tabs>
            )}
        </div>
    );
}
