"use client";

import { useEffect, useState } from "react";

import { checkHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

export function BackendStatus() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      const ok = await checkHealth();
      if (!cancelled) setOnline(ok);
    }

    poll();
    const interval = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const label =
    online === null ? "Checking backend..." : online ? "Backend online" : "Backend offline";

  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground" title={label}>
      <span
        className={cn(
          "size-2 rounded-full",
          online === null && "bg-muted-foreground/40",
          online === true && "bg-emerald-500",
          online === false && "bg-red-500"
        )}
      />
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}
