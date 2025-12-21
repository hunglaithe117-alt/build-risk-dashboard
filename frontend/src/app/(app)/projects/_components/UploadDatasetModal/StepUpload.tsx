import {
    AlertCircle,
    CheckCircle2,
    FileSpreadsheet,
    Loader2,
    Upload,
    X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import type { BuildValidationFilters } from "@/types";

import { ColumnSelector } from "./ColumnSelector";
import type { StepUploadProps, MappingKey } from "./types";

export function StepUpload({
    preview,
    uploading,
    name,
    description,
    ciProvider,
    ciProviderMode,
    ciProviderColumn,
    ciProviders,
    buildFilters,
    mappings,
    isMappingValid,
    isDatasetCreated,
    fileInputRef,
    onFileSelect,
    onNameChange,
    onDescriptionChange,
    onCiProviderChange,
    onCiProviderModeChange,
    onCiProviderColumnChange,
    onBuildFiltersChange,
    onMappingChange,
    onClearFile,
}: StepUploadProps) {
    if (!preview) {
        return (
            <div className="flex justify-center">
                <div className="w-full max-w-lg">
                    <input
                        ref={fileInputRef as React.RefObject<HTMLInputElement>}
                        type="file"
                        accept=".csv"
                        className="hidden"
                        onChange={onFileSelect}
                    />
                    <div
                        className="flex cursor-pointer flex-col items-center justify-center gap-6 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/50 px-8 py-16 transition hover:border-blue-400 hover:bg-blue-50/50 dark:border-slate-700 dark:bg-slate-900/50"
                        onClick={() => fileInputRef.current?.click()}
                    >
                        {uploading ? (
                            <>
                                <Loader2 className="h-16 w-16 animate-spin text-blue-500" />
                                <p className="text-muted-foreground">Parsing CSV...</p>
                            </>
                        ) : (
                            <>
                                <div className="rounded-full bg-blue-100 p-4 dark:bg-blue-900/30">
                                    <Upload className="h-12 w-12 text-blue-500" />
                                </div>
                                <div className="text-center">
                                    <p className="text-xl font-semibold">Drop your CSV file here</p>
                                    <p className="mt-1 text-muted-foreground">or click to browse from your computer</p>
                                </div>
                                <Badge variant="outline" className="text-xs">
                                    Supports .csv files
                                </Badge>
                            </>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <>
            <div className="flex items-center gap-3 rounded-lg bg-slate-100 px-4 py-3 dark:bg-slate-800">
                <FileSpreadsheet className="h-5 w-5 text-emerald-500" />
                <div className="flex-1">
                    <p className="font-medium">{preview.fileName}</p>
                    <p className="text-xs text-muted-foreground">
                        {preview.totalRows.toLocaleString()} rows • {preview.columns.length} columns
                    </p>
                </div>
                {!isDatasetCreated && (
                    <Button variant="ghost" size="sm" onClick={onClearFile}>
                        <X className="h-4 w-4" />
                    </Button>
                )}
            </div>

            {/* Dataset Info */}
            <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                    <Label>Dataset Name</Label>
                    <Input value={name} onChange={(e) => onNameChange(e.target.value)} placeholder="My Dataset" />
                </div>
                <div className="space-y-2">
                    <Label>Description (optional)</Label>
                    <Input value={description} onChange={(e) => onDescriptionChange(e.target.value)} placeholder="Description..." />
                </div>
            </div>

            {/* Column Mapping */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <Label className="text-base font-semibold">Column Mapping</Label>
                    {isMappingValid ? (
                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                            <CheckCircle2 className="h-4 w-4" /> Ready
                        </span>
                    ) : (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                            <AlertCircle className="h-4 w-4" /> Map required fields
                        </span>
                    )}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase text-muted-foreground">
                            Build ID <span className="text-red-500">*</span>
                        </Label>
                        <ColumnSelector
                            value={mappings.build_id}
                            columns={preview.columns}
                            onChange={(v) => onMappingChange("build_id" as MappingKey, v)}
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs uppercase text-muted-foreground">
                            Repo Name <span className="text-red-500">*</span>
                        </Label>
                        <ColumnSelector
                            value={mappings.repo_name}
                            columns={preview.columns}
                            onChange={(v) => onMappingChange("repo_name" as MappingKey, v)}
                        />
                    </div>
                </div>
            </div>

            {/* CI Provider Selection */}
            <div className="space-y-3">
                <Label className="text-base font-semibold">CI Provider</Label>

                {/* Mode Toggle */}
                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant={ciProviderMode === "single" ? "default" : "outline"}
                        size="sm"
                        onClick={() => onCiProviderModeChange("single")}
                    >
                        Single Provider
                    </Button>
                    <Button
                        type="button"
                        variant={ciProviderMode === "column" ? "default" : "outline"}
                        size="sm"
                        onClick={() => onCiProviderModeChange("column")}
                    >
                        Map from Column
                    </Button>
                </div>

                {/* Mode-specific UI */}
                {ciProviderMode === "single" ? (
                    <div className="max-w-xs">
                        <Select
                            value={ciProvider}
                            onValueChange={onCiProviderChange}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Select CI Provider" />
                            </SelectTrigger>
                            <SelectContent>
                                {ciProviders.map((provider) => (
                                    <SelectItem key={provider.value} value={provider.value}>
                                        {provider.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="mt-1.5 text-xs text-muted-foreground">
                            All builds in this dataset use the selected CI provider
                        </p>
                    </div>
                ) : (
                    <div className="max-w-xs space-y-1.5">
                        <Label className="text-xs uppercase text-muted-foreground">
                            CI Provider Column
                        </Label>
                        <ColumnSelector
                            value={ciProviderColumn}
                            columns={preview.columns}
                            onChange={onCiProviderColumnChange}
                            placeholder="Select column..."
                        />
                        <p className="mt-1.5 text-xs text-muted-foreground">
                            Each row specifies its CI provider (github_actions, travis_ci, etc.)
                        </p>
                    </div>
                )}
            </div>

            {/* Build Filters */}
            <div className="space-y-4 rounded-lg border bg-slate-50/50 p-4 dark:bg-slate-800/50">
                <div>
                    <Label className="text-base font-semibold">Build Filters</Label>
                    <p className="text-xs text-muted-foreground">
                        Configure which builds to include during validation
                    </p>
                </div>

                {/* Boolean filters */}
                <div className="flex flex-wrap gap-3">
                    <label className="flex cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-2 transition hover:border-blue-300 dark:bg-slate-900">
                        <input
                            type="checkbox"
                            checked={buildFilters.only_completed}
                            onChange={(e) =>
                                onBuildFiltersChange({
                                    ...buildFilters,
                                    only_completed: e.target.checked,
                                })
                            }
                            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="text-sm">Only completed builds</span>
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-2 transition hover:border-blue-300 dark:bg-slate-900">
                        <input
                            type="checkbox"
                            checked={buildFilters.exclude_bots}
                            onChange={(e) =>
                                onBuildFiltersChange({
                                    ...buildFilters,
                                    exclude_bots: e.target.checked,
                                })
                            }
                            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="text-sm">Exclude bot commits</span>
                    </label>
                </div>

                <div className="space-y-2">
                    <Label className="text-sm font-medium">Allowed Build Conclusions</Label>
                    <p className="text-xs text-muted-foreground">
                        Select which build results to include (click to toggle)
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {[
                            { value: "success", label: "✓ Success", color: "bg-emerald-100 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-400" },
                            { value: "failure", label: "✗ Failure", color: "bg-red-100 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-400" },
                            { value: "cancelled", label: "◯ Cancelled", color: "bg-slate-100 border-slate-300 text-slate-600 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-400" },
                            { value: "skipped", label: "⊘ Skipped", color: "bg-amber-100 border-amber-300 text-amber-700 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-400" },
                            { value: "timed_out", label: "⏱ Timed Out", color: "bg-orange-100 border-orange-300 text-orange-700 dark:bg-orange-900/30 dark:border-orange-700 dark:text-orange-400" },
                            { value: "neutral", label: "◎ Neutral", color: "bg-blue-100 border-blue-300 text-blue-700 dark:bg-blue-900/30 dark:border-blue-700 dark:text-blue-400" },
                        ].map((option) => {
                            const isSelected = buildFilters.allowed_conclusions.includes(option.value);
                            return (
                                <button
                                    key={option.value}
                                    type="button"
                                    onClick={() => {
                                        const newConclusions = isSelected
                                            ? buildFilters.allowed_conclusions.filter((c) => c !== option.value)
                                            : [...buildFilters.allowed_conclusions, option.value];
                                        onBuildFiltersChange({
                                            ...buildFilters,
                                            allowed_conclusions: newConclusions,
                                        });
                                    }}
                                    className={`rounded-full border px-3 py-1.5 text-sm font-medium transition ${isSelected
                                        ? option.color
                                        : "border-slate-200 bg-white text-slate-400 opacity-50 dark:border-slate-700 dark:bg-slate-900"
                                        }`}
                                >
                                    {option.label}
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Preview */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <Label className="text-base font-semibold">Preview</Label>
                    <span className="text-xs text-muted-foreground">
                        {preview.columns.length} columns
                    </span>
                </div>
                <div className="rounded-lg border">
                    <div className="overflow-x-auto max-h-64">
                        <table className="min-w-full text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-800 sticky top-0">
                                <tr>
                                    {preview.columns.map((col) => (
                                        <th key={col} className="whitespace-nowrap px-4 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300">
                                            {col}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {preview.rows.slice(0, 5).map((row, idx) => (
                                    <tr key={idx}>
                                        {preview.columns.map((col) => (
                                            <td key={col} className="whitespace-nowrap px-4 py-2 text-xs text-muted-foreground">
                                                {String(row[col] || "—").slice(0, 40)}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </>
    );
}
