"use client";

import { useState, useEffect, useCallback } from "react";
import { tokensApi } from "@/lib/api";
import type { GithubToken, TokenPoolStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Key,
    Plus,
    Trash2,
    Edit2,
    CheckCircle,
    XCircle,
    Clock,
    RefreshCw,
    AlertCircle,
    Power,
    PowerOff,
    Activity,
} from "lucide-react";

export default function TokensPage() {
    const [tokens, setTokens] = useState<GithubToken[]>([]);
    const [poolStatus, setPoolStatus] = useState<TokenPoolStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [includeDisabled, setIncludeDisabled] = useState(false);

    // Add token modal
    const [showAddModal, setShowAddModal] = useState(false);
    const [newToken, setNewToken] = useState("");
    const [newLabel, setNewLabel] = useState("");
    const [addingToken, setAddingToken] = useState(false);

    // Edit token
    const [editingToken, setEditingToken] = useState<string | null>(null);
    const [editLabel, setEditLabel] = useState("");

    const { toast } = useToast();

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            const [tokensRes, statusRes] = await Promise.all([
                tokensApi.list(includeDisabled),
                tokensApi.getStatus(),
            ]);
            setTokens(tokensRes.items);
            setPoolStatus(statusRes);
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to fetch tokens",
                variant: "destructive",
            });
        } finally {
            setLoading(false);
        }
    }, [includeDisabled, toast]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const handleAddToken = async () => {
        if (!newToken.trim()) {
            toast({
                title: "Error",
                description: "Token cannot be empty",
                variant: "destructive",
            });
            return;
        }

        try {
            setAddingToken(true);
            await tokensApi.create({
                token: newToken,
                label: newLabel || undefined,
            });
            toast({
                title: "Success",
                description: "Token added successfully",
            });
            setNewToken("");
            setNewLabel("");
            setShowAddModal(false);
            fetchData();
        } catch (error: any) {
            const message = error.response?.data?.detail || "Failed to add token";
            toast({
                title: "Error",
                description: message,
                variant: "destructive",
            });
        } finally {
            setAddingToken(false);
        }
    };

    const handleDeleteToken = async (tokenId: string) => {
        if (!confirm("Are you sure you want to delete this token?")) return;

        try {
            await tokensApi.delete(tokenId);
            toast({
                title: "Success",
                description: "Token deleted",
            });
            fetchData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to delete token",
                variant: "destructive",
            });
        }
    };

    const handleToggleStatus = async (token: GithubToken) => {
        const newStatus = token.status === "disabled" ? "active" : "disabled";
        try {
            await tokensApi.update(token.id, { status: newStatus });
            toast({
                title: "Success",
                description: `Token ${newStatus === "disabled" ? "disabled" : "enabled"}`,
            });
            fetchData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to update token",
                variant: "destructive",
            });
        }
    };

    const handleUpdateLabel = async (tokenId: string) => {
        try {
            await tokensApi.update(tokenId, { label: editLabel });
            toast({
                title: "Success",
                description: "Label updated",
            });
            setEditingToken(null);
            fetchData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to update label",
                variant: "destructive",
            });
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "active":
                return <Badge className="bg-green-500 hover:bg-green-600"><CheckCircle className="w-3 h-3 mr-1" />Active</Badge>;
            case "rate_limited":
                return <Badge className="bg-yellow-500 hover:bg-yellow-600"><Clock className="w-3 h-3 mr-1" />Rate Limited</Badge>;
            case "invalid":
                return <Badge className="bg-red-500 hover:bg-red-600"><XCircle className="w-3 h-3 mr-1" />Invalid</Badge>;
            case "disabled":
                return <Badge variant="outline"><PowerOff className="w-3 h-3 mr-1" />Disabled</Badge>;
            default:
                return <Badge variant="outline">{status}</Badge>;
        }
    };

    const formatResetTime = (resetAt: string | null) => {
        if (!resetAt) return "-";
        const reset = new Date(resetAt);
        const now = new Date();
        const diffMs = reset.getTime() - now.getTime();

        if (diffMs <= 0) return "Ready";

        const diffMins = Math.ceil(diffMs / 60000);
        if (diffMins < 60) return `${diffMins}m`;
        return `${Math.floor(diffMins / 60)}h ${diffMins % 60}m`;
    };

    const formatDate = (date: string | null) => {
        if (!date) return "-";
        return new Date(date).toLocaleString();
    };

    const quotaPercentage = poolStatus
        ? Math.min(100, (poolStatus.estimated_requests_available / (poolStatus.total_tokens * 5000)) * 100)
        : 0;

    return (
        <div className="container mx-auto py-6 space-y-6">
            {/* Header with Remaining Requests */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold flex items-center gap-3">
                        GitHub Tokens
                        {poolStatus && (
                            <Badge
                                variant="outline"
                                className={`text-lg px-3 py-1 ${poolStatus.estimated_requests_available === 0
                                    ? "border-red-500 text-red-600"
                                    : poolStatus.estimated_requests_available < 1000
                                        ? "border-yellow-500 text-yellow-600"
                                        : "border-green-500 text-green-600"
                                    }`}
                            >
                                <Activity className="w-4 h-4 mr-2" />
                                {poolStatus.estimated_requests_available.toLocaleString()} requests remaining
                            </Badge>
                        )}
                    </h1>
                    <p className="text-muted-foreground">
                        Manage public tokens for GitHub API access
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={fetchData} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                        Refresh
                    </Button>
                    <Button
                        variant="outline"
                        onClick={async () => {
                            try {
                                setLoading(true);
                                const result = await tokensApi.refreshAll();
                                toast({
                                    title: "Rate Limits Updated",
                                    description: `${result.refreshed} tokens refreshed, ${result.failed} failed`,
                                });
                                fetchData();
                            } catch (error) {
                                toast({
                                    title: "Error",
                                    description: "Failed to refresh rate limits",
                                    variant: "destructive",
                                });
                            } finally {
                                setLoading(false);
                            }
                        }}
                        disabled={loading}
                    >
                        <Activity className={`w-4 h-4 mr-2 ${loading ? "animate-pulse" : ""}`} />
                        Sync Rate Limits
                    </Button>
                    <Button onClick={() => setShowAddModal(true)}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Token
                    </Button>
                </div>
            </div>

            {/* Pool Status Cards */}
            {poolStatus && (
                <div className="grid gap-4 md:grid-cols-4">
                    <Card>
                        <CardHeader className="pb-2">
                            <CardDescription>Total Tokens</CardDescription>
                            <CardTitle className="text-3xl">{poolStatus.total_tokens}</CardTitle>
                        </CardHeader>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardDescription>Active</CardDescription>
                            <CardTitle className="text-3xl text-green-600">{poolStatus.active_tokens}</CardTitle>
                        </CardHeader>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardDescription>Rate Limited</CardDescription>
                            <CardTitle className="text-3xl text-yellow-600">{poolStatus.rate_limited_tokens}</CardTitle>
                        </CardHeader>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardDescription>Invalid</CardDescription>
                            <CardTitle className="text-3xl text-red-600">{poolStatus.invalid_tokens}</CardTitle>
                        </CardHeader>
                    </Card>
                </div>
            )}

            {/* Quota Progress */}
            {poolStatus && (
                <Card>
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg">Estimated Quota Available</CardTitle>
                                <CardDescription>
                                    ~{poolStatus.estimated_requests_available.toLocaleString()} requests remaining
                                </CardDescription>
                            </div>
                            {poolStatus.next_reset_at && (
                                <Badge variant="outline" className="text-sm">
                                    <Clock className="w-3 h-3 mr-1" />
                                    Next reset: {formatResetTime(poolStatus.next_reset_at)}
                                </Badge>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent>
                        <Progress value={quotaPercentage} className="h-3" />
                        <div className="flex justify-between mt-1 text-xs text-muted-foreground">
                            <span>0%</span>
                            <span>{Math.round(quotaPercentage)}% of max capacity</span>
                            <span>100%</span>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Pool Health Alert */}
            {poolStatus && !poolStatus.pool_healthy && (
                <Card className="border-red-500 bg-red-50 dark:bg-red-950">
                    <CardHeader className="pb-2">
                        <div className="flex items-center gap-2">
                            <AlertCircle className="w-5 h-5 text-red-600" />
                            <CardTitle className="text-red-600">Pool Unhealthy</CardTitle>
                        </div>
                        <CardDescription className="text-red-600/80">
                            No active tokens available. Add new tokens or wait for rate limits to reset.
                            {poolStatus.next_reset_at && (
                                <span className="ml-1">Next reset in {formatResetTime(poolStatus.next_reset_at)}.</span>
                            )}
                        </CardDescription>
                    </CardHeader>
                </Card>
            )}

            {/* Exhausted Requests Alert */}
            {poolStatus && poolStatus.estimated_requests_available === 0 && poolStatus.pool_healthy && (
                <Card className="border-orange-500 bg-orange-50 dark:bg-orange-950">
                    <CardHeader className="pb-2">
                        <div className="flex items-center gap-2">
                            <AlertCircle className="w-5 h-5 text-orange-600" />
                            <CardTitle className="text-orange-600">All Requests Exhausted</CardTitle>
                        </div>
                        <CardDescription className="text-orange-600/80">
                            All tokens have reached their rate limit (0 requests remaining).
                            You cannot make API calls until the rate limits reset.
                            {poolStatus.next_reset_at && (
                                <span className="block mt-1 font-medium">
                                    Next reset in {formatResetTime(poolStatus.next_reset_at)}.
                                </span>
                            )}
                        </CardDescription>
                    </CardHeader>
                </Card>
            )}

            {/* Low Quota Warning */}
            {poolStatus && poolStatus.estimated_requests_available > 0 && poolStatus.estimated_requests_available < 500 && (
                <Card className="border-yellow-500 bg-yellow-50 dark:bg-yellow-950">
                    <CardHeader className="pb-2">
                        <div className="flex items-center gap-2">
                            <AlertCircle className="w-5 h-5 text-yellow-600" />
                            <CardTitle className="text-yellow-600">Low Quota Warning</CardTitle>
                        </div>
                        <CardDescription className="text-yellow-600/80">
                            Only {poolStatus.estimated_requests_available.toLocaleString()} requests remaining.
                            Consider adding more tokens or waiting for rate limits to reset.
                        </CardDescription>
                    </CardHeader>
                </Card>
            )}

            {/* Add Token Modal */}
            <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Key className="w-5 h-5" />
                            Add New Token
                        </DialogTitle>
                        <DialogDescription>
                            Enter a GitHub personal access token. The token will be hashed for secure storage.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Token</label>
                            <Input
                                type="password"
                                placeholder="ghp_xxxxxxxxxxxx"
                                value={newToken}
                                onChange={(e) => setNewToken(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter" && newToken.trim()) handleAddToken();
                                }}
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Label (optional)</label>
                            <Input
                                placeholder="e.g., Personal Token 1"
                                value={newLabel}
                                onChange={(e) => setNewLabel(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter" && newToken.trim()) handleAddToken();
                                }}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddModal(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleAddToken} disabled={addingToken || !newToken.trim()}>
                            {addingToken ? "Adding..." : "Add Token"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Tokens Table */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle>Tokens</CardTitle>
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={includeDisabled}
                                onChange={(e) => setIncludeDisabled(e.target.checked)}
                                className="rounded"
                            />
                            Show disabled
                        </label>
                    </div>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Label</TableHead>
                                <TableHead>Token</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead className="text-right">Remaining</TableHead>
                                <TableHead>Reset</TableHead>
                                <TableHead>Last Used</TableHead>
                                <TableHead className="text-right">Total Requests</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {tokens.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                                        No tokens configured. Add a token to get started.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                tokens.map((token) => (
                                    <TableRow key={token.id}>
                                        <TableCell>
                                            {editingToken === token.id ? (
                                                <div className="flex gap-1">
                                                    <Input
                                                        value={editLabel}
                                                        onChange={(e) => setEditLabel(e.target.value)}
                                                        className="h-8 w-40"
                                                        onKeyDown={(e) => {
                                                            if (e.key === "Enter") handleUpdateLabel(token.id);
                                                            if (e.key === "Escape") setEditingToken(null);
                                                        }}
                                                    />
                                                    <Button size="sm" variant="ghost" onClick={() => handleUpdateLabel(token.id)}>
                                                        <CheckCircle className="w-4 h-4" />
                                                    </Button>
                                                </div>
                                            ) : (
                                                <span className="font-medium">{token.label || "-"}</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <code className="text-xs bg-muted px-2 py-1 rounded">{token.masked_token}</code>
                                        </TableCell>
                                        <TableCell>{getStatusBadge(token.status)}</TableCell>
                                        <TableCell className="text-right">
                                            {token.rate_limit_remaining !== null ? (
                                                <span className={token.rate_limit_remaining === 0 ? "text-red-600" : ""}>
                                                    {token.rate_limit_remaining.toLocaleString()}
                                                    {token.rate_limit_limit && (
                                                        <span className="text-muted-foreground">/{token.rate_limit_limit.toLocaleString()}</span>
                                                    )}
                                                </span>
                                            ) : (
                                                "-"
                                            )}
                                        </TableCell>
                                        <TableCell>{formatResetTime(token.rate_limit_reset_at)}</TableCell>
                                        <TableCell className="text-sm text-muted-foreground">
                                            {formatDate(token.last_used_at)}
                                        </TableCell>
                                        <TableCell className="text-right">{token.total_requests.toLocaleString()}</TableCell>
                                        <TableCell className="text-right">
                                            <div className="flex gap-1 justify-end">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        setEditingToken(token.id);
                                                        setEditLabel(token.label);
                                                    }}
                                                    title="Edit label"
                                                >
                                                    <Edit2 className="w-4 h-4" />
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => handleToggleStatus(token)}
                                                    title={token.status === "disabled" ? "Enable" : "Disable"}
                                                >
                                                    {token.status === "disabled" ? (
                                                        <Power className="w-4 h-4" />
                                                    ) : (
                                                        <PowerOff className="w-4 h-4" />
                                                    )}
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="text-red-600 hover:text-red-700"
                                                    onClick={() => handleDeleteToken(token.id)}
                                                    title="Delete"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </Button>
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
