"use client";

import { AlertCircle, Loader2, Search, Workflow } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import { ApiError, discoverAndExtract, type DiscoverAndExtractResponse } from "@/lib/api";

export default function DiscoverAndExtractPage() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState("5");
  const [maxDepth, setMaxDepth] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverAndExtractResponse | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    try {
      const response = await discoverAndExtract(
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
          <Workflow className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Discover + Extract</h1>
        </div>
        <p className="max-w-2xl text-muted-foreground">
          Runs URL discovery, then extracts content from every discovered
          page. Extraction runs sequentially per page with no pacing/retry of
          its own yet, so keep max pages modest on unfamiliar sites.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="combo-url">URL</Label>
              <Input
                id="combo-url"
                type="url"
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="combo-max-pages">Max pages (1-100)</Label>
                <Input
                  id="combo-max-pages"
                  type="number"
                  min={1}
                  max={100}
                  value={maxPages}
                  onChange={(e) => setMaxPages(e.target.value)}
                />
              </div>
              <div className="flex flex-1 flex-col gap-2">
                <Label htmlFor="combo-max-depth">Max depth (optional, 0-50)</Label>
                <Input
                  id="combo-max-depth"
                  type="number"
                  min={0}
                  max={50}
                  placeholder="unbounded"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={loading} className="sm:self-end sm:w-48">
                {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
                {loading ? "Working..." : "Discover + Extract"}
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
                  <Badge variant="outline">
                    discovery: {result.discovery.status}
                  </Badge>
                  <Badge variant="outline">{result.discovery.pages_traversed} pages traversed</Badge>
                  <Badge variant="outline">{result.pages.length} pages extracted</Badge>
                </div>
              </CardDescription>
            </CardHeader>
            {result.discovery.errors.length > 0 && (
              <CardContent className="flex flex-col gap-2">
                {result.discovery.errors.map((err, i) => (
                  <Alert variant="destructive" key={i}>
                    <AlertCircle className="size-4" />
                    <AlertTitle className="font-mono text-xs">{err.url}</AlertTitle>
                    <AlertDescription>{err.error}</AlertDescription>
                  </Alert>
                ))}
              </CardContent>
            )}
          </Card>

          {result.pages.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Pages</CardTitle>
              </CardHeader>
              <CardContent>
                <Accordion type="single" collapsible className="w-full">
                  {result.pages.map((page, i) => (
                    <AccordionItem key={i} value={`page-${i}`}>
                      <AccordionTrigger className="gap-3 text-sm">
                        <div className="flex flex-1 flex-wrap items-center gap-2 text-left">
                          <StatusBadge status={page.status} />
                          <span className="font-mono text-xs text-muted-foreground sm:text-sm">
                            {page.url}
                          </span>
                          {page.status === "success" && page.title && (
                            <span className="truncate font-medium">{page.title}</span>
                          )}
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="flex flex-col gap-3">
                        {page.error && (
                          <Alert variant="destructive">
                            <AlertCircle className="size-4" />
                            <AlertDescription>{page.error}</AlertDescription>
                          </Alert>
                        )}
                        {page.headings.length > 0 && (
                          <ul className="flex flex-col gap-1 text-sm">
                            {page.headings.map((heading, j) => (
                              <li key={j} className="font-medium">
                                {heading}
                              </li>
                            ))}
                          </ul>
                        )}
                        {page.paragraphs.slice(0, 3).map((paragraph, j) => (
                          <p key={j} className="text-sm leading-relaxed text-foreground/90">
                            {paragraph}
                          </p>
                        ))}
                        {page.paragraphs.length > 3 && (
                          <p className="text-xs text-muted-foreground">
                            +{page.paragraphs.length - 3} more paragraph
                            {page.paragraphs.length - 3 > 1 ? "s" : ""}
                          </p>
                        )}
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
