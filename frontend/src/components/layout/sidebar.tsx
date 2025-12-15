"use client";

import { cn } from "@/lib/utils";
import { Activity, BadgeCheck, Database, Home, Key } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
const navigation = [
  {
    label: "Overview",
    href: "/dashboard",
    icon: Home,
  },
  {
    label: "Projects",
    href: "/admin/datasets",
    icon: Database,
  },
  {
    label: "Repositories",
    href: "/admin/repos",
    icon: BadgeCheck,
  },
  {
    label: "Pipeline Runs",
    href: "/admin/pipeline",
    icon: Activity,
  },
  {
    label: "Public GitHub Tokens",
    href: "/admin/tokens",
    icon: Key,
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col border-r bg-white/70 backdrop-blur dark:bg-slate-950/90">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <div>
          <p className="text-lg font-semibold">BuildGuard</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
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
