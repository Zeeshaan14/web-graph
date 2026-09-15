"use client";

import { Cpu, FileText, Route, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/tech-detection", label: "Tech Detection", icon: Cpu },
  { href: "/url-discovery", label: "URL Discovery", icon: Route },
  { href: "/content-extraction", label: "Content Extraction", icon: FileText },
  { href: "/discover-and-extract", label: "Discover + Extract", icon: Workflow },
] as const;

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1 overflow-x-auto">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <Icon className="size-4" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
