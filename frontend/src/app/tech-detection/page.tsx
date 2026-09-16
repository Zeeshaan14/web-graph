"use client";

import { AlertCircle, Cpu, Layers, Loader2, Search, Sparkles } from "lucide-react";
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
import { PageHero } from "@/components/page-hero";
import { ResultSkeleton } from "@/components/result-skeleton";
import { ConfidenceBadge, StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  detectTech,
  type DetectResponse,
  type DirectTechnology,
  type InferredTechnology,
} from "@/lib/api";

function TechDetectionForm({
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
        <Label htmlFor="tech-url" className="sr-only">
          URL
        </Label>
        <Input
          id="tech-url"
          type="url"
          placeholder="https://example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0"
          required
        />
      </div>
      <Button type="submit" disabled={loading} className="h-10 gap-2 sm:w-36">
        {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
        {loading ? "Detecting..." : "Detect"}
      </Button>
    </form>
  );
}

function TechDetectionPageInner() {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DetectResponse | null>(null);
  const autoRan = useRef(false);

  async function runDetection(targetUrl: string) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await detectTech(targetUrl.trim());
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
      runDetection(paramUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    runDetection(url);
  }

  const direct =
    result?.technologies.filter(
      (t): t is DirectTechnology => t.detection_type === "direct"
    ) ?? [];
  const inferred =
    result?.technologies.filter(
      (t): t is InferredTechnology => t.detection_type === "inferred"
    ) ?? [];

  return (
    <div className="flex flex-col">
      <PageHero
        icon={Cpu}
        eyebrow="Feature 1"
        title="Tech Detection"
        description="Fetches a URL, evaluates weighted fingerprint rules against headers, HTML, scripts and cookies, then enriches with a headless browser when it's worth it. Inferred technologies are kept clearly separate from directly observed evidence."
      >
        <TechDetectionForm url={url} setUrl={setUrl} loading={loading} onSubmit={handleSubmit} />
      </PageHero>

      <div className="flex flex-col gap-6 py-8">
        {loading && <ResultSkeleton />}

        {!loading && !result && (
          <EmptyState
            icon={Cpu}
            title="No detection yet"
            description="Enter a URL above and run a detection to see its technology stack here."
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
                    <Badge variant="outline">
                      HTTP {result.http_status ?? "n/a"}
                    </Badge>
                    <Badge variant="outline">browser: {result.browser_status.replace("_", " ")}</Badge>
                    {result.evidence_source && (
                      <Badge variant="outline">source: {result.evidence_source}</Badge>
                    )}
                  </div>
                </CardDescription>
              </CardHeader>
              {result.errors.length > 0 && (
                <CardContent className="flex flex-col gap-2">
                  {result.errors.map((err, i) => (
                    <Alert variant="destructive" key={i}>
                      <AlertCircle className="size-4" />
                      <AlertTitle>{err.type}</AlertTitle>
                      <AlertDescription>{err.message}</AlertDescription>
                    </Alert>
                  ))}
                </CardContent>
              )}
            </Card>

            {direct.length === 0 && inferred.length === 0 ? (
              <EmptyState
                icon={Layers}
                title="Nothing confidently detected"
                description="No fingerprint matched strongly enough for this URL to report a technology."
              />
            ) : (
              <>
                {direct.length > 0 && (
                  <div className="flex flex-col gap-3">
                    <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                      Directly detected
                    </h2>
                    <div className="grid gap-4 sm:grid-cols-2">
                      {direct.map((tech, i) => (
                        <Card key={i} className="overflow-hidden">
                          <CardHeader>
                            <div className="flex items-center justify-between gap-2">
                              <CardTitle className="text-base">{tech.technology}</CardTitle>
                              <ConfidenceBadge confidence={tech.confidence} />
                            </div>
                            <CardDescription className="flex items-center gap-2 pt-1">
                              <Badge variant="secondary">{tech.category}</Badge>
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="flex flex-col gap-2">
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                                <div
                                  className="h-full rounded-full bg-primary transition-all"
                                  style={{ width: `${tech.confidence_score}%` }}
                                />
                              </div>
                              <span className="text-xs tabular-nums text-muted-foreground">
                                {tech.confidence_score}
                              </span>
                            </div>
                            {tech.evidence.length > 0 && (
                              <Accordion type="single" collapsible>
                                <AccordionItem value="evidence" className="border-b-0">
                                  <AccordionTrigger className="py-1 text-xs text-muted-foreground">
                                    {tech.evidence.length} evidence rule{tech.evidence.length > 1 ? "s" : ""} matched
                                  </AccordionTrigger>
                                  <AccordionContent>
                                    <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
                                      {tech.evidence.map((e, j) => (
                                        <li key={j} className="font-mono">
                                          {e}
                                        </li>
                                      ))}
                                    </ul>
                                  </AccordionContent>
                                </AccordionItem>
                              </Accordion>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                )}

                {inferred.length > 0 && (
                  <div className="flex flex-col gap-3">
                    <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                      Inferred
                    </h2>
                    <div className="flex flex-wrap gap-2">
                      {inferred.map((tech, i) => (
                        <Badge key={i} variant="outline" className="gap-1.5 py-1.5">
                          <Sparkles className="size-3" />
                          {tech.technology}
                          <span className="text-muted-foreground">from {tech.inferred_from}</span>
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function TechDetectionPage() {
  return (
    <Suspense>
      <TechDetectionPageInner />
    </Suspense>
  );
}
