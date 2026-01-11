"use client";

import { FileSpreadsheet, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { StepUploadProps } from "./types";

interface UploadPreviewProps extends Pick<StepUploadProps, "preview" | "isSourceCreated" | "onClearFile"> { }

export function UploadPreview({
    preview,
    isSourceCreated,
    onClearFile,
}: UploadPreviewProps) {
    if (!preview) return null;

    return (
        <div className="space-y-4 h-full flex flex-col">
            <div className="flex items-center gap-3 rounded-lg bg-slate-100 px-4 py-3 dark:bg-slate-800">
                <FileSpreadsheet className="h-5 w-5 text-emerald-500" />
                <div className="flex-1">
                    <p className="font-medium">{preview.fileName}</p>
                    <p className="text-xs text-muted-foreground">
                        {preview.totalRows.toLocaleString()} rows • {preview.columns.length} columns
                    </p>
                </div>
                {!isSourceCreated && (
                    <Button variant="ghost" size="sm" onClick={onClearFile}>
                        <X className="h-4 w-4" />
                    </Button>
                )}
            </div>

            <div className="space-y-2 flex-1 flex flex-col min-h-0">
                <div className="flex items-center justify-between">
                    <Label className="text-base font-semibold">Preview Data</Label>
                    <span className="text-xs text-muted-foreground">
                        {preview.columns.length} columns
                    </span>
                </div>
                <div className="rounded-lg border flex-1 overflow-hidden bg-background">
                    <div className="overflow-auto h-full w-full">
                        <table className="min-w-full text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-800 sticky top-0 z-10">
                                <tr>
                                    {preview.columns.map((col) => (
                                        <th key={col} className="whitespace-nowrap px-4 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800">
                                            {col}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {preview.rows.map((row, idx) => (
                                    <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/50">
                                        {preview.columns.map((col) => (
                                            <td key={col} className="whitespace-nowrap px-4 py-2 text-xs text-muted-foreground">
                                                {String(row[col] || "—").slice(0, 100)}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
}
