"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Database,
  GitBranch,
  Users,
  MessageSquare,
  FileCode,
  Clock,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import type { FeatureCategory, FeatureDefinition } from "@/types/dataset";

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  build_log: <FileCode className="h-4 w-4" />,
  git_diff: <GitBranch className="h-4 w-4" />,
  git_history: <Clock className="h-4 w-4" />,
  team: <Users className="h-4 w-4" />,
  discussion: <MessageSquare className="h-4 w-4" />,
  repo_snapshot: <Database className="h-4 w-4" />,
  metadata: <Info className="h-4 w-4" />,
  pr_info: <GitBranch className="h-4 w-4" />,
};

interface FeatureSelectorProps {
  categories: FeatureCategory[];
  selectedFeatures: string[];
  onSelectionChange: (features: string[]) => void;
  mlOnly?: boolean;
}

export function FeatureSelector({
  categories,
  selectedFeatures,
  onSelectionChange,
  mlOnly = false,
}: FeatureSelectorProps) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(categories.map((c) => c.category))
  );
  const [searchQuery, setSearchQuery] = useState("");

  // Filter features based on search and mlOnly
  const filteredCategories = useMemo(() => {
    return categories
      .map((category) => ({
        ...category,
        features: category.features.filter((f) => {
          const matchesSearch =
            !searchQuery ||
            f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            f.slug.toLowerCase().includes(searchQuery.toLowerCase()) ||
            f.description.toLowerCase().includes(searchQuery.toLowerCase());
          const matchesMl = !mlOnly || f.is_ml_feature;
          return matchesSearch && matchesMl;
        }),
      }))
      .filter((category) => category.features.length > 0);
  }, [categories, searchQuery, mlOnly]);

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const toggleFeature = (featureId: string) => {
    if (selectedFeatures.includes(featureId)) {
      onSelectionChange(selectedFeatures.filter((f) => f !== featureId));
    } else {
      onSelectionChange([...selectedFeatures, featureId]);
    }
  };

  const toggleAllInCategory = (category: FeatureCategory) => {
    const categoryIds = category.features.map((f) => f.id);
    const allSelected = categoryIds.every((id) =>
      selectedFeatures.includes(id)
    );

    if (allSelected) {
      // Deselect all in category
      onSelectionChange(
        selectedFeatures.filter((f) => !categoryIds.includes(f))
      );
    } else {
      // Select all in category
      const newSelection = new Set([...selectedFeatures, ...categoryIds]);
      onSelectionChange(Array.from(newSelection));
    }
  };

  const selectAll = () => {
    const allIds = filteredCategories.flatMap((c) =>
      c.features.map((f) => f.id)
    );
    onSelectionChange(allIds);
  };

  const clearAll = () => {
    onSelectionChange([]);
  };

  const getCategorySelectionStatus = (category: FeatureCategory) => {
    const categoryIds = category.features.map((f) => f.id);
    const selectedCount = categoryIds.filter((id) =>
      selectedFeatures.includes(id)
    ).length;

    if (selectedCount === 0) return "none";
    if (selectedCount === categoryIds.length) return "all";
    return "partial";
  };

  return (
    <div className="space-y-4">
      {/* Search and actions */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Search features..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="flex gap-2">
          <button
            onClick={selectAll}
            className="text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400"
          >
            Select All
          </button>
          <span className="text-muted-foreground">|</span>
          <button
            onClick={clearAll}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Selection count */}
      <div className="text-sm text-muted-foreground">
        {selectedFeatures.length} feature
        {selectedFeatures.length !== 1 ? "s" : ""} selected
      </div>

      {/* Feature categories */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
        {filteredCategories.map((category) => {
          const isExpanded = expandedCategories.has(category.category);
          const selectionStatus = getCategorySelectionStatus(category);

          return (
            <div
              key={category.category}
              className="rounded-lg border bg-card"
            >
              {/* Category header */}
              <div
                className="flex items-center gap-3 p-3 cursor-pointer hover:bg-muted/50"
                onClick={() => toggleCategory(category.category)}
              >
                <button className="p-0.5">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
                <div
                  className={cn(
                    "p-1.5 rounded",
                    selectionStatus === "all"
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {CATEGORY_ICONS[category.category] || (
                    <Database className="h-4 w-4" />
                  )}
                </div>
                <div className="flex-1">
                  <p className="font-medium text-sm">{category.display_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {category.features.length} features
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleAllInCategory(category);
                  }}
                  className={cn(
                    "text-xs px-2 py-1 rounded",
                    selectionStatus === "all"
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  )}
                >
                  {selectionStatus === "all" ? "Deselect all" : "Select all"}
                </button>
              </div>

              {/* Features list */}
              {isExpanded && (
                <div className="border-t px-3 py-2 space-y-1">
                  {category.features.map((feature) => (
                    <FeatureItem
                      key={feature.id}
                      feature={feature}
                      isSelected={selectedFeatures.includes(feature.id)}
                      onToggle={() => toggleFeature(feature.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface FeatureItemProps {
  feature: FeatureDefinition;
  isSelected: boolean;
  onToggle: () => void;
}

function FeatureItem({ feature, isSelected, onToggle }: FeatureItemProps) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div
      className={cn(
        "rounded-md p-2 transition-colors",
        isSelected
          ? "bg-blue-50 dark:bg-blue-950/30"
          : "hover:bg-muted/50"
      )}
    >
      <div className="flex items-start gap-3">
        <Checkbox
          checked={isSelected}
          onCheckedChange={onToggle}
          className="mt-0.5"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">
              {feature.slug}
            </span>
            {feature.is_ml_feature && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                ML
              </span>
            )}
            {feature.requires_clone && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300">
                Clone
              </span>
            )}
            {feature.requires_log && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">
                Log
              </span>
            )}
          </div>
          <p className="text-sm font-medium">{feature.name}</p>
          {showDetails && (
            <div className="mt-1 text-xs text-muted-foreground space-y-1">
              <p>{feature.description}</p>
              <p>Type: {feature.data_type}</p>
              {feature.dependencies.length > 0 && (
                <p>
                  Dependencies: {feature.dependencies.join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowDetails(!showDetails);
          }}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {showDetails ? "Less" : "More"}
        </button>
      </div>
    </div>
  );
}
