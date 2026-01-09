"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, FileSpreadsheet, RefreshCw, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/utils";
import type { DatasetRecord } from "@/types";

interface DatasetHeaderProps {
    dataset: DatasetRecord;
    onRefresh: () => void;
    onDelete: () => void;
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
                    onClick={() => router.push("/projects")}
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
                        Created {formatDateTime(dataset.created_at)}
                    </p>
                </div>
            </div>
        </div>
    );
}

