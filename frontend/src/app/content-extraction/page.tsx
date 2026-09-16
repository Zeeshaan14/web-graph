"use client";

import { AlertCircle, FileText, Loader2, ScrollText, Search } from "lucide-react";
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
import { PageHero } from "@/components/page-hero";
import { ResultSkeleton } from "@/components/result-skeleton";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, extractContent, type ExtractResponse } from "@/lib/api";

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
          type="url"
          placeholder="https://example.com/some-article"
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
      const response = await extractContent(targetUrl.trim());
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
        description="Fetches a single URL and pulls its title, headings, and paragraphs -- real content-density scoring (via trafilatura) instead of a fixed tag list, with a JS-rendered page fallback for SPA shells."
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
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  Result for <span className="font-mono text-sm font-normal">{result.url}</span>
                </CardTitle>
                <CardDescription>
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <StatusBadge status={result.status} />
                    {result.status === "success" && (
                      <>
                        <Badge variant="outline">{result.headings.length} headings</Badge>
                        <Badge variant="outline">{result.paragraphs.length} paragraphs</Badge>
                      </>
                    )}
                  </div>
                </CardDescription>
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
              (result.paragraphs.length > 0 || result.headings.length > 0 ? (
                <Card className="overflow-hidden">
                  <div className="h-1.5 bg-primary" />
                  <CardContent className="flex flex-col gap-5 pt-6">
                    {result.title && (
                      <h2 className="text-2xl font-semibold tracking-tight text-balance">
                        {result.title}
                      </h2>
                    )}
                    <div className="flex flex-col gap-5 sm:flex-row sm:gap-8">
                      {result.headings.length > 0 && (
                        <nav className="flex shrink-0 flex-col gap-1.5 sm:w-56">
                          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Outline
                          </h3>
                          <ul className="flex flex-col gap-1 border-l text-sm">
                            {result.headings.map((heading, i) => (
                              <li
                                key={i}
                                className="border-l-2 border-transparent py-0.5 pl-3 text-muted-foreground hover:border-primary hover:text-foreground"
                              >
                                {heading}
                              </li>
                            ))}
                          </ul>
                        </nav>
                      )}
                      {result.paragraphs.length > 0 && (
                        <div className="flex max-h-[36rem] flex-1 flex-col gap-4 overflow-y-auto pr-1">
                          {result.paragraphs.map((paragraph, i) => (
                            <p key={i} className="text-sm leading-relaxed text-foreground/90">
                              {paragraph}
                            </p>
                          ))}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <EmptyState
                  icon={ScrollText}
                  title="No paragraph text found"
                  description="The page was fetched successfully, but no extractable article content was found on it."
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
