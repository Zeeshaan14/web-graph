"use client";

import { AlertCircle, FileText, Loader2, Search } from "lucide-react";
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
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, extractContent, type ExtractResponse } from "@/lib/api";

export default function ContentExtractionPage() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExtractResponse | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    try {
      const response = await extractContent(url.trim());
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
          <FileText className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Content Extraction</h1>
        </div>
        <p className="max-w-2xl text-muted-foreground">
          Fetches a single URL and pulls its title, headings, and paragraphs
          -- preferring an <code className="font-mono">&lt;article&gt;</code>{" "}
          or <code className="font-mono">&lt;main&gt;</code> region and
          stripping scripts, nav, footer, and aside boilerplate first.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1 flex flex-col gap-2">
              <Label htmlFor="extract-url">URL</Label>
              <Input
                id="extract-url"
                type="url"
                placeholder="https://example.com/some-article"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={loading} className="sm:w-40">
              {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              {loading ? "Extracting..." : "Extract"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
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
          <CardContent className="flex flex-col gap-4">
            {result.error && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertTitle>Extraction failed</AlertTitle>
                <AlertDescription>{result.error}</AlertDescription>
              </Alert>
            )}

            {result.status === "success" && (
              <>
                {result.title && (
                  <div>
                    <h2 className="text-lg font-semibold">{result.title}</h2>
                  </div>
                )}

                {result.headings.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Headings
                    </h3>
                    <ul className="flex flex-col gap-1 text-sm">
                      {result.headings.map((heading, i) => (
                        <li key={i}>{heading}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.headings.length > 0 && result.paragraphs.length > 0 && <Separator />}

                {result.paragraphs.length > 0 ? (
                  <div className="flex flex-col gap-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Paragraphs
                    </h3>
                    <div className="flex max-h-[32rem] flex-col gap-3 overflow-y-auto pr-1">
                      {result.paragraphs.map((paragraph, i) => (
                        <p key={i} className="text-sm leading-relaxed text-foreground/90">
                          {paragraph}
                        </p>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No paragraph text was found on this page.</p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
