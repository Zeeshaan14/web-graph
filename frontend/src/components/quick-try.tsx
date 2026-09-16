"use client";

import { ArrowRight, Cpu, FileText, type LucideIcon, Route, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const TOOLS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/tech-detection", label: "Tech Detection", icon: Cpu },
  { href: "/url-discovery", label: "URL Discovery", icon: Route },
  { href: "/content-extraction", label: "Content Extraction", icon: FileText },
  { href: "/discover-and-extract", label: "Discover + Extract", icon: Workflow },
];

export function QuickTry() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [tool, setTool] = useState(TOOLS[0].href);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    router.push(`${tool}?url=${encodeURIComponent(url.trim())}&run=1`);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-lg rounded-lg border bg-card"
    >
      <div className="flex items-stretch">
        <span className="flex items-center border-r px-3 font-mono text-sm text-muted-foreground">
          url:
        </span>
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          type="url"
          placeholder="example.com"
          className="h-11 flex-1 border-0 bg-transparent font-mono text-sm shadow-none focus-visible:ring-0"
          required
        />
        <Button type="submit" className="h-11 gap-1.5 rounded-none rounded-r-[calc(var(--radius)-1px)]">
          Analyze
          <ArrowRight className="size-3.5" />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1 border-t p-1.5">
        {TOOLS.map(({ href, label, icon: Icon }) => (
          <button
            key={href}
            type="button"
            onClick={() => setTool(href)}
            className={cn(
              "flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-xs font-medium transition-colors",
              tool === href
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>
    </form>
  );
}
