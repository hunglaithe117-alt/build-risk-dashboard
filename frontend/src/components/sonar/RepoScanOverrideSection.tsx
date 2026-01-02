"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
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
import { Search, Settings, BarChart3, Shield, X, Trash2 } from "lucide-react";
import type { SonarConfig, TrivyConfig, ScanConfig } from "./scan-config-panel";

// =============================================================================
// Types
// =============================================================================

interface RepoInfo {
    id: string;  // github_repo_id
    full_name: string;
}

interface RepoScanOverrideSectionProps {
    repos: RepoInfo[];
    scanConfig: ScanConfig;
    onScanConfigChange: (config: ScanConfig) => void;
    disabled?: boolean;
}

// =============================================================================
// Component
// =============================================================================

export function RepoScanOverrideSection({
    repos,
    scanConfig,
    onScanConfigChange,
    disabled = false,
}: RepoScanOverrideSectionProps) {
    const [searchQuery, setSearchQuery] = useState("");
    const [editingRepo, setEditingRepo] = useState<RepoInfo | null>(null);

    // Local state for edit dialog
    const [editSonarConfig, setEditSonarConfig] = useState<SonarConfig>({});
    const [editTrivyConfig, setEditTrivyConfig] = useState<TrivyConfig>({});

    // Filter repos
    const filteredRepos = repos.filter(repo =>
        repo.full_name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    // Check if repo has override
    const hasOverride = (repoId: string) => {
        const hasSonar = !!scanConfig.sonarqube.repos?.[repoId];
        const hasTrivy = !!scanConfig.trivy.repos?.[repoId];
        return hasSonar || hasTrivy;
    };

    // Get override count
    const overrideCount = repos.filter(r => hasOverride(r.id)).length;

    // Open edit dialog
    const openEditDialog = (repo: RepoInfo) => {
        const sonarOverride = scanConfig.sonarqube.repos?.[repo.id] || {};
        const trivyOverride = scanConfig.trivy.repos?.[repo.id] || {};
        setEditSonarConfig(sonarOverride);
        setEditTrivyConfig(trivyOverride);
        setEditingRepo(repo);
    };

    // Save override
    const saveOverride = () => {
        if (!editingRepo) return;

        const newConfig = { ...scanConfig };

        // Check if has any values (extraProperties only for sonar)
        const hasSonarValues = editSonarConfig.extraProperties;
        const hasTrivyValues = editTrivyConfig.trivyYaml;

        // Update sonarqube repos
        if (hasSonarValues) {
            newConfig.sonarqube = {
                ...newConfig.sonarqube,
                repos: {
                    ...newConfig.sonarqube.repos,
                    [editingRepo.id]: editSonarConfig,
                },
            };
        } else {
            // Remove if empty
            const { [editingRepo.id]: _, ...rest } = newConfig.sonarqube.repos || {};
            newConfig.sonarqube = { ...newConfig.sonarqube, repos: rest };
        }

        // Update trivy repos
        if (hasTrivyValues) {
            newConfig.trivy = {
                ...newConfig.trivy,
                repos: {
                    ...newConfig.trivy.repos,
                    [editingRepo.id]: editTrivyConfig,
                },
            };
        } else {
            // Remove if empty
            const { [editingRepo.id]: _, ...rest } = newConfig.trivy.repos || {};
            newConfig.trivy = { ...newConfig.trivy, repos: rest };
        }

        onScanConfigChange(newConfig);
        setEditingRepo(null);
    };

    // Clear override for a repo
    const clearOverride = (repoId: string) => {
        const newConfig = { ...scanConfig };

        // Remove from sonarqube repos
        if (newConfig.sonarqube.repos) {
            const { [repoId]: _, ...rest } = newConfig.sonarqube.repos;
            newConfig.sonarqube = { ...newConfig.sonarqube, repos: rest };
        }

        // Remove from trivy repos
        if (newConfig.trivy.repos) {
            const { [repoId]: _, ...rest } = newConfig.trivy.repos;
            newConfig.trivy = { ...newConfig.trivy, repos: rest };
        }

        onScanConfigChange(newConfig);
    };

    if (repos.length === 0) {
        return null;
    }

    return (
        <div className="space-y-3 border-t pt-4 mt-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <Settings className="h-4 w-4" />
                    Per-Repository Overrides
                    {overrideCount > 0 && (
                        <Badge variant="secondary">
                            {overrideCount} override{overrideCount > 1 ? "s" : ""}
                        </Badge>
                    )}
                </div>
            </div>

            <p className="text-xs text-muted-foreground">
                Override scan configuration for specific repositories. Repos without overrides use the default config above.
            </p>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search repos..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 h-8 text-sm"
                />
            </div>

            {/* Repo table */}
            <div className="border rounded-lg max-h-[200px] overflow-y-auto">
                <Table>
                    <TableHeader>
                        <TableRow className="bg-muted/50">
                            <TableHead className="text-xs">Repository</TableHead>
                            <TableHead className="text-xs w-[100px]">Status</TableHead>
                            <TableHead className="text-xs w-[80px]">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {filteredRepos.slice(0, 20).map(repo => (
                            <TableRow key={repo.id} className="text-sm">
                                <TableCell className="py-2 font-medium">
                                    {repo.full_name}
                                </TableCell>
                                <TableCell className="py-2">
                                    {hasOverride(repo.id) ? (
                                        <Badge variant="default" className="text-xs">
                                            Custom
                                        </Badge>
                                    ) : (
                                        <span className="text-xs text-muted-foreground">
                                            Default
                                        </span>
                                    )}
                                </TableCell>
                                <TableCell className="py-2">
                                    <div className="flex gap-1">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 w-6 p-0"
                                            onClick={() => openEditDialog(repo)}
                                            disabled={disabled}
                                            title="Configure"
                                        >
                                            <Settings className="h-3 w-3" />
                                        </Button>
                                        {hasOverride(repo.id) && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-6 w-6 p-0 text-destructive"
                                                onClick={() => clearOverride(repo.id)}
                                                disabled={disabled}
                                                title="Clear override"
                                            >
                                                <X className="h-3 w-3" />
                                            </Button>
                                        )}
                                    </div>
                                </TableCell>
                            </TableRow>
                        ))}
                        {filteredRepos.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={3} className="text-center text-muted-foreground py-4 text-sm">
                                    No repos found
                                </TableCell>
                            </TableRow>
                        )}
                        {filteredRepos.length > 20 && (
                            <TableRow>
                                <TableCell colSpan={3} className="text-center text-muted-foreground py-2 text-xs">
                                    +{filteredRepos.length - 20} more repos
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>

            {/* Edit Dialog */}
            <Dialog open={!!editingRepo} onOpenChange={(open) => !open && setEditingRepo(null)}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Settings className="h-5 w-5" />
                            Scan Config Override
                        </DialogTitle>
                        <DialogDescription>
                            Set custom scan configuration for <strong>{editingRepo?.full_name}</strong>.
                            Leave empty to use default config.
                        </DialogDescription>
                    </DialogHeader>

                    <Tabs defaultValue="sonarqube" className="mt-2">
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="sonarqube" className="gap-2 text-xs">
                                <BarChart3 className="h-3 w-3" />
                                SonarQube
                            </TabsTrigger>
                            <TabsTrigger value="trivy" className="gap-2 text-xs">
                                <Shield className="h-3 w-3" />
                                Trivy
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="sonarqube" className="space-y-3 mt-3">
                            <div className="space-y-2">
                                <Label htmlFor="edit-extra-props" className="text-xs">
                                    Scanner Properties (sonar-project.properties)
                                </Label>
                                <Textarea
                                    id="edit-extra-props"
                                    placeholder="sonar.sources=src&#10;sonar.exclusions=**/test/**"
                                    value={editSonarConfig.extraProperties || ""}
                                    onChange={(e) => setEditSonarConfig({
                                        ...editSonarConfig,
                                        extraProperties: e.target.value,
                                    })}
                                    rows={8}
                                    className="font-mono text-xs"
                                />
                                <p className="text-xs text-muted-foreground">
                                    One property per line in key=value format
                                </p>
                            </div>
                        </TabsContent>

                        <TabsContent value="trivy" className="space-y-3 mt-3">
                            <div className="space-y-2">
                                <Label htmlFor="edit-trivy-yaml" className="text-xs">
                                    trivy.yaml
                                </Label>
                                <Textarea
                                    id="edit-trivy-yaml"
                                    placeholder="severity:&#10;  - CRITICAL&#10;  - HIGH"
                                    value={editTrivyConfig.trivyYaml || ""}
                                    onChange={(e) => setEditTrivyConfig({
                                        ...editTrivyConfig,
                                        trivyYaml: e.target.value,
                                    })}
                                    rows={8}
                                    className="font-mono text-xs"
                                />
                            </div>
                        </TabsContent>
                    </Tabs>

                    <DialogFooter className="mt-4">
                        <Button variant="outline" size="sm" onClick={() => setEditingRepo(null)}>
                            Cancel
                        </Button>
                        <Button size="sm" onClick={saveOverride}>
                            Save Override
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
