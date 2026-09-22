// Shared shape for the crawl-scope options exposed by both URL Discovery
// and Discover + Extract -- both hit the same url_discovery.crawler
// underneath, so the same options panel and the same request fields work
// for either page. Mirrors api/schemas/url_discovery.py's DiscoverRequest
// scope fields (camelCase here, snake_case there -- see toRequestFields()).

export interface CrawlScopeOptions {
  includePaths: string[];
  excludePaths: string[];
  regexOnFullUrl: boolean;
  restrictToStartPath: boolean;
  allowSubdomains: boolean;
  allowExternalLinks: boolean;
  ignoreQueryParameters: boolean;
  ignoreRobotsTxt: boolean;
}

export const DEFAULT_CRAWL_SCOPE_OPTIONS: CrawlScopeOptions = {
  includePaths: [],
  excludePaths: [],
  regexOnFullUrl: false,
  restrictToStartPath: false,
  allowSubdomains: false,
  allowExternalLinks: false,
  ignoreQueryParameters: false,
  ignoreRobotsTxt: false,
};

export function crawlScopeOptionsToRequestFields(options: CrawlScopeOptions) {
  return {
    include_paths: options.includePaths.length > 0 ? options.includePaths : null,
    exclude_paths: options.excludePaths.length > 0 ? options.excludePaths : null,
    regex_on_full_url: options.regexOnFullUrl,
    restrict_to_start_path: options.restrictToStartPath,
    allow_subdomains: options.allowSubdomains,
    allow_external_links: options.allowExternalLinks,
    ignore_query_parameters: options.ignoreQueryParameters,
    ignore_robots_txt: options.ignoreRobotsTxt,
  };
}

// True if anything differs from the defaults -- used to show a "N active"
// badge on the collapsed Options toggle so a caller doesn't have to open
// the panel to know a non-default crawl is about to run.
export function countActiveCrawlScopeOptions(options: CrawlScopeOptions): number {
  let count = 0;
  if (options.includePaths.length > 0) count++;
  if (options.excludePaths.length > 0) count++;
  if (options.regexOnFullUrl) count++;
  if (options.restrictToStartPath) count++;
  if (options.allowSubdomains) count++;
  if (options.allowExternalLinks) count++;
  if (options.ignoreQueryParameters) count++;
  if (options.ignoreRobotsTxt) count++;
  return count;
}
