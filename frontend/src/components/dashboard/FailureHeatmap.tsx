"use client";

import { useEffect, useState } from "react";
import { dashboardApi } from "@/lib/api";

/**
 * Failure Heatmap - shows build failures by day of week and hour
 */
export function FailureHeatmap() {
    const [data, setData] = useState<number[][]>([]);
    const [loading, setLoading] = useState(true);

    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const hours = Array.from({ length: 24 }, (_, i) => i);

    useEffect(() => {
        const loadData = async () => {
            try {
                // Initialize with empty heatmap (7 days x 24 hours)
                const heatmap = Array.from({ length: 7 }, () => Array(24).fill(0));

                // Get recent builds and aggregate failures
                const builds = await dashboardApi.getRecentBuilds(100);

                for (const build of builds) {
                    if (build.conclusion === "failure" || build.conclusion === "failed") {
                        if (!build.created_at) continue;
                        const date = new Date(build.created_at);
                        const day = date.getDay(); // 0-6
                        const hour = date.getHours(); // 0-23
                        heatmap[day][hour] = (heatmap[day][hour] || 0) + 1;
                    }
                }

                setData(heatmap);
            } catch (err) {
                console.error("Failed to load heatmap data", err);
                // Set empty data on error
                setData(Array.from({ length: 7 }, () => Array(24).fill(0)));
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, []);

    const maxValue = Math.max(...data.flat(), 1);

    const getColor = (value: number) => {
        if (value === 0) return "bg-slate-100 dark:bg-slate-800";
        const intensity = value / maxValue;
        if (intensity < 0.25) return "bg-red-100 dark:bg-red-900/30";
        if (intensity < 0.5) return "bg-red-200 dark:bg-red-800/50";
        if (intensity < 0.75) return "bg-red-300 dark:bg-red-700/70";
        return "bg-red-500 dark:bg-red-600";
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-xs text-muted-foreground">Loading...</div>
            </div>
        );
    }

    return (
        <div className="w-full h-full overflow-hidden">
            <div className="flex flex-col gap-[2px]">
                {/* Hour labels (top) */}
                <div className="flex gap-[2px] ml-8">
                    {hours.filter((_, i) => i % 4 === 0).map((h) => (
                        <div
                            key={h}
                            className="text-[8px] text-muted-foreground text-center"
                            style={{ width: "calc((100% - 32px) / 6)" }}
                        >
                            {h}:00
                        </div>
                    ))}
                </div>

                {/* Heatmap grid */}
                {days.map((day, dayIdx) => (
                    <div key={day} className="flex gap-[2px] items-center">
                        <div className="w-8 text-[10px] text-muted-foreground text-right pr-1">
                            {day}
                        </div>
                        <div className="flex-1 flex gap-[1px]">
                            {hours.map((hour) => (
                                <div
                                    key={`${dayIdx}-${hour}`}
                                    className={`flex-1 aspect-square rounded-[2px] ${getColor(data[dayIdx]?.[hour] || 0)}`}
                                    title={`${day} ${hour}:00 - ${data[dayIdx]?.[hour] || 0} failures`}
                                />
                            ))}
                        </div>
                    </div>
                ))}

                {/* Legend */}
                <div className="flex items-center justify-end gap-2 mt-1 text-[9px] text-muted-foreground">
                    <span>Less</span>
                    <div className="flex gap-[2px]">
                        <div className="w-2 h-2 rounded-[2px] bg-slate-100 dark:bg-slate-800" />
                        <div className="w-2 h-2 rounded-[2px] bg-red-100 dark:bg-red-900/30" />
                        <div className="w-2 h-2 rounded-[2px] bg-red-200 dark:bg-red-800/50" />
                        <div className="w-2 h-2 rounded-[2px] bg-red-300 dark:bg-red-700/70" />
                        <div className="w-2 h-2 rounded-[2px] bg-red-500 dark:bg-red-600" />
                    </div>
                    <span>More</span>
                </div>
            </div>
        </div>
    );
}
