import {
  ArrowRight,
  Cpu,
  FileSearch,
  FileText,
  Layers,
  Route,
  Workflow,
  Zap,
} from "lucide-react";
import Link from "next/link";

import { CrawlGraphMotif } from "@/components/crawl-graph-motif";
import { QuickTry } from "@/components/quick-try";
import { CardDescription, CardTitle } from "@/components/ui/card";

const FEATURES = [
  {
    href: "/tech-detection",
    icon: Cpu,
    tag: "detect-tech",
    title: "Tech Detection",
    description:
      "Detect the technologies a site is built on from weighted evidence, with directly-detected and inferred results kept separate.",
    points: ["Frameworks, CDNs, hosting, analytics", "Confidence-scored, not guessed", "Browser fallback for JS-only signals"],
  },
  {
    href: "/url-discovery",
    icon: Route,
    tag: "discover-urls",
    title: "URL Discovery",
    description:
      "BFS-crawl a site to discover its public URLs, respecting robots.txt and sitemap.xml along the way.",
    points: ["Canonical-aware deduplication", "Polite pacing + 429 retry", "Playwright fallback for JS-only links"],
  },
  {
    href: "/content-extraction",
    icon: FileText,
    tag: "extract-content",
    title: "Content Extraction",
    description:
      "Pull the title, headings, and paragraphs out of a single page, with real boilerplate removal.",
    points: ["Density-scored content extraction", "5 MB streamed size cap", "JS-rendered page fallback"],
  },
  {
    href: "/discover-and-extract",
    icon: Workflow,
    tag: "discover-and-extract",
    title: "Discover + Extract",
    description:
      "The combined workflow: discover a site's URLs, then extract content from every page found, in parallel.",
    points: ["Up to 5 pages extracted at once", "One combined status", "Full per-page results included"],
  },
] as const;

const STEPS = [
  {
    icon: Zap,
    title: "Fetch",
    description: "A polite HTTP request first -- headers, cookies, HTML, all captured as raw evidence.",
  },
  {
    icon: FileSearch,
    title: "Analyze",
    description: "A generic, data-driven engine evaluates that evidence -- falling back to a real browser render when JS is in the way.",
  },
  {
    icon: Layers,
    title: "Structure",
    description: "Results come back as one predictable, typed shape -- success, partial, or failed, never a raw exception.",
  },
] as const;

export default function Home() {
  return (
    <div className="flex flex-col">
      <section className="relative -mx-4 overflow-hidden border-b px-4 py-12 sm:-mx-6 sm:px-6 sm:py-16">
        <div className="relative mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <div className="flex flex-col gap-6">
            <span className="w-fit rounded-sm border bg-muted/60 px-2 py-1 font-mono text-[11px] text-muted-foreground">
              GET / -&gt; 4 tools, 1 api, v1.0
            </span>
            <h1 className="max-w-xl text-4xl font-semibold tracking-tight sm:text-5xl">
              Website intelligence, from a single URL.
            </h1>
            <p className="max-w-lg text-muted-foreground sm:text-lg">
              web-graph detects a site&apos;s technology stack, discovers its public
              pages, and extracts their content -- a generic, data-driven engine
              built from scratch, not a copy of an existing tool.
            </p>
            <QuickTry />
            <p className="font-mono text-xs text-muted-foreground">
              pick a tool, drop in a url, see a real result -- no sign-up
            </p>
          </div>
          <div className="hidden lg:block">
            <CrawlGraphMotif className="w-full text-foreground" />
          </div>
        </div>
      </section>

      <section className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">
        {FEATURES.map(({ href, icon: Icon, tag, title, description, points }) => (
          <Link key={href} href={href} className="group">
            <div className="flex h-full flex-col gap-4 bg-card p-6 transition-colors group-hover:bg-accent/40">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <Icon className="size-4 text-primary" />
                  <CardTitle className="text-base">{title}</CardTitle>
                </div>
                <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
              </div>
              <CardDescription className="text-[13px] leading-relaxed">{description}</CardDescription>
              <ul className="mt-auto flex flex-col gap-1.5 pt-2 text-xs text-muted-foreground">
                {points.map((point) => (
                  <li key={point} className="flex items-center gap-2">
                    <span className="h-px w-3 shrink-0 bg-border" />
                    {point}
                  </li>
                ))}
              </ul>
              <span className="w-fit rounded-sm border bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                POST /{tag}
              </span>
            </div>
          </Link>
        ))}
      </section>

      <section className="flex flex-col gap-8 py-14">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-xs text-muted-foreground">{"// how it works"}</span>
          <h2 className="text-2xl font-semibold tracking-tight">The same pipeline, every time</h2>
        </div>
        <div className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, description }, i) => (
            <div key={title} className="flex flex-col gap-3 bg-card p-6">
              <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                <span>0{i + 1}</span>
                <Icon className="size-3.5" />
              </div>
              <h3 className="font-heading font-semibold">{title}</h3>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
