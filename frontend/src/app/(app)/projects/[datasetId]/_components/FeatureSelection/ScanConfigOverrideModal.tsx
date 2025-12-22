"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import { BarChart3, Shield, FileCode } from "lucide-react";

// =============================================================================
// Types
// =============================================================================

export interface RepoScanConfig {
    sonarqube_properties: string | null;
    trivy_yaml: string | null;
}

interface ScanConfigOverrideModalProps {
    isOpen: boolean;
    onClose: () => void;
    repoName: string;
    scanConfig: RepoScanConfig | null;
    onSave: (config: RepoScanConfig) => void;
    isSaving?: boolean;
}

// =============================================================================
// Templates
// =============================================================================

const SONAR_TEMPLATE = `# SonarQube Project Properties
# https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/analysis-parameters/

# Sources
sonar.sources=src
sonar.exclusions=**/test/**,**/tests/**,**/__tests__/**

# Language-specific (uncomment as needed)
# sonar.java.binaries=target/classes
# sonar.python.version=3.11
`;

const TRIVY_TEMPLATE = `# Trivy Configuration
# https://aquasecurity.github.io/trivy/latest/docs/configuration/

# Scan settings
scan:
  scanners:
    - vuln
    - misconfig
    - secret

severity:
  - CRITICAL
  - HIGH
  - MEDIUM

# Skip directories
skip-dirs:
  - node_modules
  - vendor
  - .git

# Ignore unfixed vulnerabilities
ignore-unfixed: false
`;

// =============================================================================
// Component
// =============================================================================

export function ScanConfigOverrideModal({
    isOpen,
    onClose,
    repoName,
    scanConfig,
    onSave,
    isSaving = false,
}: ScanConfigOverrideModalProps) {
    const [sonarProperties, setSonarProperties] = React.useState(
        scanConfig?.sonarqube_properties || ""
    );
    const [trivyYaml, setTrivyYaml] = React.useState(
        scanConfig?.trivy_yaml || ""
    );

    // Reset on open
    React.useEffect(() => {
        if (isOpen) {
            setSonarProperties(scanConfig?.sonarqube_properties || "");
            setTrivyYaml(scanConfig?.trivy_yaml || "");
        }
    }, [isOpen, scanConfig]);

    const handleSave = () => {
        onSave({
            sonarqube_properties: sonarProperties.trim() || null,
            trivy_yaml: trivyYaml.trim() || null,
        });
    };

    const handleLoadSonarTemplate = () => {
        setSonarProperties(SONAR_TEMPLATE);
    };

    const handleLoadTrivyTemplate = () => {
        setTrivyYaml(TRIVY_TEMPLATE);
    };

    const hasConfig = sonarProperties.trim() || trivyYaml.trim();

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileCode className="h-5 w-5" />
                        Custom Scan Configuration
                    </DialogTitle>
                    <DialogDescription>
                        Override default scan settings for <strong>{repoName}</strong>.
                        Leave empty to use global defaults.
                    </DialogDescription>
                </DialogHeader>

                <Tabs defaultValue="sonarqube" className="mt-4">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="sonarqube" className="gap-2">
                            <BarChart3 className="h-4 w-4" />
                            SonarQube
                            {sonarProperties.trim() && (
                                <span className="ml-1 w-2 h-2 bg-blue-500 rounded-full" />
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="trivy" className="gap-2">
                            <Shield className="h-4 w-4" />
                            Trivy
                            {trivyYaml.trim() && (
                                <span className="ml-1 w-2 h-2 bg-green-500 rounded-full" />
                            )}
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="sonarqube" className="space-y-4 mt-4">
                        <div className="flex items-center justify-between">
                            <Label htmlFor="sonar-props" className="text-sm font-medium">
                                sonar-project.properties
                            </Label>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleLoadSonarTemplate}
                            >
                                Load Template
                            </Button>
                        </div>
                        <Textarea
                            id="sonar-props"
                            placeholder="# Enter custom sonar-project.properties content..."
                            value={sonarProperties}
                            onChange={(e) => setSonarProperties(e.target.value)}
                            rows={12}
                            className="font-mono text-sm"
                        />
                        <p className="text-xs text-muted-foreground">
                            This content will be written to sonar-project.properties before scanning.
                        </p>
                    </TabsContent>

                    <TabsContent value="trivy" className="space-y-4 mt-4">
                        <div className="flex items-center justify-between">
                            <Label htmlFor="trivy-yaml" className="text-sm font-medium">
                                trivy.yaml
                            </Label>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleLoadTrivyTemplate}
                            >
                                Load Template
                            </Button>
                        </div>
                        <Textarea
                            id="trivy-yaml"
                            placeholder="# Enter custom trivy.yaml content..."
                            value={trivyYaml}
                            onChange={(e) => setTrivyYaml(e.target.value)}
                            rows={12}
                            className="font-mono text-sm"
                        />
                        <p className="text-xs text-muted-foreground">
                            This content will be written to trivy.yaml before scanning.
                        </p>
                    </TabsContent>
                </Tabs>

                <DialogFooter className="mt-6">
                    <Button variant="outline" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button onClick={handleSave} disabled={isSaving}>
                        {isSaving ? "Saving..." : hasConfig ? "Save Configuration" : "Clear Configuration"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
