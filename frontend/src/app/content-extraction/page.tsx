"use client";

import { AlertCircle, Download, FileText, Loader2, ScrollText, Search } from "lucide-react";
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
import { EmptyState } from "@/components/empty-state";
import { MarkdownContent, RawMarkdown } from "@/components/markdown-content";
import { PageHero } from "@/components/page-hero";
import { ResultSkeleton } from "@/components/result-skeleton";
import { StatusBadge } from "@/components/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, extractContent, type ExtractResponse } from "@/lib/api";
import { downloadMarkdown, extractResponseToMarkdown, slugifyUrl } from "@/lib/markdown";
import { normalizeUrlInput } from "@/lib/url";

function wordCount(markdown: string): number {
  const trimmed = markdown.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function ContentExtractionForm({
  url,
  setUrl,
  loading,
  onSubmit,
}: {
  url: string;
  setUrl: (value: string) => void;
  loading: boolean;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="flex w-full max-w-xl flex-col gap-3 rounded-lg border bg-card p-3 sm:flex-row sm:items-center"
    >
      <div className="flex-1 flex flex-col gap-1.5">
        <Label htmlFor="extract-url" className="sr-only">
          URL
        </Label>
        <Input
          id="extract-url"
          type="text"
          inputMode="url"
          placeholder="lakshx.in/some-article or https://example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0"
          required
        />
      </div>
      <Button type="submit" disabled={loading} className="h-10 gap-2 sm:w-36">
        {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
        {loading ? "Extracting..." : "Extract"}
      </Button>
    </form>
  );
}

function ContentExtractionPageInner() {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExtractResponse | null>(null);
  const autoRan = useRef(false);

  async function runExtraction(targetUrl: string) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await extractContent(normalizeUrlInput(targetUrl));
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
      runExtraction(paramUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    runExtraction(url);
  }

  return (
    <div className="flex flex-col">
      <PageHero
        icon={FileText}
        eyebrow="Feature 2B"
        title="Content Extraction"
        description="Fetches a single URL and converts its full page -- headings, links, images, lists, nav and footer included -- straight to Markdown, with a JS-rendered page fallback for SPA shells."
      >
        <ContentExtractionForm url={url} setUrl={setUrl} loading={loading} onSubmit={handleSubmit} />
      </PageHero>

      <div className="flex flex-col gap-6 py-8">
        {loading && <ResultSkeleton />}

        {!loading && !result && (
          <EmptyState
            icon={ScrollText}
            title="No extraction yet"
            description="Enter a URL above to pull its title, headings, and paragraph text here."
          />
        )}

        {!loading && result && (
          <div className="flex animate-in fade-in flex-col gap-6 duration-300">
            <Card>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    Result for <span className="font-mono text-sm font-normal">{result.url}</span>
                  </CardTitle>
                  <CardDescription>
                    <div className="flex flex-wrap items-center gap-2 pt-2">
                      <StatusBadge status={result.status} />
                      {result.status === "success" && result.content_markdown.trim() && (
                        <Badge variant="outline">{wordCount(result.content_markdown)} words</Badge>
                      )}
                    </div>
                  </CardDescription>
                </div>
                {result.status === "success" && result.content_markdown.trim() && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0 gap-1.5 text-xs"
                    onClick={() => downloadMarkdown(result, `${slugifyUrl(result.url)}.md`)}
                  >
                    <Download className="size-3.5" />
                    Download .md
                  </Button>
                )}
              </CardHeader>
              {result.error && (
                <CardContent>
                  <Alert variant="destructive">
                    <AlertCircle className="size-4" />
                    <AlertTitle>Extraction failed</AlertTitle>
                    <AlertDescription>{result.error}</AlertDescription>
                  </Alert>
                </CardContent>
              )}
            </Card>

            {result.status === "success" &&
              (result.content_markdown.trim() ? (
                <Card className="overflow-hidden">
                  <div className="h-1.5 bg-primary" />
                  <Tabs defaultValue="preview" className="gap-0">
                    <div className="border-b px-4 pt-3">
                      <TabsList variant="line">
                        <TabsTrigger value="preview">Preview</TabsTrigger>
                        <TabsTrigger value="markdown">Markdown</TabsTrigger>
                      </TabsList>
                    </div>
                    <TabsContent value="preview" className="m-0">
                      <CardContent className="flex max-h-[42rem] flex-col overflow-y-auto pt-6 pr-1">
                        {result.title && (
                          <h2 className="text-2xl font-semibold tracking-tight text-balance">
                            {result.title}
                          </h2>
                        )}
                        <div className="mt-4">
                          <MarkdownContent markdown={result.content_markdown} variant="card" />
                        </div>
                      </CardContent>
                    </TabsContent>
                    <TabsContent value="markdown" className="m-0">
                      <CardContent className="max-h-[42rem] overflow-y-auto pt-6 pr-1">
                        <RawMarkdown markdown={extractResponseToMarkdown(result)} />
                      </CardContent>
                    </TabsContent>
                  </Tabs>
                </Card>
              ) : (
                <EmptyState
                  icon={ScrollText}
                  title="No content found"
                  description="The page was fetched successfully, but its body had no extractable content."
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ContentExtractionPage() {
  return (
    <Suspense>
      <ContentExtractionPageInner />
    </Suspense>
  );
}
