"use client";

import { useState, useRef, useCallback } from "react";
import Papa from "papaparse";
import type { CSVPreview, MappingKey } from "../types";

interface UseStep1UploadReturn {
    file: File | null;
    preview: CSVPreview | null;
    uploading: boolean;
    error: string | null;
    name: string;
    description: string;
    mappings: Record<MappingKey, string>;
    isMappingValid: boolean;
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    setName: (name: string) => void;
    setDescription: (description: string) => void;
    setError: (error: string | null) => void;
    handleFileSelect: (event: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
    handleMappingChange: (field: MappingKey, value: string) => void;
    handleClearFile: () => void;
    resetStep1: () => void;
    loadFromExistingDataset: (dataset: {
        name?: string;
        description?: string | null;
        columns?: string[];
        rows?: number;
        file_name?: string;
        size_bytes?: number;
        preview?: Record<string, unknown>[];
        mapped_fields?: { build_id?: string | null; repo_name?: string | null };
    }) => void;
}

export function useStep1Upload(): UseStep1UploadReturn {
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<CSVPreview | null>(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [mappings, setMappings] = useState<Record<MappingKey, string>>({
        build_id: "",
        repo_name: "",
    });

    const fileInputRef = useRef<HTMLInputElement>(null);

    const isMappingValid = Boolean(mappings.build_id && mappings.repo_name);

    const resetStep1 = useCallback(() => {
        setFile(null);
        setPreview(null);
        setUploading(false);
        setError(null);
        setName("");
        setDescription("");
        setMappings({ build_id: "", repo_name: "" });
    }, []);

    const parseCSVPreview = useCallback(async (file: File): Promise<CSVPreview> => {
        return new Promise((resolve, reject) => {
            const previewSlice = file.slice(0, 100000);
            const reader = new FileReader();

            reader.onload = (e) => {
                const csvText = e.target?.result as string;

                Papa.parse(csvText, {
                    header: true,
                    skipEmptyLines: true,
                    preview: 5,
                    complete: (results) => {
                        if (results.errors.length > 0 && results.data.length === 0) {
                            reject(new Error(results.errors[0].message));
                            return;
                        }

                        const columns = results.meta.fields || [];
                        const rows = results.data as Record<string, string>[];

                        const avgRowSize = csvText.length / Math.max(rows.length + 1, 1);
                        const estimatedTotalRows = Math.floor(file.size / avgRowSize) - 1;

                        resolve({
                            columns,
                            rows,
                            totalRows: estimatedTotalRows > 0 ? estimatedTotalRows : rows.length,
                            fileName: file.name,
                            fileSize: file.size,
                        });
                    },
                    error: (error: Error) => {
                        reject(new Error(error.message));
                    },
                });
            };

            reader.onerror = () => reject(new Error("Failed to read file"));
            reader.readAsText(previewSlice);
        });
    }, []);

    const guessMapping = useCallback((columns: string[]) => {
        const lowered = columns.map((c) => c.toLowerCase());

        const findMatch = (options: string[]): string => {
            for (const opt of options) {
                const idx = lowered.findIndex((c) => c.includes(opt) || c === opt);
                if (idx !== -1) return columns[idx];
            }
            return "";
        };

        return {
            build_id: findMatch(["build_id", "build id", "id", "workflow_run_id", "run_id", "tr_build_id"]),
            repo_name: findMatch(["repo", "repository", "repo_name", "full_name", "project", "gh_project_name"]),
        };
    }, []);

    const handleFileSelect = useCallback(
        async (event: React.ChangeEvent<HTMLInputElement>) => {
            const selectedFile = event.target.files?.[0];
            if (!selectedFile) return;

            setError(null);
            setUploading(true);

            try {
                const csvPreview = await parseCSVPreview(selectedFile);
                setFile(selectedFile);
                setPreview(csvPreview);
                setName(selectedFile.name.replace(/\.csv$/i, ""));

                const guessed = guessMapping(csvPreview.columns);
                setMappings(guessed);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to parse CSV");
            } finally {
                setUploading(false);
                if (event.target) event.target.value = "";
            }
        },
        [parseCSVPreview, guessMapping]
    );

    const handleMappingChange = useCallback((field: MappingKey, value: string) => {
        setMappings((prev) => ({ ...prev, [field]: value }));
    }, []);

    const handleClearFile = useCallback(() => {
        setFile(null);
        setPreview(null);
    }, []);

    const loadFromExistingDataset = useCallback(
        (dataset: {
            name?: string;
            description?: string | null;
            columns?: string[];
            rows?: number;
            file_name?: string;
            size_bytes?: number;
            preview?: Record<string, unknown>[];
            mapped_fields?: { build_id?: string | null; repo_name?: string | null };
        }) => {
            setName(dataset.name || "");
            setDescription(dataset.description || "");

            if (dataset.mapped_fields) {
                setMappings({
                    build_id: dataset.mapped_fields.build_id || "",
                    repo_name: dataset.mapped_fields.repo_name || "",
                });
            }

            if (dataset.columns?.length) {
                const previewRows = (dataset.preview || []).map((row) => {
                    const converted: Record<string, string> = {};
                    Object.entries(row).forEach(([key, value]) => {
                        converted[key] = String(value ?? "");
                    });
                    return converted;
                });
                setPreview({
                    columns: dataset.columns,
                    rows: previewRows,
                    totalRows: dataset.rows || 0,
                    fileName: dataset.file_name || "dataset.csv",
                    fileSize: dataset.size_bytes || 0,
                });
            }
        },
        []
    );

    return {
        file,
        preview,
        uploading,
        error,
        name,
        description,
        mappings,
        isMappingValid,
        fileInputRef,
        setName,
        setDescription,
        setError,
        handleFileSelect,
        handleMappingChange,
        handleClearFile,
        resetStep1,
        loadFromExistingDataset,
    };
}
