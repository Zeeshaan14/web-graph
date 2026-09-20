"use client";

import { AlertCircle, CheckCircle2, Download, Loader2, Search, Workflow, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
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
import { EmptyState } from "@/components/empty-state";
import { MarkdownContent } from "@/components/markdown-content";
import { PageHero } from "@/components/page-hero";
import { ResultSkeleton } from "@/components/result-skeleton";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, discoverAndExtract, type DiscoverAndExtractResponse } from "@/lib/api";
import { downloadBlob, extractResponseToMarkdown, slugifyUrl } from "@/lib/markdown";

function DiscoverAndExtractForm({
  url,
  setUrl,
  maxPages,
  setMaxPages,
  maxDepth,
  setMaxDepth,
  loading,
  onSubmit,
}: {
  url: string;
  setUrl: (value: string) => void;
  maxPages: string;
  setMaxPages: (value: string) => void;
  maxDepth: string;
  setMaxDepth: (value: string) => void;
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
          <Label htmlFor="combo-url" className="sr-only">
            URL
          </Label>
          <Input
            id="combo-url"
            type="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0"
            required
          />
        </div>
        <Button type="submit" disabled={loading} className="h-10 gap-2 sm:w-44">
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          {loading ? "Working..." : "Run"}
        </Button>
      </div>
      <div className="flex flex-col gap-3 border-t p-2 pt-3 sm:flex-row">
        <div className="flex flex-1 items-center gap-2">
          <Label htmlFor="combo-max-pages" className="whitespace-nowrap text-xs text-muted-foreground">
            Max pages
          </Label>
          <Input
            id="combo-max-pages"
            type="number"
            min={1}
            max={100}
            value={maxPages}
            onChange={(e) => setMaxPages(e.target.value)}
            className="h-8"
          />
        </div>
        <div className="flex flex-1 items-center gap-2">
          <Label htmlFor="combo-max-depth" className="whitespace-nowrap text-xs text-muted-foreground">
            Max depth
          </Label>
          <Input
            id="combo-max-depth"
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
    </form>
  );
}

function DiscoverAndExtractPageInner() {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [maxPages, setMaxPages] = useState("5");
  const [maxDepth, setMaxDepth] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverAndExtractResponse | null>(null);
  const [zipping, setZipping] = useState(false);
  const autoRan = useRef(false);

  async function runWorkflow(targetUrl: string) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await discoverAndExtract(
        targetUrl.trim(),
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

  async function downloadZip() {
    if (!result || result.pages.length === 0) return;
    setZipping(true);
    try {
      const { default: JSZip } = await import("jszip");
      const zip = new JSZip();
      const usedNames = new Set<string>();

      for (const page of result.pages) {
        const baseName = slugifyUrl(page.url);
        let filename = `${baseName}.md`;
        let suffix = 2;
        while (usedNames.has(filename)) {
          filename = `${baseName}-${suffix}.md`;
          suffix += 1;
        }
        usedNames.add(filename);
        zip.file(filename, extractResponseToMarkdown(page));
      }

      const blob = await zip.generateAsync({ type: "blob" });
      downloadBlob(blob, `${slugifyUrl(result.start_url) || "site"}-extract.zip`);
    } catch {
      toast.error("Could not build the .zip file.");
    } finally {
      setZipping(false);
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
      runWorkflow(paramUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    runWorkflow(url);
  }

  const succeeded = result?.pages.filter((p) => p.status === "success").length ?? 0;

  return (
    <div className="flex flex-col">
      <PageHero
        icon={Workflow}
        eyebrow="Feature 2C"
        title="Discover + Extract"
        description="Runs URL discovery, then extracts content from every discovered page -- up to 5 pages at once, with its own pacing and retry, folded into one combined result."
      >
        <DiscoverAndExtractForm
          url={url}
          setUrl={setUrl}
          maxPages={maxPages}
          setMaxPages={setMaxPages}
          maxDepth={maxDepth}
          setMaxDepth={setMaxDepth}
          loading={loading}
          onSubmit={handleSubmit}
        />
      </PageHero>

      <div className="flex flex-col gap-6 py-8">
        {loading && <ResultSkeleton />}

        {!loading && !result && (
          <EmptyState
            icon={Workflow}
            title="No run yet"
            description="Enter a URL above to discover a site's pages and extract every one's content in a single pass."
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
                    <Badge variant="outline">discovery: {result.discovery.status}</Badge>
                    <Badge variant="outline">{result.discovery.pages_traversed} pages traversed</Badge>
                    <Badge variant="outline">
                      {succeeded}/{result.pages.length} extracted successfully
                    </Badge>
                  </div>
                </CardDescription>
              </CardHeader>
              {result.pages.length > 0 && (
                <CardContent>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${(succeeded / result.pages.length) * 100}%` }}
                    />
                  </div>
                </CardContent>
              )}
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

            {result.pages.length > 0 ? (
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-base">Pages</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1.5 text-xs"
                    disabled={zipping}
                    onClick={downloadZip}
                  >
                    {zipping ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Download className="size-3.5" />
                    )}
                    {zipping ? "Zipping..." : "Download .zip"}
                  </Button>
                </CardHeader>
                <CardContent>
                  <Accordion type="single" collapsible className="w-full">
                    {result.pages.map((page, i) => (
                      <AccordionItem key={i} value={`page-${i}`}>
                        <AccordionTrigger className="gap-3 text-sm">
                          <div className="flex flex-1 flex-wrap items-center gap-2 text-left">
                            {page.status === "success" ? (
                              <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />
                            ) : (
                              <XCircle className="size-4 shrink-0 text-red-500" />
                            )}
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
                          {!page.content_markdown.trim() && !page.error && (
                            <p className="text-sm text-muted-foreground">
                              No extractable content was found on this page.
                            </p>
                          )}
                          <div className="max-h-96 overflow-y-auto pr-1">
                            <MarkdownContent markdown={page.content_markdown} variant="accordion" />
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </CardContent>
              </Card>
            ) : (
              <EmptyState
                icon={Workflow}
                title="No pages extracted"
                description="Discovery didn't find any pages to extract content from."
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DiscoverAndExtractPage() {
  return (
    <Suspense>
      <DiscoverAndExtractPageInner />
    </Suspense>
  );
}
