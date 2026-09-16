import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import "./globals.css";

import { BackendStatus } from "@/components/backend-status";
import { GraphMark } from "@/components/graph-mark";
import { Nav } from "@/components/nav";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

const archivo = Archivo({
  variable: "--font-heading",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const plexSans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "web-graph",
  description:
    "Website intelligence: tech stack detection, URL discovery, and content extraction from a single URL.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${archivo.variable} ${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider>
            <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-backdrop-filter:bg-background/70">
              <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                <div className="flex items-center justify-between gap-4">
                  <Link
                    href="/"
                    className="flex items-center gap-2 font-heading text-[15px] font-semibold tracking-tight"
                  >
                    <GraphMark className="size-6 text-primary" />
                    web-graph
                  </Link>
                  <div className="flex items-center gap-2 sm:hidden">
                    <BackendStatus />
                    <ThemeToggle />
                  </div>
                </div>
                <Nav />
                <div className="hidden items-center gap-3 sm:flex">
                  <BackendStatus />
                  <ThemeToggle />
                </div>
              </div>
            </header>
            <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-8 pt-4 sm:px-6">{children}</main>
            <footer className="border-t">
              <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 text-center sm:flex-row sm:justify-between sm:px-6 sm:text-left">
                <div className="flex flex-col gap-1">
                  <span className="flex items-center justify-center gap-2 font-heading text-sm font-semibold tracking-tight sm:justify-start">
                    <GraphMark className="size-5 text-primary" />
                    web-graph
                  </span>
                  <p className="font-mono text-xs text-muted-foreground">
                    v1.0 -- 4 features, 1 API, 0 hand-waving
                  </p>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-1.5 sm:justify-end">
                  {["FastAPI", "Next.js", "Playwright", "trafilatura"].map((tech) => (
                    <span
                      key={tech}
                      className="rounded-sm border bg-muted/50 px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {tech}
                    </span>
                  ))}
                </div>
              </div>
            </footer>
          </TooltipProvider>
        </ThemeProvider>
        <Toaster />
      </body>
    </html>
  );
}
