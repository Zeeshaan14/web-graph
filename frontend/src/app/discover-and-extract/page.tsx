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
import { MarkdownContent, RawMarkdown } from "@/components/markdown-content";
import { PageHero } from "@/components/page-hero";
import { StatusBadge } from "@/components/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ApiError,
  discoverAndExtractStream,
  type DiscoverAndExtractResponse,
  type DiscoverResponse,
  type ExtractResponse,
} from "@/lib/api";
import { downloadBlob, extractResponseToMarkdown, slugifyUrl } from "@/lib/markdown";
import { normalizeUrlInput } from "@/lib/url";

// A page starts as a bare placeholder (we only know its URL, from the
// discovery_done event) and "graduates" into the full ExtractResponse
// shape once its own page_rendered event arrives -- the same row stays
// mounted throughout (keyed by url), just filling in.
type PageStreamState = { url: string; phase: "pending" } | ({ phase: "done" } & ExtractResponse);

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
            type="text"
            inputMode="url"
            placeholder="lakshx.in or https://example.com"
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
  const [zipping, setZipping] = useState(false);
  const autoRan = useRef(false);

  // Streaming state -- fills in progressively as events arrive, instead of
  // one result object appearing all at once at the end.
  const [phaseLabel, setPhaseLabel] = useState("");
  const [discovery, setDiscovery] = useState<DiscoverResponse | null>(null);
  const [pages, setPages] = useState<PageStreamState[]>([]);
  const [sharedContentMarkdown, setSharedContentMarkdown] = useState("");
  const [finalResult, setFinalResult] = useState<DiscoverAndExtractResponse | null>(null);

  async function runWorkflow(targetUrl: string) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setPhaseLabel("Starting...");
    setDiscovery(null);
    setPages([]);
    setSharedContentMarkdown("");
    setFinalResult(null);

    // Plain closures, not state -- these only ever drive the human-readable
    // phaseLabel text, so there's no reason to round-trip them through React.
    let total = 0;
    let fetched = 0;

    try {
      await discoverAndExtractStream(
        normalizeUrlInput(targetUrl),
        Number(maxPages) || 10,
        maxDepth.trim() === "" ? null : Number(maxDepth),
        (event) => {
          switch (event.event) {
            case "discovery_started":
              setPhaseLabel("Discovering pages...");
              break;
            case "url_discovered":
              // Pages appear one by one as the crawl actually finds them,
              // not all at once when discovery_done finally fires --
              // that event still arrives later with the authoritative
              // discovery summary, but there's no reason to make the user
              // wait for it just to see the first page show up.
              setPages((prev) => [...prev, { url: event.url, phase: "pending" }]);
              setPhaseLabel(`Discovered ${event.count} page${event.count === 1 ? "" : "s"} so far...`);
              break;
            case "discovery_done":
              setDiscovery(event.discovery);
              total = event.discovery.discovered_urls.length;
              setPhaseLabel(total > 0 ? `Fetching 0/${total} pages...` : "No pages to extract.");
              break;
            case "page_fetched":
              fetched += 1;
              setPhaseLabel(`Fetching ${fetched}/${total} pages...`);
              break;
            case "dedup_done":
              setSharedContentMarkdown(event.shared_content_markdown);
              setPhaseLabel("Rendering pages...");
              break;
            case "page_rendered":
              setPages((prev) =>
                prev.map((p) => (p.url === event.page.url ? { phase: "done", ...event.page } : p))
              );
              break;
            case "complete":
              setFinalResult(event.result);
              break;
          }
        }
      );
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function downloadZip() {
    if (!finalResult || finalResult.pages.length === 0) return;
    setZipping(true);
    try {
      const { default: JSZip } = await import("jszip");
      const zip = new JSZip();
      const usedNames = new Set<string>();

      for (const page of finalResult.pages) {
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

      if (finalResult.shared_content_markdown.trim()) {
        zip.file("_shared.md", finalResult.shared_content_markdown);
      }

      const blob = await zip.generateAsync({ type: "blob" });
      downloadBlob(blob, `${slugifyUrl(finalResult.start_url) || "site"}-extract.zip`);
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

  const succeeded = pages.filter((p) => p.phase === "done" && p.status === "success").length;

  return (
    <div className="flex flex-col">
      <PageHero
        icon={Workflow}
        eyebrow="Feature 2C"
        title="Discover + Extract"
        description="Runs URL discovery, then extracts content from every discovered page -- up to 5 pages at once, with its own pacing and retry, folded into one combined result. Nav/sidebar/footer content repeated across pages is deduplicated and reported once. Results stream in live as each stage finishes, not all at once at the end."
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
        {loading && !discovery && pages.length === 0 && (
          // A live status card, not a generic skeleton -- discovery (the
          // crawl itself) commonly takes several seconds with no
          // sub-progress of its own to report, and a static skeleton gives
          // no sign the stream connection is even open during that whole
          // window. This shows the real phase text from the moment the
          // request starts, so the wait reads as "in progress," not frozen.
          // Only shown before the very first page is found -- once
          // url_discovered events start arriving, the main results
          // section below (gated on discovery || pages.length > 0) takes
          // over and shows the same live phase text plus real pages.
          <Card className="animate-in fade-in duration-300">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Result for <span className="font-mono text-sm font-normal">{url}</span>
              </CardTitle>
              <CardDescription>
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  <Badge variant="outline" className="gap-1.5">
                    <Loader2 className="size-3 animate-spin" />
                    {phaseLabel}
                  </Badge>
                </div>
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {!loading && !discovery && !finalResult && pages.length === 0 && (
          <EmptyState
            icon={Workflow}
            title="No run yet"
            description="Enter a URL above to discover a site's pages and extract every one's content in a single pass."
          />
        )}

        {(discovery || pages.length > 0) && (
          <div className="flex animate-in fade-in flex-col gap-6 duration-300">
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  Result for{" "}
                  <span className="font-mono text-sm font-normal">{discovery?.start_url ?? url}</span>
                </CardTitle>
                <CardDescription>
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    {finalResult ? (
                      <StatusBadge status={finalResult.status} />
                    ) : (
                      <Badge variant="outline" className="gap-1.5">
                        <Loader2 className="size-3 animate-spin" />
                        {phaseLabel}
                      </Badge>
                    )}
                    {discovery && <Badge variant="outline">discovery: {discovery.status}</Badge>}
                    {discovery && (
                      <Badge variant="outline">{discovery.pages_traversed} pages traversed</Badge>
                    )}
                    {pages.length > 0 && (
                      <Badge variant="outline">
                        {succeeded}/{pages.length} extracted successfully
                      </Badge>
                    )}
                  </div>
                </CardDescription>
              </CardHeader>
              {pages.length > 0 && (
                <CardContent>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${(succeeded / pages.length) * 100}%` }}
                    />
                  </div>
                </CardContent>
              )}
              {discovery && discovery.errors.length > 0 && (
                <CardContent className="flex flex-col gap-2">
                  {discovery.errors.map((err, i) => (
                    <Alert variant="destructive" key={i}>
                      <AlertCircle className="size-4" />
                      <AlertTitle className="font-mono text-xs">{err.url}</AlertTitle>
                      <AlertDescription>{err.error}</AlertDescription>
                    </Alert>
                  ))}
                </CardContent>
              )}
            </Card>

            {sharedContentMarkdown.trim() && (
              <Card className="overflow-hidden">
                <div className="h-1.5 bg-muted-foreground/40" />
                <CardHeader>
                  <CardTitle className="text-base">Shared across pages</CardTitle>
                  <CardDescription>
                    Nav, sidebar, or footer content repeated on several crawled pages -- pulled out
                    once here instead of duplicated in every page below.
                  </CardDescription>
                </CardHeader>
                <Tabs defaultValue="preview" className="gap-0">
                  <div className="border-b px-4 pt-1">
                    <TabsList variant="line">
                      <TabsTrigger value="preview">Preview</TabsTrigger>
                      <TabsTrigger value="markdown">Markdown</TabsTrigger>
                    </TabsList>
                  </div>
                  <TabsContent value="preview" className="m-0">
                    <CardContent className="max-h-96 overflow-y-auto pt-4 pr-1">
                      <MarkdownContent markdown={sharedContentMarkdown} variant="card" />
                    </CardContent>
                  </TabsContent>
                  <TabsContent value="markdown" className="m-0">
                    <CardContent className="max-h-96 overflow-y-auto pt-4 pr-1">
                      <RawMarkdown markdown={sharedContentMarkdown} />
                    </CardContent>
                  </TabsContent>
                </Tabs>
              </Card>
            )}

            {pages.length > 0 ? (
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-base">Pages</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1.5 text-xs"
                    disabled={zipping || !finalResult}
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
                    {pages.map((page, i) => (
                      <AccordionItem key={page.url} value={`page-${i}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          {page.phase === "pending" ? (
                            <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
                          ) : page.status === "success" ? (
                            <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />
                          ) : (
                            <XCircle className="size-4 shrink-0 text-red-500" />
                          )}
                          {/* A real <a>, not nested inside the accordion's own
                              <button> (invalid HTML) -- a sibling that opens
                              the page in a new tab, independent of expanding
                              the accordion item below it. */}
                          <a
                            href={page.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="shrink-0 font-mono text-xs text-muted-foreground hover:text-foreground hover:underline sm:text-sm"
                          >
                            {page.url}
                          </a>
                          <AccordionTrigger className="gap-3 text-sm">
                            {page.phase === "pending" ? (
                              <span className="text-left text-muted-foreground">Extracting...</span>
                            ) : (
                              page.status === "success" &&
                              page.title && <span className="truncate text-left font-medium">{page.title}</span>
                            )}
                          </AccordionTrigger>
                        </div>
                        <AccordionContent className="flex flex-col gap-3">
                          {page.phase === "pending" ? (
                            <p className="text-sm text-muted-foreground">Still working on this page...</p>
                          ) : (
                            <>
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
                              {page.content_markdown.trim() && (
                                <Tabs defaultValue="preview" className="gap-2">
                                  <TabsList variant="line" className="h-7">
                                    <TabsTrigger value="preview" className="text-xs">
                                      Preview
                                    </TabsTrigger>
                                    <TabsTrigger value="markdown" className="text-xs">
                                      Markdown
                                    </TabsTrigger>
                                  </TabsList>
                                  <TabsContent value="preview" className="m-0">
                                    <div className="max-h-96 overflow-y-auto pr-1">
                                      <MarkdownContent markdown={page.content_markdown} variant="accordion" />
                                    </div>
                                  </TabsContent>
                                  <TabsContent value="markdown" className="m-0">
                                    <div className="max-h-96 overflow-y-auto pr-1">
                                      <RawMarkdown markdown={extractResponseToMarkdown(page)} />
                                    </div>
                                  </TabsContent>
                                </Tabs>
                              )}
                            </>
                          )}
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </CardContent>
              </Card>
            ) : (
              finalResult && (
                <EmptyState
                  icon={Workflow}
                  title="No pages extracted"
                  description="Discovery didn't find any pages to extract content from."
                />
              )
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
