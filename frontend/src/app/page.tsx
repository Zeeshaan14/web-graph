import { ArrowRight, Cpu, FileText, Route, Workflow } from "lucide-react";
import Link from "next/link";

import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const FEATURES = [
  {
    href: "/tech-detection",
    icon: Cpu,
    title: "Tech Detection",
    description:
      "Detect the technologies a site is built on -- frameworks, CDNs, analytics -- from weighted evidence, with directly-detected and inferred results kept separate.",
  },
  {
    href: "/url-discovery",
    icon: Route,
    title: "URL Discovery",
    description:
      "BFS-crawl a site to discover its public URLs, with page/depth limits, canonical-aware deduplication, and polite request pacing.",
  },
  {
    href: "/content-extraction",
    icon: FileText,
    title: "Content Extraction",
    description:
      "Pull the title, headings, and paragraphs out of a single page, preferring its main article content over boilerplate.",
  },
  {
    href: "/discover-and-extract",
    icon: Workflow,
    title: "Discover + Extract",
    description:
      "The combined workflow: discover a site's URLs, then extract content from every page found, in one call.",
  },
] as const;

export default function Home() {
  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Website intelligence, from a single URL.
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          web-graph detects a site&apos;s technology stack, discovers its public
          pages, and extracts their content -- built from scratch as a
          generic, data-driven engine rather than a copy of an existing tool.
          Pick a feature below to try it against a live URL.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURES.map(({ href, icon: Icon, title, description }) => (
          <Link key={href} href={href} className="group">
            <Card className="h-full transition-colors group-hover:border-primary/50">
              <CardHeader>
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <CardTitle className="text-lg">{title}</CardTitle>
                </div>
                <CardDescription className="pt-2">{description}</CardDescription>
                <CardAction>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                </CardAction>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
