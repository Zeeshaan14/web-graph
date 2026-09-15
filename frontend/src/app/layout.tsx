import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

import { BackendStatus } from "@/components/backend-status";
import { Nav } from "@/components/nav";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider>
            <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-backdrop-filter:bg-background/60">
              <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center justify-between gap-4">
                  <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
                    <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm">
                      wg
                    </span>
                    <span>web-graph</span>
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
            <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
            <footer className="border-t py-6 text-center text-xs text-muted-foreground">
              web-graph V1 -- tech detection, URL discovery, content extraction, combined workflow.
            </footer>
          </TooltipProvider>
        </ThemeProvider>
        <Toaster />
      </body>
    </html>
  );
}
