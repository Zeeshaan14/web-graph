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

export interface ContentBlock {
  type: "heading" | "paragraph" | "list_item";
  level: number | null;
  text: string;
}

export interface ExtractResponse {
  status: "success" | "failed";
  url: string;
  title: string | null;
  blocks: ContentBlock[];
  error: string | null;
}

// ---- website_processing (combined) -----------------------------------------

export interface DiscoverAndExtractResponse {
  status: "success" | "partial" | "failed";
  start_url: string;
  discovery: DiscoverResponse;
  pages: ExtractResponse[];
}

// ---- request plumbing -------------------------------------------------------

interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
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
    const payload = await response.json().catch(() => null);
    if (response.status === 422 && Array.isArray(payload?.detail)) {
      const messages = (payload.detail as ValidationErrorItem[]).map(
        (item) => `${item.loc.at(-1)}: ${item.msg}`
      );
      throw new ApiError(messages.join("; "));
    }
    throw new ApiError(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with status ${response.status}`
    );
  }

  return response.json() as Promise<T>;
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
