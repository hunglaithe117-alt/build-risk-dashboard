"use client";

import { useState } from "react";
import {
    DEFAULT_SCAN_CONFIG,
    type ScanConfig,
} from "@/components/sonar/scan-config-panel";

interface UseScanConfigOptions {
    /** If true, only initialize when enabled changes to true */
    fetchOnEnable?: boolean;
    /** External trigger (e.g., modal open state) */
    enabled?: boolean;
}

interface UseScanConfigReturn {
    scanConfig: ScanConfig;
    setScanConfig: React.Dispatch<React.SetStateAction<ScanConfig>>;
    isLoading: boolean;
    resetToDefaults: () => void;
}

/**
 * Custom hook to manage scan configuration.
 * 
 * With repo-level only structure, configuration is per-repo.
 * This hook manages the scan config state and provides reset functionality.
 */
export function useScanConfig(_options: UseScanConfigOptions = {}): UseScanConfigReturn {
    const [scanConfig, setScanConfig] = useState<ScanConfig>(DEFAULT_SCAN_CONFIG);
    // No async loading needed for repo-level only config
    const [isLoading] = useState(false);

    const resetToDefaults = () => {
        setScanConfig(DEFAULT_SCAN_CONFIG);
    };

    return {
        scanConfig,
        setScanConfig,
        isLoading,
        resetToDefaults,
    };
}
