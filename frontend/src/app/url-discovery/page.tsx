"use client";

import { AlertCircle, ExternalLink, Loader2, Route, Search } from "lucide-react";
import { useState } from "react";
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
import { StatusBadge } from "@/components/status-badge";
import { ApiError, discoverUrls, type DiscoverResponse } from "@/lib/api";

export default function UrlDiscoveryPage() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverResponse | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    try {
      const response = await discoverUrls(
        url.trim(),
        Number(maxPages) || 10,
        maxDepth.trim() === "" ? null : Number(maxDepth)
      );
      setResult(response);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Route className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">URL Discovery</h1>
        </div>
        <p className="max-w-2xl text-muted-foreground">
          BFS-crawls a site starting from the given URL, staying same-site,
          respecting a politeness delay and 429 retries, and deduplicating
          output by canonical URL where one exists.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="disc-url">URL</Label>
              <Input
                id="disc-url"
                type="url"
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="disc-max-pages">Max pages (1-100)</Label>
                <Input
                  id="disc-max-pages"
                  type="number"
                  min={1}
                  max={100}
                  value={maxPages}
                  onChange={(e) => setMaxPages(e.target.value)}
                />
              </div>
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="disc-max-depth">Max depth (optional, 0-50)</Label>
                <Input
                  id="disc-max-depth"
                  type="number"
                  min={0}
                  max={50}
                  placeholder="unbounded"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={loading} className="sm:self-end sm:w-40">
                {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
                {loading ? "Crawling..." : "Discover"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="flex flex-col gap-6">
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

          {result.discovered_urls.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Discovered URLs</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col divide-y">
                  {result.discovered_urls.map((discoveredUrl, i) => (
                    <li key={i} className="flex items-center gap-2 py-2 text-sm">
                      <span className="w-8 shrink-0 text-right text-xs text-muted-foreground">
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
          )}
        </div>
      )}
    </div>
  );
}
