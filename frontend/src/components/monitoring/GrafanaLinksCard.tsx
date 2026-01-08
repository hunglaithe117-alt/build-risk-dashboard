"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
    ExternalLink,
    BarChart3,
    FileText,
    AlertTriangle,
} from "lucide-react";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3001";

interface GrafanaLink {
    label: string;
    path: string;
    icon: React.ReactNode;
    description: string;
}

const GRAFANA_LINKS: GrafanaLink[] = [
    {
        label: "Dashboard",
        path: "/dashboards",
        icon: <BarChart3 className="h-5 w-5" />,
        description: "View all dashboards",
    },
    {
        label: "Log Explorer",
        path: "/explore?orgId=1&left=%7B%22datasource%22:%22Loki%22%7D",
        icon: <FileText className="h-5 w-5" />,
        description: "Search logs via Loki",
    },
    {
        label: "Alerts",
        path: "/alerting/list",
        icon: <AlertTriangle className="h-5 w-5" />,
        description: "View alert rules",
    },
];

export function GrafanaLinksCard() {
    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <BarChart3 className="h-5 w-5 text-orange-500" />
                        <CardTitle className="text-lg">Grafana Monitoring</CardTitle>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        asChild
                    >
                        <a
                            href={GRAFANA_URL}
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            <ExternalLink className="h-4 w-4 mr-2" />
                            Open Grafana
                        </a>
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {/* Quick Links */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {GRAFANA_LINKS.map((link) => (
                        <a
                            key={link.path}
                            href={`${GRAFANA_URL}${link.path}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent transition-colors"
                        >
                            <div className="p-2 rounded-md bg-orange-500/10 text-orange-600 dark:text-orange-400">
                                {link.icon}
                            </div>
                            <div>
                                <p className="font-medium text-sm">{link.label}</p>
                                <p className="text-xs text-muted-foreground">
                                    {link.description}
                                </p>
                            </div>
                        </a>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
