"use client";

import { AlertCircle, Copy, ExternalLink, Link2, Loader2, Route, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CrawlOptionsPanel } from "@/components/crawl-options-panel";
import { EmptyState } from "@/components/empty-state";
import { PageHero } from "@/components/page-hero";
import { ResultSkeleton } from "@/components/result-skeleton";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, discoverUrls, type DiscoverResponse } from "@/lib/api";
import { DEFAULT_CRAWL_SCOPE_OPTIONS, type CrawlScopeOptions } from "@/lib/crawl-options";
import { normalizeUrlInput } from "@/lib/url";

function UrlDiscoveryForm({
  url,
  setUrl,
  maxPages,
  setMaxPages,
  maxDepth,
  setMaxDepth,
  scopeOptions,
  setScopeOptions,
  loading,
  onSubmit,
}: {
  url: string;
  setUrl: (value: string) => void;
  maxPages: string;
  setMaxPages: (value: string) => void;
  maxDepth: string;
  setMaxDepth: (value: string) => void;
  scopeOptions: CrawlScopeOptions;
  setScopeOptions: (value: CrawlScopeOptions) => void;
  loading: boolean;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="flex w-full max-w-xl flex-col gap-3 rounded-lg border bg-card p-3"
    >
      <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center">
        <div className="flex-1">
          <Label htmlFor="disc-url" className="sr-only">
            URL
          </Label>
          <Input
            id="disc-url"
            type="text"
            inputMode="url"
            placeholder="lakshx.in or https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0"
            required
          />
        </div>
        <Button type="submit" disabled={loading} className="h-10 gap-2 sm:w-36">
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          {loading ? "Crawling..." : "Discover"}
        </Button>
      </div>
      <div className="flex flex-col gap-3 border-t p-2 pt-3 sm:flex-row">
        <div className="flex flex-1 items-center gap-2">
          <Label htmlFor="disc-max-pages" className="whitespace-nowrap text-xs text-muted-foreground">
            Max pages
          </Label>
          <Input
            id="disc-max-pages"
            type="number"
            min={1}
            max={100}
            value={maxPages}
            onChange={(e) => setMaxPages(e.target.value)}
            className="h-8"
          />
        </div>
        <div className="flex flex-1 items-center gap-2">
          <Label htmlFor="disc-max-depth" className="whitespace-nowrap text-xs text-muted-foreground">
            Max depth
          </Label>
          <Input
            id="disc-max-depth"
            type="number"
            min={0}
            max={50}
            placeholder="unbounded"
            value={maxDepth}
            onChange={(e) => setMaxDepth(e.target.value)}
            className="h-8"
          />
        </div>
      </div>
      <CrawlOptionsPanel options={scopeOptions} onChange={setScopeOptions} />
    </form>
  );
}

function UrlDiscoveryPageInner() {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("");
  const [scopeOptions, setScopeOptions] = useState<CrawlScopeOptions>(DEFAULT_CRAWL_SCOPE_OPTIONS);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverResponse | null>(null);
  const autoRan = useRef(false);

  async function runDiscovery(targetUrl: string) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await discoverUrls(
        normalizeUrlInput(targetUrl),
        Number(maxPages) || 10,
        maxDepth.trim() === "" ? null : Number(maxDepth),
        scopeOptions
      );
      setResult(response);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (autoRan.current) return;
    autoRan.current = true;
    const paramUrl = searchParams.get("url");
    if (paramUrl && searchParams.get("run") === "1") {
      // Safe one-time kick-off, guarded by autoRan above -- not the
      // derived-state render loop this rule exists to catch.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      runDiscovery(paramUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    runDiscovery(url);
  }

  function copyAllUrls() {
    if (!result) return;
    navigator.clipboard.writeText(result.discovered_urls.join("\n"));
    toast.success("Copied all URLs to clipboard.");
  }

  return (
    <div className="flex flex-col">
      <PageHero
        icon={Route}
        eyebrow="Feature 2A"
        title="URL Discovery"
        description="BFS-crawls a site starting from the given URL, staying same-site, respecting robots.txt/sitemap.xml, a politeness delay, and 429 retries -- deduplicating output by canonical URL where one exists."
      >
        <UrlDiscoveryForm
          url={url}
          setUrl={setUrl}
          maxPages={maxPages}
          setMaxPages={setMaxPages}
          maxDepth={maxDepth}
          setMaxDepth={setMaxDepth}
          scopeOptions={scopeOptions}
          setScopeOptions={setScopeOptions}
          loading={loading}
          onSubmit={handleSubmit}
        />
      </PageHero>

      <div className="flex flex-col gap-6 py-8">
        {loading && <ResultSkeleton />}

        {!loading && !result && (
          <EmptyState
            icon={Route}
            title="No crawl yet"
            description="Enter a URL above and run a crawl to see every public page it finds here."
          />
        )}

        {!loading && result && (
          <div className="flex animate-in fade-in flex-col gap-6 duration-300">
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  Result for <span className="font-mono text-sm font-normal">{result.start_url}</span>
                </CardTitle>
                <CardDescription>
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <StatusBadge status={result.status} />
                    <Badge variant="outline">{result.pages_traversed} pages traversed</Badge>
                    <Badge variant="outline">{result.discovered_urls.length} URLs found</Badge>
                  </div>
                </CardDescription>
              </CardHeader>
              {result.errors.length > 0 && (
                <CardContent className="flex flex-col gap-2">
                  {result.errors.map((err, i) => (
                    <Alert variant="destructive" key={i}>
                      <AlertCircle className="size-4" />
                      <AlertTitle className="font-mono text-xs">{err.url}</AlertTitle>
                      <AlertDescription>{err.error}</AlertDescription>
                    </Alert>
                  ))}
                </CardContent>
              )}
            </Card>

            {result.discovered_urls.length > 0 ? (
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-base">Discovered URLs</CardTitle>
                  <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={copyAllUrls}>
                    <Copy className="size-3.5" />
                    Copy all
                  </Button>
                </CardHeader>
                <CardContent>
                  <ul className="flex flex-col divide-y">
                    {result.discovered_urls.map((discoveredUrl, i) => (
                      <li key={i} className="flex items-center gap-3 py-2.5 text-sm">
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
                          {i + 1}
                        </span>
                        <a
                          href={discoveredUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-1 truncate font-mono text-xs hover:underline sm:text-sm"
                        >
                          {discoveredUrl}
                        </a>
                        <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ) : (
              <EmptyState
                icon={Link2}
                title="No URLs discovered"
                description="The crawl completed but found no in-scope pages to report."
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function UrlDiscoveryPage() {
  return (
    <Suspense>
      <UrlDiscoveryPageInner />
    </Suspense>
  );
}
