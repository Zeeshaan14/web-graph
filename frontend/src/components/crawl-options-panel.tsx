"use client";

import { ChevronDown, Plus, SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  countActiveCrawlScopeOptions,
  DEFAULT_CRAWL_SCOPE_OPTIONS,
  type CrawlScopeOptions,
} from "@/lib/crawl-options";

function PathList({
  label,
  placeholder,
  values,
  onChange,
}: {
  label: string;
  placeholder: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const pattern = draft.trim();
    if (!pattern || values.includes(pattern)) return;
    onChange([...values, pattern]);
    setDraft("");
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex gap-1.5">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="h-8 font-mono text-xs"
        />
        <Button type="button" variant="outline" size="sm" onClick={add} className="shrink-0">
          <Plus className="size-3.5" />
          Add
        </Button>
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {values.map((value) => (
            <Badge key={value} variant="secondary" className="gap-1 font-mono text-[11px]">
              {value}
              <button
                type="button"
                onClick={() => onChange(values.filter((v) => v !== value))}
                className="rounded-full hover:text-destructive"
                aria-label={`Remove ${value}`}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function NumberField({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  placeholder,
  disabled,
}: {
  label: string;
  description: string;
  value: number | "";
  onChange: (value: number | null) => void;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="flex flex-col">
        <span className={`text-sm ${disabled ? "text-muted-foreground" : ""}`}>{label}</span>
        <span className="text-xs text-muted-foreground">{description}</span>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Input
          type="number"
          min={min}
          max={max}
          step={step ?? 1}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          className="h-8 w-20 text-right"
        />
        {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
}

function ScopeToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="flex flex-col">
        <span className="text-sm">{label}</span>
        <span className="text-xs text-muted-foreground">{description}</span>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} className="shrink-0" />
    </div>
  );
}

export function CrawlOptionsPanel({
  options,
  onChange,
}: {
  options: CrawlScopeOptions;
  onChange: (options: CrawlScopeOptions) => void;
}) {
  const [open, setOpen] = useState(false);
  const activeCount = countActiveCrawlScopeOptions(options);

  function set<K extends keyof CrawlScopeOptions>(key: K, value: CrawlScopeOptions[K]) {
    onChange({ ...options, [key]: value });
  }

  return (
    <div className="flex flex-col gap-2 border-t p-2 pt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-2 self-start text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <SlidersHorizontal className="size-3.5" />
        Options
        {activeCount > 0 && (
          <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
            {activeCount}
          </Badge>
        )}
        <ChevronDown className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="flex flex-col gap-3 rounded-md border bg-muted/30 p-3">
          <PathList
            label="Include only paths (regex)"
            placeholder="^/blog/"
            values={options.includePaths}
            onChange={(v) => set("includePaths", v)}
          />
          <PathList
            label="Exclude paths (regex)"
            placeholder="^/legal/"
            values={options.excludePaths}
            onChange={(v) => set("excludePaths", v)}
          />

          <div className="flex flex-col divide-y">
            <ScopeToggle
              label="Match full URL"
              description="Apply the patterns above to the whole URL (query string included), not just the path."
              checked={options.regexOnFullUrl}
              onChange={(v) => set("regexOnFullUrl", v)}
            />
            <ScopeToggle
              label="Stay under this path"
              description="Only crawl pages under the starting URL's own path, instead of the whole domain."
              checked={options.restrictToStartPath}
              onChange={(v) => set("restrictToStartPath", v)}
            />
            <ScopeToggle
              label="Allow subdomains"
              description="Treat blog.example.com, docs.example.com, etc. as part of the same site."
              checked={options.allowSubdomains}
              onChange={(v) => set("allowSubdomains", v)}
            />
            <ScopeToggle
              label="Follow external links"
              description="Record a link to a different site once, without crawling further into it."
              checked={options.allowExternalLinks}
              onChange={(v) => set("allowExternalLinks", v)}
            />
            <ScopeToggle
              label="Ignore query parameters"
              description="Treat /page?a=1 and /page?a=2 as the same page."
              checked={options.ignoreQueryParameters}
              onChange={(v) => set("ignoreQueryParameters", v)}
            />
            <ScopeToggle
              label="Ignore robots.txt"
              description="Crawl every same-site page regardless of robots.txt. Only use this on sites you own or have permission to crawl."
              checked={options.ignoreRobotsTxt}
              onChange={(v) => set("ignoreRobotsTxt", v)}
            />
          </div>

          <div className="flex flex-col divide-y border-t pt-1">
            <NumberField
              label="Max concurrency"
              description={
                options.delaySeconds !== null
                  ? "Forced to 1 while a delay is set below."
                  : "How many pages to fetch at once, instead of one at a time."
              }
              value={options.maxConcurrency}
              onChange={(v) => set("maxConcurrency", Math.min(10, Math.max(1, v ?? 1)))}
              min={1}
              max={10}
              disabled={options.delaySeconds !== null}
            />
            <NumberField
              label="Delay between fetches"
              description="Pause this many seconds between fetches (forces concurrency to 1). Leave blank for the default pacing."
              value={options.delaySeconds ?? ""}
              onChange={(v) => set("delaySeconds", v)}
              min={0}
              max={60}
              step={0.5}
              suffix="sec"
              placeholder="default"
            />
          </div>

          {activeCount > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 self-start px-2 text-xs text-muted-foreground"
              onClick={() => onChange(DEFAULT_CRAWL_SCOPE_OPTIONS)}
            >
              Reset settings
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
