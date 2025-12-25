"use client";

import { useState, useEffect, useRef } from "react";
import { settingsApi } from "@/lib/api/settings";
import {
    DEFAULT_SCAN_CONFIG,
    type ScanConfig,
} from "@/components/sonar/scan-config-panel";

interface UseScanConfigOptions {
    /** If true, only fetch when enabled changes to true */
    fetchOnEnable?: boolean;
    /** External trigger to fetch (e.g., modal open state) */
    enabled?: boolean;
}

interface UseScanConfigReturn {
    scanConfig: ScanConfig;
    setScanConfig: React.Dispatch<React.SetStateAction<ScanConfig>>;
    isLoading: boolean;
    resetToDefaults: () => void;
}

/**
 * Custom hook to manage scan configuration with backend defaults.
 * 
 * Fetches default configuration from backend settings on mount (or when enabled).
 * Provides reset functionality to restore backend defaults.
 */
export function useScanConfig(options: UseScanConfigOptions = {}): UseScanConfigReturn {
    const { fetchOnEnable = false, enabled = true } = options;

    const [scanConfig, setScanConfig] = useState<ScanConfig>(DEFAULT_SCAN_CONFIG);
    const [isLoading, setIsLoading] = useState(true);

    // Store fetched defaults for reset functionality
    const fetchedDefaultsRef = useRef<ScanConfig | null>(null);

    useEffect(() => {
        // Skip if using fetchOnEnable mode and not enabled
        if (fetchOnEnable && !enabled) return;

        const loadDefaults = async () => {
            setIsLoading(true);
            try {
                const settings = await settingsApi.get();
                if (settings) {
                    const newConfig: ScanConfig = {
                        sonarqube: {
                            ...DEFAULT_SCAN_CONFIG.sonarqube,
                            extraProperties: settings.sonarqube.default_config || "",
                        },
                        trivy: {
                            ...DEFAULT_SCAN_CONFIG.trivy,
                            trivyYaml: settings.trivy.default_config || "",
                        },
                    };
                    fetchedDefaultsRef.current = newConfig;
                    setScanConfig(newConfig);
                }
            } catch (error) {
                console.error("Failed to load default scan settings", error);
            } finally {
                setIsLoading(false);
            }
        };

        loadDefaults();
    }, [fetchOnEnable, enabled]);

    const resetToDefaults = () => {
        if (fetchedDefaultsRef.current) {
            setScanConfig(fetchedDefaultsRef.current);
        } else {
            setScanConfig(DEFAULT_SCAN_CONFIG);
        }
    };

    return {
        scanConfig,
        setScanConfig,
        isLoading,
        resetToDefaults,
    };
}
