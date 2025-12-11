"use client";

import { memo, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    AlertCircle,
    Check,
    ChevronDown,
    ChevronRight,
    FileText,
    GitBranch,
    Search,
    Settings,
    Shield,
    Github,
    Database,
} from "lucide-react";

interface FeatureDefinition {
    name: string;
    display_name: string;
    description: string;
    data_type: string;
    is_active: boolean;
}

interface ExtractorInfo {
    name: string;
    display_name: string;
    features: FeatureDefinition[];
    feature_count: number;
}

interface SourceInfo {
    source: string;
    display_name: string;
    description: string;
    icon: string;
    is_configured: boolean;
    extractors: Record<string, ExtractorInfo>;
    total_features: number;
}

interface ListViewProps {
    sources: SourceInfo[];
    selectedFeatures: Set<string>;
    expandedSources: Set<string>;
    expandedExtractors: Set<string>;
    onToggleFeature: (featureName: string) => void;
    onToggleExtractor: (extractorName: string, features: string[]) => void;
    onToggleSource: (sourceName: string) => void;
    onToggleSourceExpand: (sourceName: string) => void;
    onToggleExtractorExpand: (extractorName: string) => void;
    searchQuery: string;
    onSearchChange: (query: string) => void;
    isLoading?: boolean;
}

const sourceIcons: Record<string, typeof GitBranch> = {
    git: GitBranch,
    github: Github,
    build_log: FileText,
    sonarqube: Settings,
    trivy: Shield,
    repo: Database,
};

export const ListView = memo(function ListView({
    sources,
    selectedFeatures,
    expandedSources,
    expandedExtractors,
    onToggleFeature,
    onToggleExtractor,
    onToggleSource,
    onToggleSourceExpand,
    onToggleExtractorExpand,
    searchQuery,
    onSearchChange,
    isLoading = false,
}: ListViewProps) {
    if (isLoading) {
        return (
            <div className="flex h-[400px] items-center justify-center">
                <div className="text-muted-foreground">Loading features...</div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    placeholder="Search features..."
                    value={searchQuery}
                    onChange={(e) => onSearchChange(e.target.value)}
                    className="pl-10"
                />
            </div>

            {/* Sources */}
            <div className="max-h-[400px] space-y-3 overflow-y-auto pr-2">
                {sources.map((source) => (
                    <SourceCard
                        key={source.source}
                        source={source}
                        selectedFeatures={selectedFeatures}
                        isExpanded={expandedSources.has(source.source)}
                        expandedExtractors={expandedExtractors}
                        onToggleSource={() => onToggleSource(source.source)}
                        onToggleExpand={() => onToggleSourceExpand(source.source)}
                        onToggleExtractor={onToggleExtractor}
                        onToggleExtractorExpand={onToggleExtractorExpand}
                        onToggleFeature={onToggleFeature}
                    />
                ))}
            </div>

            {sources.length === 0 && (
                <div className="flex h-[200px] items-center justify-center text-muted-foreground">
                    No features match your search
                </div>
            )}
        </div>
    );
});

interface SourceCardProps {
    source: SourceInfo;
    selectedFeatures: Set<string>;
    isExpanded: boolean;
    expandedExtractors: Set<string>;
    onToggleSource: () => void;
    onToggleExpand: () => void;
    onToggleExtractor: (extractorName: string, features: string[]) => void;
    onToggleExtractorExpand: (extractorName: string) => void;
    onToggleFeature: (featureName: string) => void;
}

function SourceCard({
    source,
    selectedFeatures,
    isExpanded,
    expandedExtractors,
    onToggleSource,
    onToggleExpand,
    onToggleExtractor,
    onToggleExtractorExpand,
    onToggleFeature,
}: SourceCardProps) {
    const Icon = sourceIcons[source.source] || Database;

    // Count selected features in this source
    const allSourceFeatures = useMemo(() => {
        const features: string[] = [];
        Object.values(source.extractors).forEach((ext) => {
            ext.features.forEach((f) => features.push(f.name));
        });
        return features;
    }, [source.extractors]);

    const selectedCount = allSourceFeatures.filter((f) =>
        selectedFeatures.has(f)
    ).length;
    const allSelected = selectedCount === allSourceFeatures.length && allSourceFeatures.length > 0;
    const someSelected = selectedCount > 0 && selectedCount < allSourceFeatures.length;

    return (
        <div
            className={`rounded-lg border ${source.is_configured
                ? "border-slate-200 dark:border-slate-700"
                : "border-dashed border-slate-300 opacity-75 dark:border-slate-600"
                }`}
        >
            {/* Source Header */}
            <div
                className={`flex cursor-pointer items-center justify-between p-3 ${source.is_configured ? "hover:bg-slate-50 dark:hover:bg-slate-800/50" : ""
                    }`}
                onClick={source.is_configured ? onToggleExpand : undefined}
            >
                <div className="flex items-center gap-3">
                    <div
                        className={`rounded-lg p-2 ${source.is_configured
                            ? "bg-slate-100 dark:bg-slate-800"
                            : "bg-slate-50 dark:bg-slate-900"
                            }`}
                    >
                        <Icon
                            className={`h-4 w-4 ${source.is_configured
                                ? "text-slate-600 dark:text-slate-400"
                                : "text-slate-400"
                                }`}
                        />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <span className="font-medium">{source.display_name}</span>
                            {source.is_configured ? (
                                <Badge variant="outline" className="text-xs border-green-500 text-green-600">
                                    <Check className="mr-1 h-2.5 w-2.5" />
                                    Available
                                </Badge>
                            ) : (
                                <Badge variant="outline" className="text-xs">
                                    <AlertCircle className="mr-1 h-2.5 w-2.5" />
                                    Not Configured
                                </Badge>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground">{source.description}</p>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {source.is_configured && (
                        <>
                            <Badge
                                variant={allSelected ? "default" : someSelected ? "secondary" : "outline"}
                                className="text-xs"
                            >
                                {selectedCount}/{source.total_features}
                            </Badge>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onToggleSource();
                                }}
                            >
                                {allSelected ? "Deselect" : "Select All"}
                            </Button>
                            {isExpanded ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* Extractors */}
            {source.is_configured && isExpanded && (
                <div className="border-t p-3 pt-2">
                    <div className="space-y-2">
                        {Object.values(source.extractors).map((extractor) => (
                            <ExtractorSection
                                key={extractor.name}
                                extractor={extractor}
                                selectedFeatures={selectedFeatures}
                                isExpanded={expandedExtractors.has(extractor.name)}
                                onToggleExtractor={() =>
                                    onToggleExtractor(
                                        extractor.name,
                                        extractor.features.map((f) => f.name)
                                    )
                                }
                                onToggleExpand={() => onToggleExtractorExpand(extractor.name)}
                                onToggleFeature={onToggleFeature}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

interface ExtractorSectionProps {
    extractor: ExtractorInfo;
    selectedFeatures: Set<string>;
    isExpanded: boolean;
    onToggleExtractor: () => void;
    onToggleExpand: () => void;
    onToggleFeature: (featureName: string) => void;
}

function ExtractorSection({
    extractor,
    selectedFeatures,
    isExpanded,
    onToggleExtractor,
    onToggleExpand,
    onToggleFeature,
}: ExtractorSectionProps) {
    const selectedCount = extractor.features.filter((f) =>
        selectedFeatures.has(f.name)
    ).length;
    const allSelected = selectedCount === extractor.features.length;
    const someSelected = selectedCount > 0 && !allSelected;

    return (
        <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
            <div className="rounded-md bg-slate-50 dark:bg-slate-800/50">
                <CollapsibleTrigger asChild>
                    <div className="flex cursor-pointer items-center justify-between px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800">
                        <div className="flex items-center gap-2">
                            <Checkbox
                                checked={allSelected}
                                // ref prop for indeterminate is not standard, using data attribute or custom styling
                                className={someSelected ? "data-[state=checked]:bg-yellow-500" : ""}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onToggleExtractor();
                                }}
                            />
                            <span className="text-sm font-medium">{extractor.display_name}</span>
                            <span className="text-xs text-muted-foreground">
                                ({selectedCount}/{extractor.feature_count})
                            </span>
                        </div>
                        {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        ) : (
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        )}
                    </div>
                </CollapsibleTrigger>

                <CollapsibleContent>
                    <div className="space-y-1 px-3 pb-2">
                        {extractor.features.map((feature) => (
                            <label
                                key={feature.name}
                                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-700"
                            >
                                <Checkbox
                                    checked={selectedFeatures.has(feature.name)}
                                    onCheckedChange={() => onToggleFeature(feature.name)}
                                />
                                <div className="flex-1 min-w-0">
                                    <span className="text-sm font-mono">{feature.name}</span>
                                    <p className="truncate text-xs text-muted-foreground">
                                        {feature.description}
                                    </p>
                                </div>
                            </label>
                        ))}
                    </div>
                </CollapsibleContent>
            </div>
        </Collapsible>
    );
}
