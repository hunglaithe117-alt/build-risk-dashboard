"use client";

import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TablePaginationProps {
    currentPage: number;
    totalPages: number;
    totalItems: number;
    pageSize: number;
    onPageChange: (page: number) => void;
    isLoading?: boolean;
    className?: string;
}

export function TablePagination({
    currentPage,
    totalPages,
    totalItems,
    pageSize,
    onPageChange,
    isLoading = false,
    className,
}: TablePaginationProps) {
    const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const endItem = Math.min(currentPage * pageSize, totalItems);

    const handlePrevious = () => {
        if (currentPage > 1) {
            onPageChange(currentPage - 1);
        }
    };

    const handleNext = () => {
        if (currentPage < totalPages) {
            onPageChange(currentPage + 1);
        }
    };

    return (
        <div className={cn(
            "flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground",
            className
        )}>
            <div>
                {totalItems > 0
                    ? `Showing ${startItem}-${endItem} of ${totalItems}`
                    : "No items"}
            </div>
            <div className="flex items-center gap-2">
                {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                <Button
                    size="sm"
                    variant="outline"
                    onClick={handlePrevious}
                    disabled={currentPage === 1 || isLoading}
                >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                </Button>
                <span className="text-xs px-2">
                    Page {currentPage} of {Math.max(totalPages, 1)}
                </span>
                <Button
                    size="sm"
                    variant="outline"
                    onClick={handleNext}
                    disabled={currentPage >= totalPages || isLoading}
                >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
            </div>
        </div>
    );
}
