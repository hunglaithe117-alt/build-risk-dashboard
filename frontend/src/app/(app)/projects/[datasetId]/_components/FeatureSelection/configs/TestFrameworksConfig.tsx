"use client";

import { Badge } from "@/components/ui/badge";
import type { ConfigComponentProps } from "./types";

/**
 * Test Frameworks Config Component
 */
export function TestFrameworksConfig({
    field,
    value,
    onChange,
    disabled = false,
}: ConfigComponentProps) {
    const selectedFrameworks = (value as string[]) || [];
    // Options come as grouped dict: { python: ["pytest", ...], ruby: [...], ... }
    const groupedOptions = (field.options as Record<string, string[]>) || {};

    const toggleOption = (option: string) => {
        if (disabled) return;
        const newValue = selectedFrameworks.includes(option)
            ? selectedFrameworks.filter(v => v !== option)
            : [...selectedFrameworks, option];
        onChange(newValue);
    };

    return (
        <div className="space-y-3">
            {Object.entries(groupedOptions).map(([language, frameworks]) => (
                <div key={language} className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted-foreground w-24 capitalize font-medium">
                        {language}:
                    </span>
                    <div className="flex flex-wrap gap-1 flex-1">
                        {frameworks.map(framework => {
                            const isSelected = selectedFrameworks.includes(framework);
                            return (
                                <Badge
                                    key={framework}
                                    variant={isSelected ? "default" : "outline"}
                                    className={`cursor-pointer transition-colors text-xs ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                                        }`}
                                    onClick={() => toggleOption(framework)}
                                >
                                    {framework}
                                </Badge>
                            );
                        })}
                    </div>
                </div>
            ))}
        </div>
    );
}
