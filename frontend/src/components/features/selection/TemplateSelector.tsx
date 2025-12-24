"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Loader2, Search, FileStack, Check } from "lucide-react";
import { datasetsApi } from "@/lib/api";
import type { DatasetTemplateRecord } from "@/types";

interface TemplateSelectorProps {
    onApplyTemplate: (featureNames: string[]) => void;
    disabled?: boolean;
}

export function TemplateSelector({ onApplyTemplate, disabled }: TemplateSelectorProps) {
    const [templates, setTemplates] = useState<DatasetTemplateRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [isOpen, setIsOpen] = useState(false);
    const [appliedTemplate, setAppliedTemplate] = useState<string | null>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Load templates on mount
    useEffect(() => {
        async function loadTemplates() {
            try {
                setLoading(true);
                const response = await datasetsApi.listTemplates();
                setTemplates(response.items);
            } catch (err) {
                console.error("Failed to load templates:", err);
            } finally {
                setLoading(false);
            }
        }
        loadTemplates();
    }, []);

    // Close dropdown when clicking outside
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // Filter templates by search query
    const filteredTemplates = templates.filter((t) => {
        if (!searchQuery.trim()) return true;
        const query = searchQuery.toLowerCase();
        return (
            t.name.toLowerCase().includes(query) ||
            t.description?.toLowerCase().includes(query) ||
            t.tags.some((tag) => tag.toLowerCase().includes(query))
        );
    });

    const handleSelect = (template: DatasetTemplateRecord) => {
        onApplyTemplate(template.feature_names);
        setAppliedTemplate(template.name);
        setIsOpen(false);
        setSearchQuery("");
    };

    return (
        <div ref={dropdownRef} className="relative">
            <div className="flex items-center gap-2">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                        placeholder="Search templates to auto-select features..."
                        value={searchQuery}
                        onChange={(e) => {
                            setSearchQuery(e.target.value);
                            setIsOpen(true);
                        }}
                        onFocus={() => setIsOpen(true)}
                        className="pl-9"
                        disabled={disabled || loading}
                    />
                </div>
                {appliedTemplate && (
                    <Badge variant="secondary" className="gap-1 whitespace-nowrap">
                        <Check className="h-3 w-3" />
                        {appliedTemplate}
                    </Badge>
                )}
            </div>

            {/* Dropdown */}
            {isOpen && (
                <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-64 overflow-auto rounded-md border bg-popover shadow-lg">
                    {loading ? (
                        <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        </div>
                    ) : filteredTemplates.length === 0 ? (
                        <div className="py-4 text-center text-sm text-muted-foreground">
                            No templates found
                        </div>
                    ) : (
                        <ul className="py-1">
                            {filteredTemplates.map((template) => (
                                <li key={template.id}>
                                    <Button
                                        variant="ghost"
                                        className="w-full justify-start h-auto py-2 px-3 rounded-none"
                                        onClick={() => handleSelect(template)}
                                        disabled={disabled}
                                    >
                                        <div className="flex flex-col items-start gap-1 w-full">
                                            <div className="flex items-center gap-2 w-full">
                                                <FileStack className="h-4 w-4 text-muted-foreground shrink-0" />
                                                <span className="font-medium truncate">{template.name}</span>
                                                <Badge variant="outline" className="ml-auto text-xs shrink-0">
                                                    {template.feature_names.length} features
                                                </Badge>
                                            </div>
                                            {template.description && (
                                                <p className="text-xs text-muted-foreground line-clamp-1 pl-6">
                                                    {template.description}
                                                </p>
                                            )}
                                            {template.tags.length > 0 && (
                                                <div className="flex gap-1 pl-6">
                                                    {template.tags.slice(0, 3).map((tag) => (
                                                        <Badge key={tag} variant="secondary" className="text-xs">
                                                            {tag}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </Button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
