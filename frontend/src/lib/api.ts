// Thin typed client for the web-graph FastAPI backend. Mirrors the Pydantic
// schemas in api/schemas/*.py exactly -- this file has no business logic of
// its own, same principle the backend's own api/ layer follows.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {}

// ---- tech_detection ------------------------------------------------------

export interface ErrorDetail {
  type: string;
  message: string;
}

export interface DirectTechnology {
  technology: string;
  category: string;
  confidence_score: number;
  confidence: "strong" | "likely" | "possible";
  evidence: string[];
  browser_enrichable: boolean;
  detection_type: "direct";
}

export interface InferredTechnology {
  technology: string;
  detection_type: "inferred";
  inferred_from: string;
}

export type Technology = DirectTechnology | InferredTechnology;

export interface DetectResponse {
  url: string;
  status: "success" | "partial" | "failed";
  http_status: number | null;
  browser_status: "not_launched" | "ok" | "failed";
  evidence_source: string | null;
  technologies: Technology[];
  errors: ErrorDetail[];
}

// ---- url_discovery ---------------------------------------------------------

export interface CrawlErrorDetail {
  url: string;
  error: string;
}

export interface DiscoverResponse {
  status: "success" | "partial" | "failed";
  start_url: string;
  discovered_urls: string[];
  pages_traversed: number;
  errors: CrawlErrorDetail[];
}

// ---- content_extraction ----------------------------------------------------

export interface ExtractResponse {
  status: "success" | "failed";
  url: string;
  title: string | null;
  // The page's full body converted to Markdown -- not a boilerplate-
  // stripped "main content" pick. See backend/content_extraction.py.
  content_markdown: string;
  error: string | null;
}

// ---- website_processing (combined) -----------------------------------------

export interface DiscoverAndExtractResponse {
  status: "success" | "partial" | "failed";
  start_url: string;
  discovery: DiscoverResponse;
  pages: ExtractResponse[];
  // Nav/sidebar/footer content observed to repeat across several of this
  // crawl's own pages, pulled out of each page above and reported once
  // here instead. Empty string when nothing met that bar.
  shared_content_markdown: string;
}

// ---- website_processing (streaming) -----------------------------------------

// One JSON object per line (newline-delimited), matching
// api/routes/website_processing.py's discover_and_extract_stream_route()
// exactly -- see that route's docstring for why this isn't
// Server-Sent-Events framing.
export type DiscoverAndExtractStreamEvent =
  | { event: "discovery_started" }
  | { event: "discovery_done"; discovery: DiscoverResponse }
  | { event: "page_fetched"; url: string; status: "success" | "failed" }
  | { event: "dedup_done"; shared_content_markdown: string }
  | { event: "page_rendered"; page: ExtractResponse }
  | { event: "complete"; result: DiscoverAndExtractResponse };

// ---- request plumbing -------------------------------------------------------

interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  if (response.status === 422 && Array.isArray(payload?.detail)) {
    const messages = (payload.detail as ValidationErrorItem[]).map(
      (item) => `${item.loc.at(-1)}: ${item.msg}`
    );
    return new ApiError(messages.join("; "));
  }
  return new ApiError(
    typeof payload?.detail === "string"
      ? payload.detail
      : `Request failed with status ${response.status}`
  );
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is "uv run uvicorn api.main:app --reload" running?`
    );
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return response.json() as Promise<T>;
}

// Streams the same call, one parsed event at a time, via onEvent -- resolves
// once the stream ends (after the "complete" event) or rejects on a
// connection/parse failure. See DiscoverAndExtractStreamEvent for the shape.
export async function discoverAndExtractStream(
  url: string,
  maxPages: number,
  maxDepth: number | null,
  onEvent: (event: DiscoverAndExtractStreamEvent) => void
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/discover-and-extract/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, max_pages: maxPages, max_depth: maxDepth }),
    });
  } catch {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is "uv run uvicorn api.main:app --reload" running?`
    );
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  if (!response.body) {
    throw new ApiError("The backend did not return a streamable response.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // The last split segment is either empty (the chunk ended cleanly on a
    // newline) or a partial line still waiting on more bytes -- either way
    // it goes back in the buffer, not out to onEvent, until it's complete.
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as DiscoverAndExtractStreamEvent);
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as DiscoverAndExtractStreamEvent);
  }
}

export function detectTech(url: string): Promise<DetectResponse> {
  return postJson<DetectResponse>("/detect-tech", { url });
}

export function discoverUrls(
  url: string,
  maxPages: number,
  maxDepth: number | null
): Promise<DiscoverResponse> {
  return postJson<DiscoverResponse>("/discover-urls", {
    url,
    max_pages: maxPages,
    max_depth: maxDepth,
  });
}

export function extractContent(url: string): Promise<ExtractResponse> {
  return postJson<ExtractResponse>("/extract-content", { url });
}

export function discoverAndExtract(
  url: string,
  maxPages: number,
  maxDepth: number | null
): Promise<DiscoverAndExtractResponse> {
  return postJson<DiscoverAndExtractResponse>("/discover-and-extract", {
    url,
    max_pages: maxPages,
    max_depth: maxDepth,
  });
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}
