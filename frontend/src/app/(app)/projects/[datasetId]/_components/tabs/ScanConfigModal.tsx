"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

// =============================================================================
// Types
// =============================================================================

interface ScanConfigModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (config: string | null) => void;
    toolType: string;
    currentConfig?: string | null;
    mode: "start" | "retry";
    commitSha?: string;
}

// =============================================================================
// Templates
// =============================================================================

const SONAR_TEMPLATE = `# SonarQube configuration
sonar.sources=src
sonar.exclusions=**/test/**,**/node_modules/**,**/vendor/**
sonar.java.binaries=.
sonar.sourceEncoding=UTF-8
`;

const TRIVY_TEMPLATE = `# Trivy configuration
severity:
  - CRITICAL
  - HIGH
  - MEDIUM

timeout: 10m

scan:
  skip-dirs:
    - node_modules
    - vendor
    - .git
`;

// =============================================================================
// Component
// =============================================================================

export function ScanConfigModal({
    isOpen,
    onClose,
    onSubmit,
    toolType,
    currentConfig,
    mode,
    commitSha,
}: ScanConfigModalProps) {
    const [config, setConfig] = useState(currentConfig || "");
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleTemplateSelect = (template: string) => {
        if (template === "sonar") {
            setConfig(SONAR_TEMPLATE);
        } else if (template === "trivy") {
            setConfig(TRIVY_TEMPLATE);
        } else {
            setConfig("");
        }
    };

    const handleSubmit = async () => {
        setIsSubmitting(true);
        try {
            await onSubmit(config.trim() || null);
            onClose();
        } finally {
            setIsSubmitting(false);
        }
    };

    const title = mode === "start"
        ? "Configure Scan"
        : `Retry Scan${commitSha ? ` - ${commitSha.slice(0, 8)}` : ""}`;

    const description = mode === "start"
        ? "Set default configuration for all commits in this scan."
        : "Set custom configuration for this specific commit.";

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-2xl">
                <DialogHeader>
                    <DialogTitle>{title}</DialogTitle>
                    <DialogDescription>{description}</DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="flex items-center gap-4">
                        <Label>Template:</Label>
                        <Select onValueChange={handleTemplateSelect}>
                            <SelectTrigger className="w-48">
                                <SelectValue placeholder="Select template" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="none">No template</SelectItem>
                                <SelectItem value="sonar">SonarQube</SelectItem>
                                <SelectItem value="trivy">Trivy</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div>
                        <Label>
                            {toolType === "sonarqube"
                                ? "sonar-project.properties"
                                : "trivy.yaml"}
                        </Label>
                        <Textarea
                            value={config}
                            onChange={(e) => setConfig(e.target.value)}
                            placeholder={`Enter ${toolType === "sonarqube" ? "SonarQube" : "Trivy"} configuration...`}
                            className="mt-2 font-mono text-sm h-64"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                            Leave empty to use default settings.
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={isSubmitting}>
                        {mode === "start" ? "Start Scan" : "Retry"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
