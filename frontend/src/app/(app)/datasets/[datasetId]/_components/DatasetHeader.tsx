"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, FileSpreadsheet, RefreshCw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DatasetRecord } from "@/types";

interface DatasetHeaderProps {
    dataset: DatasetRecord;
    onRefresh: () => void;
    onDelete: () => void;
}

function formatDate(value?: string | null) {
    if (!value) return "—";
    try {
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(value));
    } catch {
        return value;
    }
}

export function DatasetHeader({ dataset, onRefresh, onDelete }: DatasetHeaderProps) {
    const router = useRouter();

    const hasMapping = Boolean(
        dataset.mapped_fields?.build_id && dataset.mapped_fields?.repo_name
    );
    const isValidated = dataset.validation_status === "completed";

    const getStatusBadge = () => {
        if (!hasMapping) {
            return <Badge variant="secondary">Pending Mapping</Badge>;
        }
        if (!isValidated) {
            return (
                <Badge variant="outline" className="border-amber-500 text-amber-600">
                    Pending Validation
                </Badge>
            );
        }
        return (
            <Badge variant="outline" className="border-green-500 text-green-600">
                Validated
            </Badge>
        );
    };

    return (
        <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
                <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => router.push("/datasets")}
                >
                    <ArrowLeft className="h-4 w-4" />
                </Button>
                <div>
                    <div className="flex items-center gap-3">
                        <FileSpreadsheet className="h-6 w-6 text-muted-foreground" />
                        <h1 className="text-2xl font-bold">{dataset.name}</h1>
                        {getStatusBadge()}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {dataset.file_name} • {dataset.rows.toLocaleString()} rows •
                        Created {formatDate(dataset.created_at)}
                    </p>
                </div>
            </div>
            <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={onRefresh}>
                    <RefreshCw className="mr-2 h-4 w-4" /> Refresh
                </Button>
                <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-900/20"
                    onClick={onDelete}
                >
                    <Trash2 className="mr-2 h-4 w-4" /> Delete
                </Button>
            </div>
        </div>
    );
}

