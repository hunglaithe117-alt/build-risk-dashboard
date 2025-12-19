"use client";

import { memo, useCallback, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
    ReactFlow,
    Controls,
    Background,
    MiniMap,
    useNodesState,
    useEdgesState,
    BackgroundVariant,
    Handle,
    Position,
    Node,
    Edge,
    NodeProps,
    MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import { Badge } from "@/components/ui/badge";
import { Database, GitBranch, FileCode, Users, Clock, Server } from "lucide-react";

// Types matching backend response
export interface DAGNode {
    id: string;
    type: "extractor" | "resource";
    label: string;
    features: string[];
    feature_count: number;
    requires_resources: string[];
    requires_features: string[];
    level: number;
}

export interface DAGEdge {
    id: string;
    source: string;
    target: string;
    type: "feature_dependency" | "resource_dependency";
}

export interface ExecutionLevel {
    level: number;
    nodes: string[];
}

export interface FeatureDAGData {
    nodes: DAGNode[];
    edges: DAGEdge[];
    execution_levels: ExecutionLevel[];
    total_features: number;
    total_nodes: number;
}

interface FeatureDAGVisualizationProps {
    dagData: FeatureDAGData | null;
    selectedFeatures: string[];
    onFeaturesChange: (features: string[]) => void;
    isLoading?: boolean;
    className?: string;
}

// Simple Tooltip Component
const Tooltip = ({ x, y, label, features, visible }: { x: number; y: number; label: string; features: string[]; visible: boolean }) => {
    if (!visible) return null;
    return (
        <div
            className="absolute z-50 px-3 py-2 text-sm text-white bg-slate-900 rounded-lg shadow-xl pointer-events-none"
            style={{
                left: x,
                top: y - 10,
                transform: 'translate(-50%, -100%)',
                maxWidth: '250px'
            }}
        >
            <div className="font-semibold mb-1">{label}</div>
            <div className="text-xs text-slate-300 max-h-[150px] overflow-y-auto">
                {features.length > 0 ? (
                    <ul className="list-disc list-inside">
                        {features.slice(0, 5).map(f => <li key={f} className="truncate">{f}</li>)}
                        {features.length > 5 && <li>+{features.length - 5} more</li>}
                    </ul>
                ) : (
                    "No features directly extracted"
                )}
            </div>
        </div>
    );
};
const getNodeIcon = (nodeId: string) => {
    if (nodeId.includes("git") || nodeId.includes("commit")) return GitBranch;
    if (nodeId.includes("team") || nodeId.includes("membership")) return Users;
    if (nodeId.includes("workflow") || nodeId.includes("log")) return FileCode;
    if (nodeId === "git_repo" || nodeId === "log_storage") return Database;
    return Server;
};

// Custom Extractor Node
const ExtractorNode = memo(({ data, selected }: NodeProps) => {
    const Icon = getNodeIcon(data.nodeId);
    const isActive = data.featureCount > 0 && data.selectedCount > 0;
    const allSelected = data.selectedCount === data.featureCount;
    const someSelected = data.selectedCount > 0 && data.selectedCount < data.featureCount;

    return (
        <div
            className={`
                px-4 py-3 rounded-xl border-2 shadow-lg min-w-[180px] cursor-pointer
                transition-all duration-200 hover:scale-105
                ${isActive
                    ? "bg-gradient-to-br from-blue-500/20 to-indigo-500/20 border-blue-500/50 dark:from-blue-600/30 dark:to-indigo-600/30"
                    : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700"
                }
                ${selected ? "ring-2 ring-blue-500 ring-offset-2 dark:ring-offset-slate-900" : ""}
            `}
            onClick={() => data.onNodeClick?.(data.nodeId, data.features)}
        >
            <Handle
                type="target"
                position={Position.Top}
                className="!w-3 !h-3 !bg-slate-400 !border-2 !border-white dark:!border-slate-800"
            />

            <div className="flex items-center gap-2 mb-2">
                <div className={`
                    p-1.5 rounded-lg 
                    ${isActive ? "bg-blue-500/20" : "bg-slate-100 dark:bg-slate-700"}
                `}>
                    <Icon className={`h-4 w-4 ${isActive ? "text-blue-500" : "text-slate-500"}`} />
                </div>
                <span className="font-semibold text-sm truncate">{data.label}</span>
            </div>

            <div className="flex items-center justify-between gap-2">
                <Badge
                    variant={allSelected ? "default" : someSelected ? "secondary" : "outline"}
                    className="text-xs"
                >
                    {data.selectedCount}/{data.featureCount} features
                </Badge>
                <div className={`
                    w-2 h-2 rounded-full
                    ${allSelected ? "bg-green-500" : someSelected ? "bg-yellow-500" : "bg-slate-300 dark:bg-slate-600"}
                `} />
            </div>

            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-3 !h-3 !bg-slate-400 !border-2 !border-white dark:!border-slate-800"
            />
        </div>
    );
});
ExtractorNode.displayName = "ExtractorNode";

// Custom Resource Node (hexagon-like)
const ResourceNode = memo(({ data }: NodeProps) => {
    const Icon = getNodeIcon(data.nodeId);

    return (
        <div
            className="px-3 py-2 rounded-lg border-2 border-dashed bg-slate-50 dark:bg-slate-900 
                       border-slate-300 dark:border-slate-600 min-w-[120px]"
        >
            <div className="flex items-center gap-2">
                <Icon className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                    {data.label}
                </span>
            </div>
            <Handle
                type="source"
                position={Position.Bottom}
                className="!w-2 !h-2 !bg-slate-300 !border-2 !border-white dark:!border-slate-900"
            />
        </div>
    );
});
ResourceNode.displayName = "ResourceNode";

const nodeTypes = {
    extractor: ExtractorNode,
    resource: ResourceNode,
};

export function FeatureDAGVisualization({
    dagData,
    selectedFeatures,
    onFeaturesChange,
    isLoading = false,
    className = "",
}: FeatureDAGVisualizationProps) {
    // Tooltip state
    const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string; features: string[]; visible: boolean }>({
        x: 0,
        y: 0,
        label: "",
        features: [],
        visible: false,
    });

    const onNodeMouseEnter = useCallback((event: React.MouseEvent, node: Node) => {
        // Calculate position based on the node's position in the flow
        // The event gives us screen/client coordinates, but we want relative to the flow pane?
        // Actually, for a simple tooltip overlay on top of the flow container, client coordinates relative to container are best.
        // But ReactFlow handles events. Let's try simple offset.

        // Better: Use node position from data if available, or just event target.
        const target = event.currentTarget as HTMLElement;
        const rect = target.getBoundingClientRect();

        // We need the bounding rect of the container to calculate relative position if we put tooltip inside container
        // OR we can use fixed positioning if we use a Portal.
        // Let's rely on the mouse event for simplicity.

        setTooltip({
            x: event.clientX, // We will adjust this in the render if needed, or use fixed
            y: rect.top,
            label: node.data.label,
            features: node.data.features || [],
            visible: true,
        });
    }, []);

    const onNodeMouseLeave = useCallback(() => {
        setTooltip((prev) => ({ ...prev, visible: false }));
    }, []);

    // Convert DAG data to React Flow format
    const { initialNodes, initialEdges } = useMemo(() => {
        if (!dagData) return { initialNodes: [], initialEdges: [] };

        const selectedSet = new Set(selectedFeatures);
        const levelSpacing = 300; // Increased for horizontal spacing (Level -> X)
        const nodeSpacing = 120; // Vertical spacing between nodes (Index -> Y)

        // Group nodes by level for layout
        const nodesByLevel: Record<number, DAGNode[]> = {};
        dagData.nodes.forEach((node) => {
            const level = node.level;
            if (!nodesByLevel[level]) nodesByLevel[level] = [];
            nodesByLevel[level].push(node);
        });

        const nodes: Node[] = dagData.nodes.map((node) => {
            const level = node.level;
            const nodesAtLevel = nodesByLevel[level] || [];
            const indexAtLevel = nodesAtLevel.findIndex((n) => n.id === node.id);
            const totalAtLevel = nodesAtLevel.length;

            // Horizontal Layout: X depends on Level
            // Vertical (Y) depends on Index, centered

            // X position: Level * Spacing
            const x = (level + 1) * levelSpacing;

            // Y position: Center around 0? or Start from top?
            // Let's center them vertically.
            const offsetY = (indexAtLevel - (totalAtLevel - 1) / 2) * nodeSpacing;
            const y = 300 + offsetY; // Base Y + offset

            const selectedCount = node.features.filter((f) => selectedSet.has(f)).length;

            return {
                id: node.id,
                type: node.type,
                position: { x, y },
                data: {
                    label: node.label,
                    nodeId: node.id,
                    features: node.features,
                    featureCount: node.feature_count,
                    selectedCount,
                    onNodeClick: (nodeId: string, features: string[]) => {
                        const allSelected = features.every((f) => selectedSet.has(f));
                        if (allSelected) {
                            // Deselect all features of this node
                            onFeaturesChange(
                                selectedFeatures.filter((f) => !features.includes(f))
                            );
                        } else {
                            // Select all features of this node
                            onFeaturesChange(
                                Array.from(new Set([...selectedFeatures, ...features]))
                            );
                        }
                    },
                },
            };
        });

        const edges: Edge[] = dagData.edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: "smoothstep",
            animated: edge.type === "feature_dependency",
            style: {
                stroke: edge.type === "feature_dependency" ? "#6366f1" : "#94a3b8",
                strokeWidth: edge.type === "feature_dependency" ? 2 : 1,
            },
            markerEnd: {
                type: MarkerType.ArrowClosed,
                color: edge.type === "feature_dependency" ? "#6366f1" : "#94a3b8",
            },
        }));

        return { initialNodes: nodes, initialEdges: edges };
    }, [dagData, selectedFeatures, onFeaturesChange]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Update nodes when data changes
    useMemo(() => {
        setNodes(initialNodes);
        setEdges(initialEdges);
    }, [initialNodes, initialEdges, setNodes, setEdges]);

    if (isLoading) {
        return (
            <div className="h-[400px] flex items-center justify-center bg-slate-50 dark:bg-slate-900/50 rounded-xl border">
                <div className="flex items-center gap-2 text-muted-foreground">
                    <Clock className="h-5 w-5 animate-spin" />
                    <span>Loading DAG...</span>
                </div>
            </div>
        );
    }

    if (!dagData || dagData.nodes.length === 0) {
        return (
            <div className="h-[400px] flex items-center justify-center bg-slate-50 dark:bg-slate-900/50 rounded-xl border">
                <span className="text-muted-foreground">No features available</span>
            </div>
        );
    }

    return (
        <div className={`rounded-xl border bg-slate-50/50 dark:bg-slate-900/30 overflow-hidden ${className}`}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.5}
                maxZoom={1.5}
                proOptions={{ hideAttribution: true }}
                onNodeMouseEnter={onNodeMouseEnter}
                onNodeMouseLeave={onNodeMouseLeave}
            >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
                <Controls className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700 !rounded-lg !shadow-lg" />

                {/* Tooltip Portal or Absolute Overlay */}
                {tooltip.visible && createPortal(
                    <Tooltip {...tooltip} />,
                    document.body
                )}
                <MiniMap
                    className="!bg-white dark:!bg-slate-800 !border-slate-200 dark:!border-slate-700 !rounded-lg"
                    nodeColor={(node) => {
                        if (node.type === "resource") return "#94a3b8";
                        return node.data?.selectedCount > 0 ? "#6366f1" : "#cbd5e1";
                    }}
                />
            </ReactFlow>
        </div>
    );
}
