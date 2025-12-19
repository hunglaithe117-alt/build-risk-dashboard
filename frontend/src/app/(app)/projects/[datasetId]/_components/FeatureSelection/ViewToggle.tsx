"use client";

import { LayoutGrid, List } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ViewToggleProps {
    value: "graph" | "list";
    onChange: (value: "graph" | "list") => void;
}

export function ViewToggle({ value, onChange }: ViewToggleProps) {
    return (
        <div className="flex items-center gap-1 rounded-lg border bg-slate-50 p-1 dark:bg-slate-800">
            <Button
                variant={value === "graph" ? "default" : "ghost"}
                size="sm"
                onClick={() => onChange("graph")}
                className="h-7 gap-1.5 px-2.5"
            >
                <LayoutGrid className="h-3.5 w-3.5" />
                Graph
            </Button>
            <Button
                variant={value === "list" ? "default" : "ghost"}
                size="sm"
                onClick={() => onChange("list")}
                className="h-7 gap-1.5 px-2.5"
            >
                <List className="h-3.5 w-3.5" />
                List
            </Button>
        </div>
    );
}
