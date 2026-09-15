"use client";

import { AlertCircle, Cpu, Loader2, Search, Sparkles } from "lucide-react";
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
import { ConfidenceBadge, StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  detectTech,
  type DetectResponse,
  type DirectTechnology,
  type InferredTechnology,
} from "@/lib/api";

export default function TechDetectionPage() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DetectResponse | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    try {
      const response = await detectTech(url.trim());
      setResult(response);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
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
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Cpu className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Tech Detection</h1>
        </div>
        <p className="max-w-2xl text-muted-foreground">
          Fetches a URL, evaluates weighted fingerprint rules against headers,
          HTML, scripts and cookies, then enriches with a headless browser
          when it&apos;s worth it. Inferred technologies (e.g. React implied by
          Next.js) are kept clearly separate from directly observed evidence.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1 flex flex-col gap-2">
              <Label htmlFor="tech-url">URL</Label>
              <Input
                id="tech-url"
                type="url"
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={loading} className="sm:w-40">
              {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              {loading ? "Detecting..." : "Detect"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="flex flex-col gap-6">
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
            <p className="text-sm text-muted-foreground">
              No technologies were confidently detected for this URL.
            </p>
          ) : (
            <>
              {direct.length > 0 && (
                <div className="flex flex-col gap-3">
                  <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                    Directly detected
                  </h2>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {direct.map((tech, i) => (
                      <Card key={i}>
                        <CardHeader>
                          <div className="flex items-center justify-between gap-2">
                            <CardTitle className="text-base">{tech.technology}</CardTitle>
                            <ConfidenceBadge confidence={tech.confidence} />
                          </div>
                          <CardDescription className="flex items-center gap-2 pt-1">
                            <Badge variant="secondary">{tech.category}</Badge>
                            <span className="text-xs">score {tech.confidence_score}</span>
                          </CardDescription>
                        </CardHeader>
                        {tech.evidence.length > 0 && (
                          <CardContent>
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
                          </CardContent>
                        )}
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
  );
}
