/**
 * Feature Config UI Components Registry
 * 
 * Each feature config field has its own UI component for custom rendering.
 * When adding a new feature config, create a new file in this folder and
 * register it in the configComponents map below.
 */

import { SourceLanguagesConfig } from "./SourceLanguagesConfig";
import { LookbackDaysConfig } from "./LookbackDaysConfig";
import { TestFrameworksConfig } from "./TestFrameworksConfig";

// Re-export types
export type { ConfigField, ConfigComponentProps } from "./types";

// Registry of config components by field name
export const configComponents: Record<string, React.ComponentType<import("./types").ConfigComponentProps>> = {
    source_languages: SourceLanguagesConfig,
    lookback_days: LookbackDaysConfig,
    test_frameworks: TestFrameworksConfig,
};

// Check if a custom component exists for a field
export const hasCustomConfig = (fieldName: string): boolean => {
    return fieldName in configComponents;
};

// Get the component for a field (or null if not found)
export const getConfigComponent = (
    fieldName: string
): React.ComponentType<import("./types").ConfigComponentProps> | null => {
    return configComponents[fieldName] || null;
};

export { SourceLanguagesConfig, LookbackDaysConfig, TestFrameworksConfig };
