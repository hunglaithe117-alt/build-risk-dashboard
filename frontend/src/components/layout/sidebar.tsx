"use client";

import { cn } from "@/lib/utils";
import { Activity, BadgeCheck, Database, GitBranch, Home, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

const navigation = [
  {
    label: "Overview",
    href: "/overview",
    icon: Home,
    adminOnly: false,
    userOnly: false, // Shown to all
  },
  {
    label: "My Repositories",
    href: "/repos",
    icon: GitBranch,
    adminOnly: false,
    userOnly: true,
  },
  {
    label: "Projects",
    href: "/admin/datasets",
    icon: Database,
    adminOnly: true,
    userOnly: false,
  },
  {
    label: "Repositories",
    href: "/admin/repos",
    icon: BadgeCheck,
    adminOnly: true,
    userOnly: false,
  },
  {
    label: "Monitoring",
    href: "/admin/monitoring",
    icon: Activity,
    adminOnly: true,
    userOnly: false,
  },
  {
    label: "Users",
    href: "/admin/users",
    icon: Users,
    adminOnly: true,
    userOnly: false,
  }
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const isAdmin = user?.role === "admin";

  const visibleNavigation = navigation.filter((item) => {
    if (item.adminOnly && !isAdmin) return false;
    if (item.userOnly && isAdmin) return false;
    return true;
  });

  return (
    <div className="flex h-full flex-col border-r bg-white/70 backdrop-blur dark:bg-slate-950/90">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <div>
          <p className="text-lg font-semibold">BuildGuard</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {visibleNavigation.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-blue-600 text-white hover:text-white" : ""
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4",
                  isActive ? "text-white" : "text-muted-foreground"
                )}
              />
              <span className="flex-1">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

