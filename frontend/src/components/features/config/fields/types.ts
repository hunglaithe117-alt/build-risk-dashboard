/**
 * Shared types for Feature Config components
 */

export interface ConfigField {
    name: string;
    type: string;
    scope: string;
    required: boolean;
    description: string;
    default: unknown;
    options: unknown;
}

// Props passed to all config components
export interface ConfigComponentProps {
    field: ConfigField;
    value: unknown;
    onChange: (value: unknown) => void;
    disabled?: boolean;
}
