"use client";

import { Badge } from "@/components/ui/badge";
import type { ConfigComponentProps } from "./types";

/**
 * Source Languages Config Component
 */
export function SourceLanguagesConfig({
    field,
    value,
    onChange,
    disabled = false,
}: ConfigComponentProps) {
    const selectedLanguages = (value as string[]) || [];
    const options = (field.options as string[]) || [];

    const toggleOption = (option: string) => {
        if (disabled) return;
        const newValue = selectedLanguages.includes(option)
            ? selectedLanguages.filter(v => v !== option)
            : [...selectedLanguages, option];
        onChange(newValue);
    };

    return (
        <div className="flex flex-wrap gap-1.5">
            {options.map(option => {
                const isSelected = selectedLanguages.includes(option);
                return (
                    <Badge
                        key={option}
                        variant={isSelected ? "default" : "outline"}
                        className={`cursor-pointer transition-colors ${disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-primary/80"
                            }`}
                        onClick={() => toggleOption(option)}
                    >
                        {option}
                    </Badge>
                );
            })}
        </div>
    );
}
