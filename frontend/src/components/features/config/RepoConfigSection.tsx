"use client";

import { useState, useCallback, useMemo, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    ChevronLeft,
    ChevronRight,
    Search,
    Folder,
    Check,
    ArrowRight,
    Settings,
    Loader2,
} from "lucide-react";
import { ScanConfigOverrideModal, RepoScanConfig } from "./ScanConfigOverrideModal";
import { reposApi } from "@/lib/api";

interface RepoInfo {
    id: string;
    full_name: string;
    validation_status: string;
}

// Dynamic config: field name -> array of selected values
type RepoConfig = Record<string, string[]>;

interface ConfigFieldSpec {
    name: string;
    type: string;
    scope: string;
    required: boolean;
    description: string;
    default: unknown;
    options: unknown; // Flexible: string[] (flat) or Record<string, string[]> (grouped)
}

interface RepoConfigSectionProps {
    repos: RepoInfo[];
    repoFields: ConfigFieldSpec[];
    repoConfigs: Record<string, RepoConfig>;
    onChange: (configs: Record<string, RepoConfig>) => void;
    disabled?: boolean;
    isLoading?: boolean;
    // Scan config props
    datasetId?: string;
    repoScanConfigs?: Record<string, RepoScanConfig>;
    onScanConfigChange?: (repoId: string, config: RepoScanConfig) => void;
    showScanConfig?: boolean;
}

const PAGE_SIZE = 10;

/** Format field name for display (snake_case -> Title Case) */
const formatFieldName = (name: string) =>
    name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

export function RepoConfigSection({
    repos,
    repoFields,
    repoConfigs,
    onChange,
    disabled = false,
    isLoading = false,
    datasetId,
    repoScanConfigs = {},
    onScanConfigChange,
    showScanConfig = false,
}: RepoConfigSectionProps) {
    const [page, setPage] = useState(0);
    const [searchQuery, setSearchQuery] = useState("");
    const [filterMode, setFilterMode] = useState<"all" | "overrides" | "default">("all");

    // Scan config modal state
    const [scanConfigRepo, setScanConfigRepo] = useState<{ id: string; name: string } | null>(null);
    const [savingScanConfig, setSavingScanConfig] = useState(false);

    // Apply to all state - dynamic based on repoFields
    const [applyAllValues, setApplyAllValues] = useState<RepoConfig>({});

    // Edit dialog state
    const [editingRepo, setEditingRepo] = useState<string | null>(null);
    const [editValues, setEditValues] = useState<RepoConfig>({});

    // Language detection state
    const [repoLanguages, setRepoLanguages] = useState<Record<string, string[]>>({});
    const [languageLoading, setLanguageLoading] = useState<Record<string, boolean>>({});

    // Detect languages for repos when they change
    useEffect(() => {
        if (repos.length === 0) return;

        const detectLanguagesForRepos = async () => {
            for (const repo of repos) {
                // Skip if already loaded or loading
                if (repoLanguages[repo.id] !== undefined || languageLoading[repo.id]) {
                    continue;
                }

                setLanguageLoading(prev => ({ ...prev, [repo.id]: true }));
                try {
                    const result = await reposApi.detectLanguages(repo.full_name);
                    setRepoLanguages(prev => ({
                        ...prev,
                        [repo.id]: result.languages.map(l => l.toLowerCase()),
                    }));
                } catch (err) {
                    console.error(`Failed to detect languages for ${repo.full_name}:`, err);
                    // Set empty array to prevent re-fetching
                    setRepoLanguages(prev => ({ ...prev, [repo.id]: [] }));
                } finally {
                    setLanguageLoading(prev => ({ ...prev, [repo.id]: false }));
                }
            }
        };

        detectLanguagesForRepos();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [repos]);

    // Get union of all detected languages (for "Apply to All" section)
    const allDetectedLanguages = useMemo(() => {
        const languages = new Set<string>();
        Object.values(repoLanguages).forEach(langs => {
            langs.forEach(l => languages.add(l));
        });
        return Array.from(languages);
    }, [repoLanguages]);

    // Check if any repo is still loading languages
    const isLoadingLanguages = useMemo(() =>
        Object.values(languageLoading).some(Boolean),
        [languageLoading]
    );

    // Initialize when repoFields change
    useEffect(() => {
        const initialConfig: RepoConfig = {};
        repoFields.forEach(field => {
            if (field.type === "list") {
                initialConfig[field.name] = [];
            }
        });
        setApplyAllValues(prev => {
            // Preserve existing values
            const merged = { ...initialConfig };
            repoFields.forEach(field => {
                if (prev[field.name]) {
                    merged[field.name] = prev[field.name];
                }
            });
            return merged;
        });
    }, [repoFields]);

    // When repos is empty, sync applyAllValues as default config
    useEffect(() => {
        const hasAnyValues = Object.values(applyAllValues).some(arr => arr.length > 0);
        if (repos.length === 0 && hasAnyValues) {
            onChange({ __default__: applyAllValues });
        }
    }, [repos.length, applyAllValues, onChange]);

    // Only fields with type "list" and valid options (array or non-empty object)
    const listFields = useMemo(() =>
        repoFields.filter(f => {
            if (f.type !== "list" || !f.options) return false;
            // Check for array with items OR object with keys
            if (Array.isArray(f.options)) return f.options.length > 0;
            if (typeof f.options === "object") return Object.keys(f.options).length > 0;
            return false;
        }),
        [repoFields]
    );

    // Check if repo has override
    const hasOverride = useCallback((repoId: string) => {
        const config = repoConfigs[repoId];
        if (!config) return false;
        return Object.values(config).some(arr => arr.length > 0);
    }, [repoConfigs]);

    // Filter repos
    const filteredRepos = useMemo(() => {
        let result = repos;
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            result = result.filter(r => r.full_name.toLowerCase().includes(q));
        }
        if (filterMode === "overrides") {
            result = result.filter(r => hasOverride(r.id));
        } else if (filterMode === "default") {
            result = result.filter(r => !hasOverride(r.id));
        }
        return result;
    }, [repos, searchQuery, filterMode, hasOverride]);

    // Paginated repos
    const paginatedRepos = useMemo(() => {
        const start = page * PAGE_SIZE;
        return filteredRepos.slice(start, start + PAGE_SIZE);
    }, [filteredRepos, page]);

    const totalPages = Math.ceil(filteredRepos.length / PAGE_SIZE);

    // Apply to all repos for a specific field
    const handleApplyToAll = (fieldName: string) => {
        if (disabled) return;
        const newConfigs = { ...repoConfigs };
        repos.forEach(repo => {
            if (!newConfigs[repo.id]) {
                newConfigs[repo.id] = {};
            }
            newConfigs[repo.id] = {
                ...newConfigs[repo.id],
                [fieldName]: [...(applyAllValues[fieldName] || [])],
            };
        });
        onChange(newConfigs);
    };

    // Toggle option in apply-all
    const toggleApplyAllOption = (fieldName: string, option: string) => {
        setApplyAllValues(prev => {
            const current = prev[fieldName] || [];
            const newValues = current.includes(option)
                ? current.filter(v => v !== option)
                : [...current, option];
            return { ...prev, [fieldName]: newValues };
        });
    };

    // Open edit dialog
    const openEditDialog = (repoId: string) => {
        const existingConfig = repoConfigs[repoId] || {};
        // Initialize with empty arrays for all fields
        const config: RepoConfig = {};
        repoFields.forEach(f => {
            config[f.name] = existingConfig[f.name] || [];
        });
        setEditValues(config);
        setEditingRepo(repoId);
    };

    // Save edit
    const saveEdit = () => {
        if (!editingRepo) return;
        onChange({
            ...repoConfigs,
            [editingRepo]: editValues,
        });
        setEditingRepo(null);
    };

    // Toggle option in edit dialog
    const toggleEditOption = (fieldName: string, option: string) => {
        setEditValues(prev => {
            const current = prev[fieldName] || [];
            const newValues = current.includes(option)
                ? current.filter(v => v !== option)
                : [...current, option];
            return { ...prev, [fieldName]: newValues };
        });
    };

    // Get display value for a repo's config field
    const getDisplayValue = (repoId: string, fieldName: string) => {
        const config = repoConfigs[repoId];
        if (!config || !config[fieldName] || config[fieldName].length === 0) return "—";
        return config[fieldName].join(", ");
    };

    // Filter source_languages options based on detected languages
    const filterSourceLanguages = useCallback((options: string[], languages: string[]): string[] => {
        if (languages.length === 0) return options; // Show all if no languages detected
        const langSet = new Set(languages.map(l => l.toLowerCase()));
        return options.filter(opt => langSet.has(opt.toLowerCase()));
    }, []);

    // Filter test_frameworks options based on detected languages
    const filterTestFrameworks = useCallback((
        options: Record<string, string[]>,
        languages: string[]
    ): Record<string, string[]> => {
        if (languages.length === 0) return options; // Show all if no languages detected
        const langSet = new Set(languages.map(l => l.toLowerCase()));
        const filtered: Record<string, string[]> = {};
        for (const [lang, frameworks] of Object.entries(options)) {
            if (langSet.has(lang.toLowerCase())) {
                filtered[lang] = frameworks;
            }
        }
        return filtered;
    }, []);

    // Get filtered options for a field based on languages
    const getFilteredOptions = useCallback((field: ConfigFieldSpec, languages: string[]) => {
        if (field.name === "source_languages" && Array.isArray(field.options)) {
            return filterSourceLanguages(field.options as string[], languages);
        }
        if (field.name === "test_frameworks" && typeof field.options === "object" && !Array.isArray(field.options)) {
            return filterTestFrameworks(field.options as Record<string, string[]>, languages);
        }
        return field.options;
    }, [filterSourceLanguages, filterTestFrameworks]);

    // If no list fields with options, don't render
    if (listFields.length === 0) {
        return null;
    }

    // Show empty state when no repos but fields exist
    if (repos.length === 0 && !isLoading) {
        return (
            <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <Folder className="h-4 w-4" />
                    Repository Settings
                </div>
                <div className="border rounded-lg p-4 bg-muted/30 space-y-3">
                    <div className="text-sm text-muted-foreground">
                        <p className="mb-2">
                            ⚠️ <strong>Dataset validation required</strong> to configure per-repo settings.
                        </p>
                        <p className="text-xs">
                            Please validate the dataset first to see repositories, or set default values below.
                        </p>
                    </div>

                    <div className="pt-3 border-t space-y-4">
                        <div className="text-sm font-medium">Set Default Values for All Repositories</div>

                        {listFields.map(field => {
                            // All options are now flat arrays from API

                            return (
                                <div key={field.name} className="border rounded-lg p-3 bg-background">
                                    <div className="text-sm font-medium mb-2">
                                        {formatFieldName(field.name)}
                                    </div>

                                    {field.name === "test_frameworks" ? (
                                        <div className="space-y-2">
                                            {Object.entries(field.options as Record<string, string[]>).map(([group, options]) => (
                                                <div key={group} className="flex flex-wrap items-center gap-2">
                                                    <span className="text-xs text-muted-foreground w-20 capitalize font-medium">
                                                        {group}:
                                                    </span>
                                                    <div className="flex flex-wrap gap-1 flex-1">
                                                        {options.map(option => {
                                                            const isSelected = (applyAllValues[field.name] || []).includes(option);
                                                            return (
                                                                <Badge
                                                                    key={option}
                                                                    variant={isSelected ? "default" : "outline"}
                                                                    className={`cursor-pointer transition-colors text-xs ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                                                        }`}
                                                                    onClick={() => !disabled && toggleApplyAllOption(field.name, option)}
                                                                >
                                                                    {option}
                                                                </Badge>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="flex flex-wrap gap-1">
                                            {(Array.isArray(field.options) ? field.options : []).map((option: string) => {
                                                const isSelected = (applyAllValues[field.name] || []).includes(option);
                                                return (
                                                    <Badge
                                                        key={option}
                                                        variant={isSelected ? "default" : "outline"}
                                                        className={`cursor-pointer transition-colors ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                                            }`}
                                                        onClick={() => !disabled && toggleApplyAllOption(field.name, option)}
                                                    >
                                                        {option}
                                                    </Badge>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Folder className="h-4 w-4" />
                Repository Settings ({repos.length} repos)
            </div>

            {/* Apply to All Section - Each field in separate card */}
            <div className="space-y-3">
                <div className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                    📋 Apply to All Repositories
                    {isLoadingLanguages && (
                        <Loader2 className="h-3 w-3 animate-spin" />
                    )}
                </div>

                {listFields.map(field => {
                    // Get filtered options based on all detected languages
                    const filteredOptions = getFilteredOptions(field, allDetectedLanguages);

                    return (
                        <div key={field.name} className="border rounded-lg p-4 bg-muted/30">
                            <div className="flex items-center justify-between mb-3">
                                <span className="text-sm font-medium">
                                    {formatFieldName(field.name)}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={disabled || !(applyAllValues[field.name]?.length)}
                                    onClick={() => handleApplyToAll(field.name)}
                                    className="gap-1"
                                >
                                    Apply to All <ArrowRight className="h-3 w-3" />
                                </Button>
                            </div>

                            {field.name === "test_frameworks" ? (
                                // Render grouped by language - filtered
                                <div className="space-y-2">
                                    {Object.entries(filteredOptions as Record<string, string[]>).map(([group, options]) => (
                                        <div key={group} className="flex flex-wrap items-center gap-2">
                                            <span className="text-xs text-muted-foreground w-24 capitalize font-medium">
                                                {group}:
                                            </span>
                                            <div className="flex flex-wrap gap-1 flex-1">
                                                {options.map(option => {
                                                    const isSelected = (applyAllValues[field.name] || []).includes(option);
                                                    return (
                                                        <Badge
                                                            key={option}
                                                            variant={isSelected ? "default" : "outline"}
                                                            className={`cursor-pointer transition-colors text-xs ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                                                }`}
                                                            onClick={() => !disabled && toggleApplyAllOption(field.name, option)}
                                                        >
                                                            {option}
                                                        </Badge>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                    {Object.keys(filteredOptions as Record<string, string[]>).length === 0 && (
                                        <div className="text-xs text-muted-foreground italic">
                                            No matching frameworks for detected languages
                                        </div>
                                    )}
                                </div>
                            ) : field.name === "source_languages" ? (
                                // Filtered source languages
                                <div className="flex flex-wrap gap-1">
                                    {(filteredOptions as string[]).map((option: string) => {
                                        const isSelected = (applyAllValues[field.name] || []).includes(option);
                                        return (
                                            <Badge
                                                key={option}
                                                variant={isSelected ? "default" : "outline"}
                                                className={`cursor-pointer transition-colors ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                                    }`}
                                                onClick={() => !disabled && toggleApplyAllOption(field.name, option)}
                                            >
                                                {option}
                                            </Badge>
                                        );
                                    })}
                                    {(filteredOptions as string[]).length === 0 && (
                                        <div className="text-xs text-muted-foreground italic">
                                            No supported languages detected
                                        </div>
                                    )}
                                </div>
                            ) : (
                                // Flat list fallback for other fields
                                <div className="flex flex-wrap gap-1">
                                    {(Array.isArray(field.options) ? field.options : []).slice(0, 15).map((option: string) => {
                                        const isSelected = (applyAllValues[field.name] || []).includes(option);
                                        return (
                                            <Badge
                                                key={option}
                                                variant={isSelected ? "default" : "outline"}
                                                className={`cursor-pointer transition-colors ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                                    }`}
                                                onClick={() => !disabled && toggleApplyAllOption(field.name, option)}
                                            >
                                                {option}
                                            </Badge>
                                        );
                                    })}
                                    {(Array.isArray(field.options) && field.options.length > 15) && (
                                        <Badge variant="secondary">+{field.options.length - 15} more</Badge>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Search and Filter */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search repos..."
                        value={searchQuery}
                        onChange={(e) => {
                            setSearchQuery(e.target.value);
                            setPage(0);
                        }}
                        className="pl-9"
                    />
                </div>
                <Select value={filterMode} onValueChange={(v) => { setFilterMode(v as typeof filterMode); setPage(0); }}>
                    <SelectTrigger className="w-40">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">All ({repos.length})</SelectItem>
                        <SelectItem value="overrides">With Overrides</SelectItem>
                        <SelectItem value="default">Using Default</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Table */}
            {isLoading ? (
                <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                </div>
            ) : (
                <div className="border rounded-lg overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow className="bg-muted/50">
                                <TableHead className="w-[40%]">Repository</TableHead>
                                {listFields.map(field => (
                                    <TableHead key={field.name}>
                                        {formatFieldName(field.name)}
                                    </TableHead>
                                ))}
                                {showScanConfig && (
                                    <TableHead className="w-[80px]">Scan Config</TableHead>
                                )}
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {paginatedRepos.map(repo => (
                                <TableRow
                                    key={repo.id}
                                    className={`cursor-pointer hover:bg-muted/50 ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
                                    onClick={() => !disabled && openEditDialog(repo.id)}
                                >
                                    <TableCell className="font-medium">
                                        <div className="flex items-center gap-2">
                                            <span>{repo.full_name}</span>
                                            {hasOverride(repo.id) && (
                                                <span className="text-primary" title="Has custom settings">●</span>
                                            )}
                                        </div>
                                    </TableCell>
                                    {listFields.map(field => (
                                        <TableCell key={field.name} className="text-sm text-muted-foreground">
                                            {getDisplayValue(repo.id, field.name)}
                                        </TableCell>
                                    ))}
                                    {/* Scan Config Button */}
                                    {showScanConfig && (
                                        <TableCell>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setScanConfigRepo({ id: repo.id, name: repo.full_name });
                                                }}
                                                className="gap-1"
                                                title="Configure scan settings"
                                            >
                                                <Settings className="h-3.5 w-3.5" />
                                                {repoScanConfigs[repo.id] && (
                                                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                                                )}
                                            </Button>
                                        </TableCell>
                                    )}
                                </TableRow>
                            ))}
                            {paginatedRepos.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={1 + listFields.length} className="text-center text-muted-foreground py-8">
                                        No repositories match your search
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>
                        Showing {page * PAGE_SIZE + 1} - {Math.min((page + 1) * PAGE_SIZE, filteredRepos.length)} of {filteredRepos.length}
                    </span>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page === 0}
                            onClick={() => setPage(p => p - 1)}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page >= totalPages - 1}
                            onClick={() => setPage(p => p + 1)}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}

            {/* Edit Dialog */}
            <Dialog open={editingRepo !== null} onOpenChange={() => setEditingRepo(null)}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>Configure {repos.find(r => r.id === editingRepo)?.full_name || "Repository"}</DialogTitle>
                        <DialogDescription>
                            Set configuration values for this repository
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        {listFields.map(field => {
                            // Get filtered options for this specific repo
                            const repoLangs = editingRepo ? (repoLanguages[editingRepo] || []) : [];
                            const filteredOptions = getFilteredOptions(field, repoLangs);

                            return (
                                <div key={field.name} className="space-y-2">
                                    <label className="text-sm font-medium">{formatFieldName(field.name)}</label>

                                    {field.name === "test_frameworks" ? (
                                        // Grouped by language - filtered for this repo
                                        <div className="space-y-3 max-h-[300px] overflow-y-auto">
                                            {Object.entries(filteredOptions as Record<string, string[]>).map(([group, options]) => (
                                                <div key={group} className="space-y-1">
                                                    <span className="text-xs text-muted-foreground capitalize font-medium">
                                                        {group}
                                                    </span>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {options.map(option => {
                                                            const isSelected = (editValues[field.name] || []).includes(option);
                                                            return (
                                                                <Badge
                                                                    key={option}
                                                                    variant={isSelected ? "default" : "outline"}
                                                                    className="cursor-pointer transition-colors hover:bg-primary/80"
                                                                    onClick={() => toggleEditOption(field.name, option)}
                                                                >
                                                                    {isSelected && <Check className="h-3 w-3 mr-1" />}
                                                                    {option}
                                                                </Badge>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                            {Object.keys(filteredOptions as Record<string, string[]>).length === 0 && (
                                                <div className="text-xs text-muted-foreground italic">
                                                    No matching frameworks for this repo&apos;s languages
                                                </div>
                                            )}
                                        </div>
                                    ) : field.name === "source_languages" ? (
                                        // Filtered source languages for this repo
                                        <div className="flex flex-wrap gap-1.5 max-h-[200px] overflow-y-auto">
                                            {(filteredOptions as string[]).map((option: string) => {
                                                const isSelected = (editValues[field.name] || []).includes(option);
                                                return (
                                                    <Badge
                                                        key={option}
                                                        variant={isSelected ? "default" : "outline"}
                                                        className="cursor-pointer transition-colors hover:bg-primary/80"
                                                        onClick={() => toggleEditOption(field.name, option)}
                                                    >
                                                        {isSelected && <Check className="h-3 w-3 mr-1" />}
                                                        {option}
                                                    </Badge>
                                                );
                                            })}
                                            {(filteredOptions as string[]).length === 0 && (
                                                <div className="text-xs text-muted-foreground italic">
                                                    No supported languages detected for this repo
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        // Flat list for other fields
                                        <div className="flex flex-wrap gap-1.5 max-h-[200px] overflow-y-auto">
                                            {(Array.isArray(field.options) ? field.options : []).map((option: string) => {
                                                const isSelected = (editValues[field.name] || []).includes(option);
                                                return (
                                                    <Badge
                                                        key={option}
                                                        variant={isSelected ? "default" : "outline"}
                                                        className="cursor-pointer transition-colors hover:bg-primary/80"
                                                        onClick={() => toggleEditOption(field.name, option)}
                                                    >
                                                        {isSelected && <Check className="h-3 w-3 mr-1" />}
                                                        {option}
                                                    </Badge>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditingRepo(null)}>
                            Cancel
                        </Button>
                        <Button onClick={saveEdit}>
                            Save Changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Scan Config Modal */}
            {scanConfigRepo && (
                <ScanConfigOverrideModal
                    isOpen={!!scanConfigRepo}
                    onClose={() => setScanConfigRepo(null)}
                    repoName={scanConfigRepo.name}
                    scanConfig={repoScanConfigs[scanConfigRepo.id] || null}
                    onSave={(config) => {
                        if (onScanConfigChange) {
                            onScanConfigChange(scanConfigRepo.id, config);
                        }
                        setScanConfigRepo(null);
                    }}
                    isSaving={savingScanConfig}
                />
            )}
        </div>
    );
}
