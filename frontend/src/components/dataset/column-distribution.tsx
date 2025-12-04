"use client";

import { useState, useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
} from "recharts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BarChart3, PieChart as PieChartIcon, Info, TrendingUp, Hash, ToggleLeft, Type, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

interface ColumnDistributionProps {
  columns: string[];
  rows: Record<string, unknown>[];
}

interface HistogramBin {
  range: string;
  count: number;
  percent: number;
}

interface CategoryCount {
  name: string;
  value: number;
  percent: number;
}

export interface ColumnStats {
  type: "numeric" | "boolean" | "categorical" | "datetime" | "unknown";
  count: number;
  missing: number;
  unique: number;
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  std?: number;
  trueCount?: number;
  falseCount?: number;
}

const COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
];

export function getColumnType(values: unknown[]): ColumnStats["type"] {
  const nonNull = values.filter(v => v !== null && v !== undefined && v !== "");
  
  if (nonNull.length === 0) return "unknown";
  
  // Check boolean
  const allBoolean = nonNull.every(v => 
    typeof v === "boolean" || v === "true" || v === "false" || v === 0 || v === 1
  );
  if (allBoolean) return "boolean";
  
  // Check numeric
  const allNumeric = nonNull.every(v => typeof v === "number" || !isNaN(Number(v)));
  if (allNumeric) return "numeric";
  
  // Check datetime
  const sample = String(nonNull[0]);
  if (sample.match(/^\d{4}-\d{2}-\d{2}/) || sample.includes("T")) {
    return "datetime";
  }
  
  return "categorical";
}

export function calculateStats(values: unknown[], type: ColumnStats["type"]): ColumnStats {
  const nonNull = values.filter(v => v !== null && v !== undefined && v !== "");
  const stats: ColumnStats = {
    type,
    count: values.length,
    missing: values.length - nonNull.length,
    unique: new Set(nonNull.map(v => String(v))).size,
  };
  
  if (type === "numeric") {
    const nums = nonNull.map(v => Number(v)).filter(n => !isNaN(n));
    if (nums.length > 0) {
      stats.min = Math.min(...nums);
      stats.max = Math.max(...nums);
      stats.mean = nums.reduce((a, b) => a + b, 0) / nums.length;
      
      // Median
      const sorted = [...nums].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      stats.median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
      
      // Standard deviation
      const variance = nums.reduce((acc, val) => acc + Math.pow(val - stats.mean!, 2), 0) / nums.length;
      stats.std = Math.sqrt(variance);
    }
  } else if (type === "boolean") {
    stats.trueCount = nonNull.filter(v => 
      v === true || v === "true" || v === 1
    ).length;
    stats.falseCount = nonNull.length - stats.trueCount;
  }
  
  return stats;
}

function createHistogram(values: number[], bins: number = 10): HistogramBin[] {
  const validValues = values.filter(v => !isNaN(v) && isFinite(v));
  if (validValues.length === 0) return [];
  
  const min = Math.min(...validValues);
  const max = Math.max(...validValues);
  
  if (min === max) {
    return [{
      range: min.toFixed(2),
      count: validValues.length,
      percent: 100,
    }];
  }
  
  const binWidth = (max - min) / bins;
  const histogram: HistogramBin[] = Array(bins).fill(0).map((_, i) => {
    const start = min + i * binWidth;
    const end = min + (i + 1) * binWidth;
    return {
      range: `${start.toFixed(1)}-${end.toFixed(1)}`,
      count: 0,
      percent: 0,
    };
  });
  
  validValues.forEach(v => {
    let binIndex = Math.floor((v - min) / binWidth);
    if (binIndex >= bins) binIndex = bins - 1;
    histogram[binIndex].count++;
  });
  
  histogram.forEach(bin => {
    bin.percent = (bin.count / validValues.length) * 100;
  });
  
  return histogram;
}

function createCategoryDistribution(values: unknown[], maxCategories: number = 10): CategoryCount[] {
  const counts: Record<string, number> = {};
  let total = 0;
  
  values.forEach(v => {
    if (v === null || v === undefined || v === "") return;
    const key = String(v);
    counts[key] = (counts[key] || 0) + 1;
    total++;
  });
  
  const sorted = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxCategories);
  
  const result: CategoryCount[] = sorted.map(([name, value]) => ({
    name: name.length > 20 ? name.slice(0, 17) + "..." : name,
    value,
    percent: (value / total) * 100,
  }));
  
  // Add "Others" if there are more categories
  const othersCount = total - sorted.reduce((acc, [, count]) => acc + count, 0);
  if (othersCount > 0) {
    result.push({
      name: "Others",
      value: othersCount,
      percent: (othersCount / total) * 100,
    });
  }
  
  return result;
}

function StatsCard({ stats, column }: { stats: ColumnStats; column: string }) {
  return (
    <Card className="mb-4">
      <CardHeader className="py-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <Info className="h-4 w-4" />
          Statistics for <code className="bg-muted px-1 rounded">{column}</code>
        </CardTitle>
      </CardHeader>
      <CardContent className="py-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground text-xs">Type</p>
            <p className="font-medium capitalize">{stats.type}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-xs">Count</p>
            <p className="font-medium">{stats.count.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-xs">Missing</p>
            <p className="font-medium">{stats.missing} ({((stats.missing / stats.count) * 100).toFixed(1)}%)</p>
          </div>
          <div>
            <p className="text-muted-foreground text-xs">Unique</p>
            <p className="font-medium">{stats.unique.toLocaleString()}</p>
          </div>
          
          {stats.type === "numeric" && (
            <>
              <div>
                <p className="text-muted-foreground text-xs">Min</p>
                <p className="font-medium">{stats.min?.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Max</p>
                <p className="font-medium">{stats.max?.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Mean</p>
                <p className="font-medium">{stats.mean?.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Std Dev</p>
                <p className="font-medium">{stats.std?.toFixed(2)}</p>
              </div>
            </>
          )}
          
          {stats.type === "boolean" && (
            <>
              <div>
                <p className="text-muted-foreground text-xs">True</p>
                <p className="font-medium text-green-600">{stats.trueCount} ({((stats.trueCount! / (stats.count - stats.missing)) * 100).toFixed(1)}%)</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">False</p>
                <p className="font-medium text-red-600">{stats.falseCount} ({((stats.falseCount! / (stats.count - stats.missing)) * 100).toFixed(1)}%)</p>
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function HistogramChart({ data }: { data: HistogramBin[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <XAxis 
          dataKey="range" 
          angle={-45} 
          textAnchor="end" 
          height={80}
          fontSize={10}
          interval={0}
        />
        <YAxis 
          fontSize={12}
          tickFormatter={(value) => value.toLocaleString()}
        />
        <Tooltip 
          formatter={(value: number, name: string) => [
            `${value.toLocaleString()} (${data.find(d => d.count === value)?.percent.toFixed(1)}%)`,
            "Count"
          ]}
          labelStyle={{ fontFamily: "monospace" }}
        />
        <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]}>
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function CategoryBarChart({ data }: { data: CategoryCount[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ top: 20, right: 30, left: 100, bottom: 20 }}>
        <XAxis type="number" fontSize={12} tickFormatter={(value) => value.toLocaleString()} />
        <YAxis type="category" dataKey="name" fontSize={11} width={90} />
        <Tooltip 
          formatter={(value: number) => [
            `${value.toLocaleString()} (${data.find(d => d.value === value)?.percent.toFixed(1)}%)`,
            "Count"
          ]}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function CategoryPieChart({ data }: { data: CategoryCount[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={({ name, percent }) => `${name}: ${percent.toFixed(0)}%`}
          outerRadius={100}
          fill="#8884d8"
          dataKey="value"
        >
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip 
          formatter={(value: number) => [value.toLocaleString(), "Count"]}
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}

function BooleanChart({ stats }: { stats: ColumnStats }) {
  const data = [
    { name: "True", value: stats.trueCount || 0 },
    { name: "False", value: stats.falseCount || 0 },
  ];
  
  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={90}
          paddingAngle={5}
          dataKey="value"
          label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
        >
          <Cell fill="#10b981" />
          <Cell fill="#ef4444" />
        </Pie>
        <Tooltip formatter={(value: number) => [value.toLocaleString(), "Count"]} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function ColumnDistribution({ columns, rows }: ColumnDistributionProps) {
  const [selectedColumn, setSelectedColumn] = useState<string>(columns[0] || "");
  const [chartType, setChartType] = useState<"bar" | "pie">("bar");
  
  const columnData = useMemo(() => {
    if (!selectedColumn || rows.length === 0) return null;
    
    const values = rows.map(row => row[selectedColumn]);
    const type = getColumnType(values);
    const stats = calculateStats(values, type);
    
    let distribution: HistogramBin[] | CategoryCount[] = [];
    
    if (type === "numeric") {
      const numValues = values
        .filter(v => v !== null && v !== undefined && v !== "")
        .map(v => Number(v));
      distribution = createHistogram(numValues, Math.min(15, Math.ceil(Math.sqrt(numValues.length))));
    } else if (type === "categorical" || type === "datetime") {
      distribution = createCategoryDistribution(values);
    }
    
    return { type, stats, distribution };
  }, [selectedColumn, rows]);
  
  // Filter columns to show only numeric and categorical
  const numericColumns = useMemo(() => {
    return columns.filter(col => {
      const values = rows.map(row => row[col]);
      const type = getColumnType(values);
      return type === "numeric";
    });
  }, [columns, rows]);
  
  const categoricalColumns = useMemo(() => {
    return columns.filter(col => {
      const values = rows.map(row => row[col]);
      const type = getColumnType(values);
      return type === "categorical" || type === "boolean" || type === "datetime";
    });
  }, [columns, rows]);

  if (columns.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No columns available for distribution analysis.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Column Selector */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium">Select Column:</label>
          <Select value={selectedColumn} onValueChange={setSelectedColumn}>
            <SelectTrigger className="w-[250px]">
              <SelectValue placeholder="Select a column" />
            </SelectTrigger>
            <SelectContent className="max-h-[300px]">
              {numericColumns.length > 0 && (
                <>
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                    Numeric Columns
                  </div>
                  {numericColumns.map(col => (
                    <SelectItem key={col} value={col} className="font-mono text-sm">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="h-3 w-3 text-blue-500" />
                        {col}
                      </div>
                    </SelectItem>
                  ))}
                </>
              )}
              {categoricalColumns.length > 0 && (
                <>
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground mt-2">
                    Categorical/Boolean Columns
                  </div>
                  {categoricalColumns.map(col => (
                    <SelectItem key={col} value={col} className="font-mono text-sm">
                      <div className="flex items-center gap-2">
                        <PieChartIcon className="h-3 w-3 text-green-500" />
                        {col}
                      </div>
                    </SelectItem>
                  ))}
                </>
              )}
            </SelectContent>
          </Select>
        </div>
        
        {columnData && columnData.type !== "numeric" && columnData.type !== "boolean" && (
          <Tabs value={chartType} onValueChange={(v) => setChartType(v as "bar" | "pie")}>
            <TabsList className="h-8">
              <TabsTrigger value="bar" className="text-xs gap-1 px-2 h-6">
                <BarChart3 className="h-3 w-3" />
                Bar
              </TabsTrigger>
              <TabsTrigger value="pie" className="text-xs gap-1 px-2 h-6">
                <PieChartIcon className="h-3 w-3" />
                Pie
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      </div>
      
      {/* Stats */}
      {columnData && (
        <StatsCard stats={columnData.stats} column={selectedColumn} />
      )}
      
      {/* Chart */}
      {columnData && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Distribution
              <Badge variant="outline" className="ml-2 text-xs capitalize">
                {columnData.type}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {columnData.type === "numeric" && columnData.distribution.length > 0 && (
              <HistogramChart data={columnData.distribution as HistogramBin[]} />
            )}
            
            {columnData.type === "boolean" && (
              <BooleanChart stats={columnData.stats} />
            )}
            
            {(columnData.type === "categorical" || columnData.type === "datetime") && 
             columnData.distribution.length > 0 && (
              chartType === "bar" ? (
                <CategoryBarChart data={columnData.distribution as CategoryCount[]} />
              ) : (
                <CategoryPieChart data={columnData.distribution as CategoryCount[]} />
              )
            )}
            
            {columnData.distribution.length === 0 && columnData.type !== "boolean" && (
              <div className="text-center py-8 text-muted-foreground">
                Not enough data to display distribution.
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Mini stats component for table headers
interface ColumnHeaderStatsProps {
  columnName: string;
  values: unknown[];
}

const TYPE_ICONS = {
  numeric: Hash,
  boolean: ToggleLeft,
  categorical: Type,
  datetime: Calendar,
  unknown: Info,
};

const TYPE_COLORS = {
  numeric: "text-blue-500",
  boolean: "text-green-500", 
  categorical: "text-purple-500",
  datetime: "text-orange-500",
  unknown: "text-gray-500",
};

function formatCompact(num: number): string {
  if (Math.abs(num) >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (Math.abs(num) >= 1000) return (num / 1000).toFixed(1) + "K";
  if (Number.isInteger(num)) return num.toString();
  return num.toFixed(2);
}

export function ColumnHeaderStats({ columnName, values }: ColumnHeaderStatsProps) {
  const stats = useMemo(() => {
    const type = getColumnType(values);
    return calculateStats(values, type);
  }, [values]);

  const TypeIcon = TYPE_ICONS[stats.type];
  const typeColor = TYPE_COLORS[stats.type];

  return (
    <div className="flex flex-col gap-1 min-w-[120px]">
      {/* Column name with type icon */}
      <div className="flex items-center gap-1.5">
        <TypeIcon className={cn("h-3 w-3", typeColor)} />
        <span className="font-semibold truncate">{columnName}</span>
      </div>
      
      {/* Stats based on type */}
      <div className="text-[10px] font-normal text-muted-foreground space-y-0.5">
        {stats.type === "numeric" && (
          <>
            <div className="flex justify-between gap-2">
              <span>min:</span>
              <span className="font-mono">{stats.min !== undefined ? formatCompact(stats.min) : "-"}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span>max:</span>
              <span className="font-mono">{stats.max !== undefined ? formatCompact(stats.max) : "-"}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span>μ:</span>
              <span className="font-mono">{stats.mean !== undefined ? formatCompact(stats.mean) : "-"}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span>σ:</span>
              <span className="font-mono">{stats.std !== undefined ? formatCompact(stats.std) : "-"}</span>
            </div>
          </>
        )}
        
        {stats.type === "boolean" && (
          <>
            <div className="flex justify-between gap-2">
              <span className="text-green-600">true:</span>
              <span className="font-mono">{stats.trueCount} ({((stats.trueCount! / (stats.count - stats.missing)) * 100).toFixed(0)}%)</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-red-600">false:</span>
              <span className="font-mono">{stats.falseCount} ({((stats.falseCount! / (stats.count - stats.missing)) * 100).toFixed(0)}%)</span>
            </div>
          </>
        )}
        
        {(stats.type === "categorical" || stats.type === "datetime") && (
          <>
            <div className="flex justify-between gap-2">
              <span>unique:</span>
              <span className="font-mono">{stats.unique}</span>
            </div>
          </>
        )}
        
        {stats.missing > 0 && (
          <div className="flex justify-between gap-2 text-amber-600">
            <span>missing:</span>
            <span className="font-mono">{stats.missing}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Precomputed stats for all columns
interface ColumnStatsMap {
  [columnName: string]: ColumnStats;
}

export function useColumnStats(columns: string[], rows: Record<string, unknown>[]): ColumnStatsMap {
  return useMemo(() => {
    const statsMap: ColumnStatsMap = {};
    columns.forEach(col => {
      const values = rows.map(row => row[col]);
      const type = getColumnType(values);
      statsMap[col] = calculateStats(values, type);
    });
    return statsMap;
  }, [columns, rows]);
}
