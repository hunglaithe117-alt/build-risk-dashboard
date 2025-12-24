"use client";

import { Input } from "@/components/ui/input";
import type { ConfigComponentProps } from "./types";

/**
 * Lookback Days Config Component
 */
export function LookbackDaysConfig({
    field,
    value,
    onChange,
    disabled = false,
}: ConfigComponentProps) {
    const currentValue = (value as number) ?? (field.default as number) ?? 90;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const numValue = parseInt(e.target.value, 10);
        if (!isNaN(numValue) && numValue > 0) {
            onChange(numValue);
        }
    };

    return (
        <div className="flex items-center gap-3">
            <Input
                type="number"
                min={1}
                max={365}
                value={currentValue}
                onChange={handleChange}
                disabled={disabled}
                className="w-24"
            />
            <span className="text-sm text-muted-foreground">days</span>
        </div>
    );
}
