"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import { ShieldCheck, Workflow, GitBranch, Settings2, Plus, GripVertical, LayoutGrid, Grid2x2, Grid3x3, LayoutPanelLeft, Download, Upload, Timer } from "lucide-react";

import GridLayout from "react-grid-layout";
import "react-grid-layout/css/styles.css";

// Define layout item type for react-grid-layout
interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  static?: boolean;
}

// Cast GridLayout to typed component to avoid type issues with v2.x
const RGL = GridLayout as unknown as React.ComponentType<{
  className?: string;
  layout: LayoutItem[];
  cols: number;
  rowHeight: number;
  width: number;
  onLayoutChange: (layout: LayoutItem[]) => void;
  isDraggable?: boolean;
  isResizable?: boolean;
  margin?: [number, number];
  containerPadding?: [number, number];
  useCSSTransforms?: boolean;
  children?: React.ReactNode;
}>;

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { dashboardApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import type { Build, DashboardSummaryResponse, WidgetConfig, WidgetDefinition } from "@/types";
import { useAuth } from "@/contexts/auth-context";
import { formatDuration, cn } from "@/lib/utils";

const GRID_COLS = 12; // Use 12-column grid for more flexibility
const GRID_COLS_LAPTOP = 6; // Laptop uses 6 columns for stacking
const LAPTOP_BREAKPOINT = 1280; // Below 1280px is Laptop mode (1024-1279px)
const ROW_HEIGHT = 100;

// Preset layouts
const PRESET_LAYOUTS = {
  // 4 equal stat cards in row 1, then 2 equal large widgets
  fourColumn: [
    { widget_id: "total_builds", x: 0, y: 0, w: 3, h: 1 },
    { widget_id: "success_rate", x: 3, y: 0, w: 3, h: 1 },
    { widget_id: "avg_duration", x: 6, y: 0, w: 3, h: 1 },
    { widget_id: "active_repos", x: 9, y: 0, w: 3, h: 1 },
    { widget_id: "repo_distribution", x: 0, y: 1, w: 6, h: 3 },
    { widget_id: "recent_builds", x: 6, y: 1, w: 6, h: 3 },
  ],
  // 2/3 split: 2 wide on left, 1 on right
  twoThirdSplit: [
    { widget_id: "total_builds", x: 0, y: 0, w: 4, h: 1 },
    { widget_id: "success_rate", x: 4, y: 0, w: 4, h: 1 },
    { widget_id: "avg_duration", x: 8, y: 0, w: 4, h: 1 },
    { widget_id: "active_repos", x: 0, y: 1, w: 4, h: 1 },
    { widget_id: "repo_distribution", x: 0, y: 2, w: 8, h: 3 },
    { widget_id: "recent_builds", x: 8, y: 1, w: 4, h: 4 },
  ],
  // 3 column layout
  threeColumn: [
    { widget_id: "total_builds", x: 0, y: 0, w: 4, h: 1 },
    { widget_id: "success_rate", x: 4, y: 0, w: 4, h: 1 },
    { widget_id: "avg_duration", x: 8, y: 0, w: 4, h: 1 },
    { widget_id: "active_repos", x: 0, y: 1, w: 4, h: 1 },
    { widget_id: "repo_distribution", x: 4, y: 1, w: 4, h: 3 },
    { widget_id: "recent_builds", x: 8, y: 1, w: 4, h: 3 },
  ],
  // Compact: all small
  compact: [
    { widget_id: "total_builds", x: 0, y: 0, w: 3, h: 1 },
    { widget_id: "success_rate", x: 3, y: 0, w: 3, h: 1 },
    { widget_id: "avg_duration", x: 6, y: 0, w: 3, h: 1 },
    { widget_id: "active_repos", x: 9, y: 0, w: 3, h: 1 },
    { widget_id: "repo_distribution", x: 0, y: 1, w: 6, h: 2 },
    { widget_id: "recent_builds", x: 6, y: 1, w: 6, h: 2 },
  ],
};

export default function OverviewPage() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const { authenticated, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [widgets, setWidgets] = useState<WidgetConfig[]>([]);
  const [availableWidgets, setAvailableWidgets] = useState<WidgetDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [recentBuilds, setRecentBuilds] = useState<Build[]>([]);

  // Measure container width
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };

    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  // Dynamic grid cols based on screen width
  const isLaptopView = containerWidth < LAPTOP_BREAKPOINT;
  const gridCols = isLaptopView ? GRID_COLS_LAPTOP : GRID_COLS;

  useEffect(() => {
    if (authLoading || !authenticated) {
      return;
    }

    let isActive = true;

    const loadData = async () => {
      setLoading(true);

      try {
        const [summaryResult, layoutResult, widgetsResult, buildsResult] = await Promise.all([
          dashboardApi.getSummary(),
          dashboardApi.getLayout(),
          dashboardApi.getAvailableWidgets(),
          dashboardApi.getRecentBuilds(10),
        ]);

        if (!isActive) {
          return;
        }

        setSummary(summaryResult);
        setRecentBuilds(buildsResult);
        setWidgets(layoutResult.widgets);
        setAvailableWidgets(widgetsResult);
      } catch (err) {
        console.error("Failed to load overview data", err);
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    };

    loadData();

    return () => {
      isActive = false;
    };
  }, [authenticated, authLoading]);

  const handleLayoutChange = useCallback((layout: LayoutItem[]) => {
    setWidgets((prev) =>
      prev.map((widget) => {
        const item = layout.find((l) => l.i === widget.widget_id);
        if (item) {
          return {
            ...widget,
            x: item.x,
            y: item.y,
            w: item.w,
            h: item.h,
          };
        }
        return widget;
      })
    );
  }, []);

  const handleSaveLayout = async () => {
    setIsSaving(true);
    try {
      await dashboardApi.saveLayout({ widgets });
      setIsEditing(false);
    } catch (err) {
      console.error("Failed to save layout", err);
    } finally {
      setIsSaving(false);
    }
  };

  const applyPreset = (presetName: keyof typeof PRESET_LAYOUTS) => {
    const preset = PRESET_LAYOUTS[presetName];
    setWidgets((prev) =>
      prev.map((widget) => {
        const presetItem = preset.find((p) => p.widget_id === widget.widget_id);
        if (presetItem) {
          return {
            ...widget,
            x: presetItem.x,
            y: presetItem.y,
            w: presetItem.w,
            h: presetItem.h,
            enabled: true,
          };
        }
        return widget;
      })
    );
  };

  const toggleWidget = (widgetId: string) => {
    setWidgets((prev) =>
      prev.map((w) =>
        w.widget_id === widgetId ? { ...w, enabled: !w.enabled } : w
      )
    );
  };

  const exportLayout = () => {
    const exportData = {
      version: 1,
      widgets: widgets.map((w) => ({
        widget_id: w.widget_id,
        widget_type: w.widget_type,
        title: w.title,
        enabled: w.enabled,
        x: w.x,
        y: w.y,
        w: w.w,
        h: w.h,
      })),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dashboard-layout-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importLayout = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const data = JSON.parse(event.target?.result as string);
          if (data.version === 1 && Array.isArray(data.widgets)) {
            setWidgets(data.widgets);
          } else {
            alert("Invalid layout file format");
          }
        } catch {
          alert("Failed to parse layout file");
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const addWidget = (definition: WidgetDefinition) => {
    const existingWidget = widgets.find((w) => w.widget_id === definition.widget_id);
    if (existingWidget) {
      setWidgets((prev) =>
        prev.map((w) =>
          w.widget_id === definition.widget_id ? { ...w, enabled: true } : w
        )
      );
    } else {
      const maxY = Math.max(...widgets.map((w) => w.y + w.h), 0);
      setWidgets((prev) => [
        ...prev,
        {
          widget_id: definition.widget_id,
          widget_type: definition.widget_type,
          title: definition.title,
          enabled: true,
          x: 0,
          y: maxY,
          w: definition.default_w * 3, // Scale to 12-col
          h: definition.default_h,
        },
      ]);
    }
  };

  const totalRepositories = summary?.repo_distribution?.length ?? 0;
  const enabledWidgets = widgets.filter((w) => w.enabled);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Loading overview...</CardTitle>
            <CardDescription>
              Connecting to the backend API to retrieve aggregated data.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Please wait a moment.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!summary || !summary.metrics) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="w-full max-w-md border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-900/20">
          <CardHeader>
            <CardTitle className="text-amber-600 dark:text-amber-300">
              No data available
            </CardTitle>
            <CardDescription>
              Overview data is not yet available. Import repositories or create datasets to get started.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const { metrics } = summary;

  const renderWidget = (widget: WidgetConfig) => {
    const commonCardClass = cn(
      "h-full overflow-hidden",
      isEditing && "ring-2 ring-blue-500/20 cursor-move"
    );

    switch (widget.widget_id) {
      case "total_builds":
        return (
          <StatCard
            className={commonCardClass}
            icon={<Workflow className="h-5 w-5 text-blue-500 flex-shrink-0" />}
            title={widget.title}
            value={metrics.total_builds}
            sublabel="All tracked builds"
            isEditing={isEditing}
          />
        );
      case "success_rate":
        return (
          <StatCard
            className={commonCardClass}
            icon={<ShieldCheck className="h-5 w-5 text-emerald-500 flex-shrink-0" />}
            title={widget.title}
            value={metrics.success_rate}
            format="percentage"
            sublabel="Build success ratio"
            isEditing={isEditing}
          />
        );
      case "avg_duration":
        return (
          <StatCard
            className={commonCardClass}
            icon={<Timer className="h-5 w-5 text-orange-500 flex-shrink-0" />}
            title={widget.title}
            value={metrics.average_duration_minutes}
            format="minutes"
            sublabel="Average build duration"
            isEditing={isEditing}
          />
        );
      case "active_repos":
        return (
          <StatCard
            className={commonCardClass}
            icon={<GitBranch className="h-5 w-5 text-purple-500 flex-shrink-0" />}
            title={widget.title}
            value={totalRepositories}
            sublabel="Connected via GitHub"
            isEditing={isEditing}
          />
        );
      case "repo_distribution":
        return (
          <Card className={commonCardClass}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Build count per repository
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-auto flex-1">
              <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
                <thead className="bg-slate-50 dark:bg-slate-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">Repository</th>
                    <th className="px-3 py-2 text-left font-semibold">Builds</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {summary.repo_distribution.length === 0 ? (
                    <tr>
                      <td className="px-3 py-4 text-center text-muted-foreground" colSpan={2}>
                        No repositories connected yet.
                      </td>
                    </tr>
                  ) : (
                    summary.repo_distribution.slice(0, 5).map((repo) => (
                      <tr
                        key={repo.id}
                        className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-900/50"
                        onClick={() => !isEditing && router.push(`/repositories/${repo.id}/builds`)}
                      >
                        <td className="px-3 py-2 font-medium truncate max-w-[150px]">{repo.repository}</td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {repo.builds.toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        );
      case "recent_builds":
        return (
          <Card className={commonCardClass}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Latest builds with risk level
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-auto flex-1">
              <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
                <thead className="bg-slate-50 dark:bg-slate-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">Build</th>
                    <th className="px-3 py-2 text-left font-semibold">Risk</th>
                    <th className="px-3 py-2 text-left font-semibold">Branch</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {recentBuilds.length === 0 ? (
                    <tr>
                      <td className="px-3 py-4 text-center text-muted-foreground" colSpan={3}>
                        No recent builds.
                      </td>
                    </tr>
                  ) : (
                    recentBuilds.slice(0, 5).map((build) => (
                      <tr
                        key={build.id}
                        className="transition hover:bg-slate-50 dark:hover:bg-slate-900/50"
                      >
                        <td className="px-3 py-2 font-medium truncate max-w-[100px]">
                          #{build.build_number || build.commit_sha?.slice(0, 7)}
                        </td>
                        <td className="px-3 py-2">
                          {build.predicted_label ? (
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${build.predicted_label === "LOW" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" :
                              build.predicted_label === "MEDIUM" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" :
                                build.predicted_label === "HIGH" ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" :
                                  "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400"
                              }`}>
                              {build.predicted_label}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground truncate max-w-[100px]">
                          {build.branch}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        );
      case "risk_trend":
        // Calculate risk distribution from recent builds
        const riskCounts = { LOW: 0, MEDIUM: 0, HIGH: 0 };
        recentBuilds.forEach((b) => {
          if (b.predicted_label === "LOW") riskCounts.LOW++;
          else if (b.predicted_label === "MEDIUM") riskCounts.MEDIUM++;
          else if (b.predicted_label === "HIGH") riskCounts.HIGH++;
        });
        const hasRiskData = riskCounts.LOW + riskCounts.MEDIUM + riskCounts.HIGH > 0;

        return (
          <Card className={commonCardClass}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Recent build risk levels
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center h-[calc(100%-60px)]">
              {hasRiskData ? (
                <div className="w-full space-y-2 px-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs w-12">LOW</span>
                    <div className="flex-1 h-4 bg-slate-100 dark:bg-slate-800 rounded overflow-hidden">
                      <div
                        className="h-full bg-green-500"
                        style={{ width: `${(riskCounts.LOW / recentBuilds.length) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs w-6 text-right">{riskCounts.LOW}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs w-12">MED</span>
                    <div className="flex-1 h-4 bg-slate-100 dark:bg-slate-800 rounded overflow-hidden">
                      <div
                        className="h-full bg-amber-500"
                        style={{ width: `${(riskCounts.MEDIUM / recentBuilds.length) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs w-6 text-right">{riskCounts.MEDIUM}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs w-12">HIGH</span>
                    <div className="flex-1 h-4 bg-slate-100 dark:bg-slate-800 rounded overflow-hidden">
                      <div
                        className="h-full bg-red-500"
                        style={{ width: `${(riskCounts.HIGH / recentBuilds.length) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs w-6 text-right">{riskCounts.HIGH}</span>
                  </div>
                </div>
              ) : (
                <div className="text-center space-y-2">
                  <ShieldCheck className="h-8 w-8 mx-auto text-muted-foreground/50" />
                  <p className="text-xs text-muted-foreground">
                    No prediction data available
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        );
      case "risk_distribution":
        // Donut-style display of risk levels
        const distCounts = { LOW: 0, MEDIUM: 0, HIGH: 0 };
        recentBuilds.forEach((b) => {
          if (b.predicted_label === "LOW") distCounts.LOW++;
          else if (b.predicted_label === "MEDIUM") distCounts.MEDIUM++;
          else if (b.predicted_label === "HIGH") distCounts.HIGH++;
        });
        const totalPredicted = distCounts.LOW + distCounts.MEDIUM + distCounts.HIGH;

        return (
          <Card className={commonCardClass}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Risk level breakdown
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center h-[calc(100%-60px)]">
              {totalPredicted > 0 ? (
                <div className="flex items-center gap-4">
                  <div className="flex flex-col items-center">
                    <div className="text-2xl font-bold text-green-600">{distCounts.LOW}</div>
                    <div className="text-xs text-muted-foreground">Low</div>
                  </div>
                  <div className="flex flex-col items-center">
                    <div className="text-2xl font-bold text-amber-600">{distCounts.MEDIUM}</div>
                    <div className="text-xs text-muted-foreground">Medium</div>
                  </div>
                  <div className="flex flex-col items-center">
                    <div className="text-2xl font-bold text-red-600">{distCounts.HIGH}</div>
                    <div className="text-xs text-muted-foreground">High</div>
                  </div>
                </div>
              ) : (
                <div className="text-center space-y-2">
                  <ShieldCheck className="h-8 w-8 mx-auto text-muted-foreground/50" />
                  <p className="text-xs text-muted-foreground">
                    No predictions yet
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        );
      case "high_risk_builds":
        const highRiskCount = recentBuilds.filter((b) => b.predicted_label === "HIGH").length;
        return (
          <StatCard
            className={cn(commonCardClass, highRiskCount > 0 && "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20")}
            icon={<ShieldCheck className={`h-5 w-5 flex-shrink-0 ${highRiskCount > 0 ? "text-red-500" : "text-muted-foreground"}`} />}
            title={widget.title}
            value={highRiskCount}
            sublabel="Predicted as HIGH risk"
            isEditing={isEditing}
          />
        );
      // Admin-only widgets
      case "dataset_enrichment_summary":
        const enrichmentStats = summary?.admin_extras?.dataset_enrichment;
        return (
          <Card className={commonCardClass}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Dataset Enrichment Pipeline
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center gap-4 h-[calc(100%-60px)]">
              <div className="flex flex-col items-center">
                <div className="text-2xl font-bold text-blue-600">{enrichmentStats?.active_projects ?? 0}</div>
                <div className="text-xs text-muted-foreground">Projects</div>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-2xl font-bold text-amber-600">{enrichmentStats?.processing_versions ?? 0}</div>
                <div className="text-xs text-muted-foreground">Processing</div>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-2xl font-bold text-green-600">{enrichmentStats?.total_enriched_builds ?? 0}</div>
                <div className="text-xs text-muted-foreground">Enriched</div>
              </div>
            </CardContent>
          </Card>
        );
      case "monitoring_summary":
        const monitoringStats = summary?.admin_extras?.monitoring;
        const hasErrors = (monitoringStats?.error_count_24h ?? 0) > 0;
        return (
          <Card className={cn(commonCardClass, hasErrors && "border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-900/20")}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                System monitoring (24h)
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center gap-4 h-[calc(100%-60px)]">
              <div className="flex flex-col items-center">
                <div className={`text-2xl font-bold ${hasErrors ? "text-amber-600" : "text-green-600"}`}>
                  {monitoringStats?.error_count_24h ?? 0}
                </div>
                <div className="text-xs text-muted-foreground">Errors</div>
              </div>
            </CardContent>
          </Card>
        );
      case "user_activity":
        const totalUsers = summary?.admin_extras?.total_users ?? 0;
        return (
          <StatCard
            className={commonCardClass}
            icon={<GitBranch className="h-5 w-5 text-indigo-500 flex-shrink-0" />}
            title={widget.title}
            value={totalUsers}
            sublabel="Registered users"
            isEditing={isEditing}
          />
        );
      // User-only widget
      case "getting_started":
        const hasRepos = totalRepositories > 0;
        const hasBuilds = metrics.total_builds > 0;
        if (hasRepos && hasBuilds) {
          // User already has data, show minimal widget
          return (
            <Card className={commonCardClass}>
              <CardContent className="flex items-center justify-center h-full">
                <div className="text-center space-y-2">
                  <ShieldCheck className="h-8 w-8 mx-auto text-green-500" />
                  <p className="text-sm font-medium text-green-600">You&apos;re all set!</p>
                  <p className="text-xs text-muted-foreground">
                    {totalRepositories} repos, {metrics.total_builds} builds
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        }
        return (
          <Card className={cn(commonCardClass, "border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-900/20")}>
            {isEditing && (
              <div className="absolute top-2 left-2 z-10">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <CardHeader className="pb-2">
              <CardTitle className="text-sm truncate">{widget.title}</CardTitle>
              <CardDescription className="text-xs truncate">
                Quick start guide
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 overflow-auto">
              <div className="flex items-center gap-2">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${hasRepos ? "bg-green-500 text-white" : "bg-blue-500 text-white"}`}>
                  {hasRepos ? "✓" : "1"}
                </div>
                <span className={`text-sm ${hasRepos ? "line-through text-muted-foreground" : ""}`}>
                  Import a repository
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${hasBuilds ? "bg-green-500 text-white" : "bg-slate-300 text-slate-600"}`}>
                  {hasBuilds ? "✓" : "2"}
                </div>
                <span className={`text-sm ${hasBuilds ? "line-through text-muted-foreground" : "text-muted-foreground"}`}>
                  Wait for ingestion
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-slate-300 text-slate-600">
                  3
                </div>
                <span className="text-sm text-muted-foreground">Start processing</span>
              </div>
              {!hasRepos && !isEditing && (
                <button
                  onClick={() => router.push("/repositories/import")}
                  className="mt-2 w-full px-3 py-1.5 text-xs font-medium text-white bg-blue-500 rounded hover:bg-blue-600 transition"
                >
                  Import Repository
                </button>
              )}
            </CardContent>
          </Card>
        );
      default:
        return (
          <Card className={commonCardClass}>
            <CardContent className="flex items-center justify-center h-full">
              <p className="text-sm text-muted-foreground truncate">
                Unknown widget: {widget.widget_id}
              </p>
            </CardContent>
          </Card>
        );
    }
  };

  const layout = enabledWidgets.map((widget) => ({
    i: widget.widget_id,
    x: widget.x,
    y: widget.y,
    w: widget.w,
    h: widget.h,
    minW: 2,
    minH: 1,
    static: !isEditing,
  }));

  return (
    <div className="space-y-4" ref={containerRef}>
      {/* Header with edit controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold">Dashboard Overview</h2>
          <p className="text-sm text-muted-foreground">
            {isEditing ? "Drag widgets to rearrange or use presets" : "Your customizable overview"}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {isEditing ? (
            <>
              {/* Preset Layout Buttons */}
              <div className="flex items-center gap-1 border rounded-md p-1 bg-muted/50">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => applyPreset("fourColumn")}
                  title="4 Equal Columns"
                  className="h-7 px-2"
                >
                  <Grid2x2 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => applyPreset("threeColumn")}
                  title="3 Column Layout"
                  className="h-7 px-2"
                >
                  <Grid3x3 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => applyPreset("twoThirdSplit")}
                  title="2/3 Split"
                  className="h-7 px-2"
                >
                  <LayoutPanelLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => applyPreset("compact")}
                  title="Compact Layout"
                  className="h-7 px-2"
                >
                  <LayoutGrid className="h-4 w-4" />
                </Button>
              </div>

              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Plus className="h-4 w-4 mr-1" />
                    Widgets
                  </Button>
                </SheetTrigger>
                <SheetContent>
                  <SheetHeader>
                    <SheetTitle>Available Widgets</SheetTitle>
                    <SheetDescription>
                      Toggle widgets to show/hide them on your dashboard
                    </SheetDescription>
                  </SheetHeader>
                  <div className="mt-4 space-y-4">
                    {availableWidgets.map((widget) => {
                      const isEnabled = widgets.find(
                        (w) => w.widget_id === widget.widget_id
                      )?.enabled;
                      return (
                        <div
                          key={widget.widget_id}
                          className="flex items-center justify-between py-2 border-b"
                        >
                          <div>
                            <p className="font-medium text-sm">{widget.title}</p>
                            <p className="text-xs text-muted-foreground">
                              {widget.description}
                            </p>
                          </div>
                          <Switch
                            checked={isEnabled ?? false}
                            onCheckedChange={() => {
                              if (isEnabled) {
                                toggleWidget(widget.widget_id);
                              } else {
                                addWidget(widget);
                              }
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-6 border-t pt-4 space-y-2">
                    <p className="text-xs text-muted-foreground mb-2">Layout Management</p>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={exportLayout} className="flex-1 gap-1">
                        <Download className="h-3 w-3" /> Export
                      </Button>
                      <Button variant="outline" size="sm" onClick={importLayout} className="flex-1 gap-1">
                        <Upload className="h-3 w-3" /> Import
                      </Button>
                    </div>
                  </div>
                </SheetContent>
              </Sheet>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsEditing(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSaveLayout}
                disabled={isSaving}
              >
                {isSaving ? "Saving..." : "Save Layout"}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsEditing(true)}
            >
              <Settings2 className="h-4 w-4 mr-1" />
              Customize
            </Button>
          )}
        </div>
      </div>

      {/* Grid Layout */}
      <RGL
        className="layout"
        layout={layout}
        cols={gridCols}
        rowHeight={isLaptopView ? 90 : ROW_HEIGHT}
        width={containerWidth}
        onLayoutChange={handleLayoutChange}
        isDraggable={isEditing}
        isResizable={isEditing}
        margin={isLaptopView ? [8, 8] : [12, 12]}
        containerPadding={[0, 0]}
        useCSSTransforms
      >
        {enabledWidgets.map((widget) => (
          <div key={widget.widget_id} className="relative">
            {renderWidget(widget)}
          </div>
        ))}
      </RGL>
    </div>
  );
}

interface StatCardProps {
  icon: ReactNode;
  title: string;
  value: number;
  format?: "score" | "percentage" | "minutes";
  sublabel?: string;
  className?: string;
  isEditing?: boolean;
}

function StatCard({
  icon,
  title,
  value,
  format,
  sublabel,
  className,
  isEditing,
}: StatCardProps) {
  const formattedValue =
    format === "score"
      ? value.toFixed(2)
      : format === "percentage"
        ? `${value.toFixed(1)}%`
        : format === "minutes"
          ? formatDuration(value)
          : value;

  return (
    <Card className={cn("relative flex flex-col", className)}>
      {isEditing && (
        <div className="absolute top-2 left-2 z-10">
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </div>
      )}
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1 pt-3 px-4">
        <CardTitle className="text-xs font-medium text-muted-foreground truncate pr-2">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent className="pb-3 px-4 flex-1">
        <div className="text-xl font-bold truncate">{formattedValue}</div>
        {sublabel ? (
          <p className="text-[10px] text-muted-foreground truncate">{sublabel}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
