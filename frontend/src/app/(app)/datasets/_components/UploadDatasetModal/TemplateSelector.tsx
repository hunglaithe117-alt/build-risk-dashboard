"use client";

import { useState } from "react";
import { Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { DatasetTemplateRecord } from "@/types";
import type { TemplateSelectorProps } from "./types";

export function TemplateSelector({
    templates,
    selectedTemplate,
    onSelectTemplate,
    onApplyTemplate,
}: TemplateSelectorProps) {
    const [templateSearch, setTemplateSearch] = useState("");
    const [showDropdown, setShowDropdown] = useState(false);

    const filteredTemplates = templates.filter(t =>
        !templateSearch || t.name.toLowerCase().includes(templateSearch.toLowerCase())
    );

    return (
        <div className="space-y-4 rounded-lg border p-4 bg-slate-50/50 dark:bg-slate-900/20">
            <h4 className="text-sm font-semibold">Apply Feature Template</h4>
            <div className="flex gap-2">
                <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search templates..."
                        className="pl-9"
                        value={templateSearch}
                        onChange={(e) => setTemplateSearch(e.target.value)}
                        onFocus={() => setShowDropdown(true)}
                        onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
                    />

                    {/* Dropdown List */}
                    {showDropdown && (
                        <div className="absolute top-full left-0 right-0 mt-1 max-h-[300px] overflow-y-auto rounded-md border bg-white dark:bg-slate-950 shadow-lg z-50 p-1">
                            {filteredTemplates.map(tpl => (
                                <div
                                    key={tpl.id}
                                    className="flex flex-col gap-1 rounded-sm px-2 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                                    onClick={() => {
                                        setTemplateSearch(tpl.name);
                                        onSelectTemplate(tpl);
                                    }}
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="font-medium text-sm">{tpl.name}</span>
                                        <Badge variant="secondary" className="text-[10px]">{tpl.feature_names.length} feats</Badge>
                                    </div>
                                    <span className="text-xs text-muted-foreground line-clamp-1">{tpl.description}</span>
                                </div>
                            ))}
                            {templates.length === 0 && <div className="p-2 text-sm text-muted-foreground text-center">No templates found</div>}
                        </div>
                    )}
                </div>
                <Button
                    disabled={!selectedTemplate}
                    onClick={onApplyTemplate}
                >
                    Apply
                </Button>
            </div>

            {/* Selected Template Details */}
            {selectedTemplate && (
                <div className="flex items-start gap-3 p-3 text-sm border rounded-md bg-background">
                    <div className="flex-1 space-y-2">
                        <div className="font-medium">Selected: {selectedTemplate.name}</div>
                        <p className="text-muted-foreground text-xs">{selectedTemplate.description}</p>
                        <div className="flex flex-wrap gap-1">
                            {(selectedTemplate.tags || []).map((tag) => (
                                <Badge key={tag} variant="outline" className="text-[10px]">{tag}</Badge>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
