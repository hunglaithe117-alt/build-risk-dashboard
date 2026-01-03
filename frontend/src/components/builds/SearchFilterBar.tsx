"use client";

import { Search, X, Filter } from "lucide-react";
import { useState, useCallback, useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useDebounce } from "@/hooks/use-debounce";

interface StatusOption {
    value: string;
    label: string;
}

interface SearchFilterBarProps {
    placeholder?: string;
    statusOptions: StatusOption[];
    onSearch: (searchQuery: string) => void;
    onStatusFilter: (status: string) => void;
    isLoading?: boolean;
    defaultStatus?: string;
}

export function SearchFilterBar({
    placeholder = "Search by commit SHA or build number...",
    statusOptions,
    onSearch,
    onStatusFilter,
    isLoading = false,
    defaultStatus = "all",
}: SearchFilterBarProps) {
    const [searchValue, setSearchValue] = useState("");
    const [status, setStatus] = useState(defaultStatus);

    // Debounce search value
    const debouncedSearchValue = useDebounce(searchValue, 300);

    // Trigger search when debounced value changes
    useEffect(() => {
        onSearch(debouncedSearchValue);
    }, [debouncedSearchValue, onSearch]);

    const handleSearchChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            setSearchValue(e.target.value);
        },
        []
    );

    const handleClearSearch = useCallback(() => {
        setSearchValue("");
    }, []);

    const handleStatusChange = useCallback(
        (value: string) => {
            setStatus(value);
            onStatusFilter(value);
        },
        [onStatusFilter]
    );

    return (
        <div className="flex items-center gap-3">
            {/* Search Input */}
            <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder={placeholder}
                    value={searchValue}
                    onChange={handleSearchChange}
                    className="pl-9 pr-8"
                    disabled={isLoading}
                />
                {searchValue && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6 p-0"
                        onClick={handleClearSearch}
                    >
                        <X className="h-3 w-3" />
                    </Button>
                )}
            </div>

            {/* Status Filter */}
            <Select value={status} onValueChange={handleStatusChange} disabled={isLoading}>
                <SelectTrigger className="w-[160px]">
                    <Filter className="mr-2 h-4 w-4" />
                    <SelectValue placeholder="Filter status" />
                </SelectTrigger>
                <SelectContent>
                    {statusOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                            {option.label}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}

// Predefined status options for ingestion phase
export const INGESTION_STATUS_OPTIONS: StatusOption[] = [
    { value: "all", label: "All Statuses" },
    { value: "pending", label: "Pending" },
    { value: "fetched", label: "Fetched" },
    { value: "ingesting", label: "Ingesting" },
    { value: "ingested", label: "Ingested" },
    { value: "failed", label: "Failed" },
    { value: "missing_resource", label: "Missing Resource" },
];

// Predefined status options for dataset import (no fetched state)
export const DATASET_INGESTION_STATUS_OPTIONS: StatusOption[] = [
    { value: "all", label: "All Statuses" },
    { value: "pending", label: "Pending" },
    { value: "ingesting", label: "Ingesting" },
    { value: "ingested", label: "Ingested" },
    { value: "failed", label: "Failed" },
    { value: "missing_resource", label: "Missing Resource" },
];

// Predefined status options for processing/extraction phase  
export const PROCESSING_STATUS_OPTIONS: StatusOption[] = [
    { value: "all", label: "All Statuses" },
    { value: "pending", label: "Pending" },
    { value: "in_progress", label: "In Progress" },
    { value: "completed", label: "Completed" },
    { value: "partial", label: "Partial" },
    { value: "failed", label: "Failed" },
];

// Predefined status options for integration scans (Trivy, SonarQube)
export const SCAN_STATUS_OPTIONS: StatusOption[] = [
    { value: "all", label: "All Statuses" },
    { value: "pending", label: "Pending" },
    { value: "scanning", label: "Scanning" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" },
];
