"use client";

import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";
import { Activity, BadgeCheck, Database, GitBranch, Home, PanelLeft, PanelLeftClose, Settings, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const navigation = [
  {
    label: "Overview",
    href: "/overview",
    icon: Home,
    adminOnly: false,
    userOnly: false, // Shown to all
  },
  {
    label: "Build Risk Evaluation",
    href: "/repositories",
    icon: BadgeCheck,
    adminOnly: true, // Admin only
    userOnly: false,
  },
  {
    label: "My Repositories",
    href: "/my-repos",
    icon: GitBranch,
    adminOnly: false,
    userOnly: true, // Only for org members
  },
  {
    label: "Data Enrichments",
    href: "/projects",
    icon: Database,
    adminOnly: true, // Admin only
    userOnly: false,
  },
  {
    label: "Monitoring",
    href: "/admin/monitoring",
    icon: Activity,
    adminOnly: true, // Admin only
    userOnly: false,
  },
  {
    label: "Users",
    href: "/admin/users",
    icon: Users,
    adminOnly: true, // Admin only
    userOnly: false,
  },
  {
    label: "App Settings",
    href: "/admin/settings",
    icon: Settings,
    adminOnly: true, // Admin only
    userOnly: false,
  },
];

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function Sidebar({ collapsed = false, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();

  const isAdmin = user?.role === "admin";

  const visibleNavigation = navigation.filter((item) => {
    // Admin sees everything except userOnly
    if (isAdmin) return !item.userOnly;
    // User (org member) sees userOnly and common pages
    return !item.adminOnly;
  });

  const CollapseIcon = collapsed ? PanelLeft : PanelLeftClose;

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-full flex-col border-r bg-white/70 backdrop-blur dark:bg-slate-950/90">
        <div className={cn(
          "flex h-16 items-center gap-2 border-b",
          collapsed ? "justify-center px-2" : "px-6"
        )}>
          <div>
            <p className={cn(
              "font-semibold",
              collapsed ? "text-sm" : "text-lg"
            )}>
              {collapsed ? "BG" : "BuildGuard"}
            </p>
          </div>
        </div>

        <nav className={cn(
          "flex-1 space-y-1 py-4",
          collapsed ? "px-2" : "px-3"
        )}>
          {visibleNavigation.map((item) => {
            const isActive = pathname.startsWith(item.href);
            const Icon = item.icon;

            const linkContent = (
              <Link
                href={item.href}
                className={cn(
                  "group flex items-center rounded-lg text-sm font-medium transition-colors",
                  collapsed ? "justify-center p-2" : "gap-3 px-3 py-2",
                  isActive
                    ? "bg-blue-600 text-white hover:bg-blue-600 hover:text-white"
                    : "text-muted-foreground hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800/70 dark:hover:text-slate-100"
                )}
              >
                <Icon
                  className={cn(
                    collapsed ? "h-5 w-5" : "h-4 w-4",
                    isActive
                      ? "text-white"
                      : "text-muted-foreground group-hover:text-slate-900 dark:group-hover:text-slate-100"
                  )}
                />
                {!collapsed && <span className="flex-1">{item.label}</span>}
              </Link>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.href}>
                  <TooltipTrigger asChild>
                    {linkContent}
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    {item.label}
                  </TooltipContent>
                </Tooltip>
              );
            }

            return <div key={item.href}>{linkContent}</div>;
          })}
        </nav>

        {/* Collapse Toggle Button - Only show on desktop */}
        {onToggleCollapse && (
          <div className={cn(
            "border-t py-3",
            collapsed ? "px-2" : "px-3"
          )}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={onToggleCollapse}
                  className={cn(
                    "flex items-center gap-2 rounded-lg text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground w-full",
                    collapsed ? "justify-center p-2" : "px-3 py-2"
                  )}
                >
                  <CollapseIcon className="h-4 w-4" />
                  {!collapsed && <span></span>}
                </button>
              </TooltipTrigger>
              {collapsed && (
                <TooltipContent side="right">
                  Expand sidebar
                </TooltipContent>
              )}
            </Tooltip>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
