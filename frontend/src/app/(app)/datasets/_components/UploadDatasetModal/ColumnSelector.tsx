"use client";

import { useState, useRef, useMemo } from "react";
import { Check, ChevronsUpDown, Search } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ColumnSelectorProps } from "./types";

export function ColumnSelector({
    value,
    columns,
    onChange,
    placeholder = "Select column",
}: ColumnSelectorProps) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    const filteredColumns = useMemo(() => {
        if (!search) return columns;
        const lower = search.toLowerCase();
        return columns.filter(col => col.toLowerCase().includes(lower));
    }, [columns, search]);

    const selectedLabel = value || placeholder;

    return (
        <div className="relative">
            <button
                type="button"
                onClick={() => {
                    setOpen(!open);
                    if (!open) {
                        setTimeout(() => inputRef.current?.focus(), 50);
                    }
                }}
                className={cn(
                    "flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background",
                    "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    !value && "text-muted-foreground"
                )}
            >
                <span className="truncate">{selectedLabel}</span>
                <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
            </button>

            {open && (
                <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg">
                    <div className="flex items-center border-b px-2 py-1.5">
                        <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                        <input
                            ref={inputRef}
                            type="text"
                            placeholder="Search columns..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="flex h-7 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                        />
                    </div>

                    <ScrollArea className="max-h-48">
                        <div className="p-1">
                            <button
                                type="button"
                                onClick={() => {
                                    onChange("");
                                    setOpen(false);
                                    setSearch("");
                                }}
                                className={cn(
                                    "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none",
                                    "hover:bg-accent hover:text-accent-foreground",
                                    !value && "bg-accent"
                                )}
                            >
                                {!value && (
                                    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                        <Check className="h-4 w-4" />
                                    </span>
                                )}
                                <span className="text-muted-foreground">-- Not mapped --</span>
                            </button>

                            {filteredColumns.length === 0 ? (
                                <div className="py-2 text-center text-sm text-muted-foreground">
                                    No columns found
                                </div>
                            ) : (
                                filteredColumns.map((col) => (
                                    <button
                                        key={col}
                                        type="button"
                                        onClick={() => {
                                            onChange(col);
                                            setOpen(false);
                                            setSearch("");
                                        }}
                                        className={cn(
                                            "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none",
                                            "hover:bg-accent hover:text-accent-foreground",
                                            value === col && "bg-accent"
                                        )}
                                    >
                                        {value === col && (
                                            <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                                                <Check className="h-4 w-4" />
                                            </span>
                                        )}
                                        <span className="truncate">{col}</span>
                                    </button>
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </div>
            )}

            {open && (
                <div
                    className="fixed inset-0 z-40"
                    onClick={() => {
                        setOpen(false);
                        setSearch("");
                    }}
                />
            )}
        </div>
    );
}
